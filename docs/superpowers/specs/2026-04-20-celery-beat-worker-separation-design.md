# Celery Beat/Worker Separation Design

**Date**: 2026-04-20
**Goal**: Separate celery-beat (DB access, static scheduler) from celery-workers (no DB, off-host capable) by converting the 3 remaining ORM-dependent steam tasks to use the internal HTTP API.

## Architecture

```
┌─────────────┐     ┌───────┐     ┌──────────────────┐     ┌────────────┐
│ Celery Beat │────▶│ Redis │◀────│ Celery Worker(s) │────▶│ Steam API  │
│ (static     │     │Broker │     │ (no DB, off-host)│     └────────────┘
│  schedule)  │     └───────┘     │                  │
└─────────────┘                   │  internal HTTP   │
                                  │       ▼          │
                                  │ ┌────────────┐   │
                                  └─│  Backend   │───┘
                                    │ (Django +  │
                                    │  SQLite)   │
                                    └────────────┘
```

- **Beat**: Static schedule defined in code. No DB. No `django-celery-beat`. Fires tasks to Redis.
- **Workers**: Stateless. No `DATABASES`. Call Steam API for fetches, call backend internal API for DB reads/writes. Can run off-host with only broker + backend URL access.
- **Backend (Daphne)**: Sole owner of the database. Exposes internal HTTP endpoints for workers to read/write state.

## Current State

### Tasks by DB dependency

| Module | Count | Uses DB? | Method |
|--------|-------|----------|--------|
| `events/tasks.py` | 12 | No | `internal_client` HTTP |
| `events/tournament_tasks.py` | 3 | No | `internal_client` HTTP |
| `discordbot/tasks.py` | 1 | No | `internal_client` HTTP |
| `app/tasks/avatar_refresh.py` | 3 | No | `internal_client` HTTP |
| `steam/tasks.py` | 3 | **Yes** | Direct ORM |

### Steam tasks that need migration

1. **`sync_league_matches_task`** — Fetches matches from Steam API, stores Match + PlayerMatchStats in DB, links users via steamid
2. **`update_league_stats_task`** — Aggregates PlayerMatchStats into LeaguePlayerStats per user
3. **`recalculate_user_league_mmr_task`** — Recalculates a single user's league MMR

## Design

### New Internal API Endpoints

All endpoints authenticated via `X-Internal-Token` header (existing `InternalServiceAuth`).

#### 1. `GET /api/internal/steam/sync-state/<int:league_id>/`

Returns the LeagueSyncState for a league (creates if missing).

**Response:**
```json
{
  "league_id": 17929,
  "last_match_seq_num": 123456,
  "is_syncing": false,
  "failed_match_ids": [789, 790]
}
```

#### 2. `PATCH /api/internal/steam/sync-state/<int:league_id>/`

Updates sync state fields (is_syncing, last_match_seq_num, failed_match_ids, etc).

**Request body:**
```json
{
  "is_syncing": true,
  "last_match_seq_num": 123457,
  "failed_match_ids": []
}
```

#### 3. `POST /api/internal/steam/store-match/`

Receives raw match data from Steam API, creates/updates Match + PlayerMatchStats, links users.

**Request body:**
```json
{
  "match_id": 8000000001,
  "league_id": 17929,
  "radiant_win": true,
  "duration": 2400,
  "start_time": 1713600000,
  "game_mode": 2,
  "lobby_type": 1,
  "players": [
    {
      "account_id": 12345678,
      "player_slot": 0,
      "hero_id": 1,
      "kills": 10,
      "deaths": 3,
      "assists": 15,
      "gold_per_min": 550,
      "xp_per_min": 600,
      "last_hits": 200,
      "denies": 10,
      "hero_damage": 25000,
      "tower_damage": 3000,
      "hero_healing": 0
    }
  ]
}
```

**Response:**
```json
{
  "match_id": 8000000001,
  "created": true,
  "players_stored": 10,
  "players_linked": 7
}
```

#### 4. `POST /api/internal/steam/update-league-stats/<int:league_id>/`

Triggers full stats recalculation for all users in the league. Runs the existing `update_all_league_stats_for_league` logic on the backend side.

**Response:**
```json
{
  "updated_count": 42
}
```

#### 5. `POST /api/internal/steam/recalculate-mmr/<int:user_id>/`

Recalculates a single user's league MMR.

**Response:**
```json
{
  "user_id": 5,
  "new_mmr": 3250
}
```

### Refactored Steam Tasks

After migration, `steam/tasks.py` will:

1. **`sync_league_matches_task`**:
   - `GET sync-state` → check if already syncing
   - `PATCH sync-state` → set is_syncing=true
   - Call Steam API (I/O) → fetch match list
   - For each match: call Steam API for details → `POST store-match`
   - `PATCH sync-state` → set is_syncing=false, update last_match_seq_num
   - If new matches synced → `update_league_stats_task.delay()`

2. **`update_league_stats_task`**:
   - `POST update-league-stats/<league_id>/` → done

3. **`recalculate_user_league_mmr_task`**:
   - `POST recalculate-mmr/<user_id>/` → done

### Settings Changes

#### `config/settings_celery.py` (final state)

```python
"""Minimal Django settings for Celery workers. No ORM, no DB."""
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = "celery-worker-not-serving-http"
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "config", "app", "events", "discordbot", "steam",
]
DATABASES = {}  # No DB — all tasks use internal HTTP API
CELERY_BROKER_URL = ...
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
AUTH_USER_MODEL = "app.CustomUser"
```

#### Docker Compose (prod) — celery-worker

```yaml
celery-worker:
  image: ghcr.io/kettleofketchup/draftforge/backend:latest
  entrypoint: ["celery"]
  command: ["-A", "config.celery_light", "worker", "-l", "info", "--pool=solo"]
  environment:
    DJANGO_SETTINGS_MODULE: config.settings_celery
  volumes:
    - ./backend/.env:/app/backend/.env
  # NO database volume — workers are DB-free
```

#### Docker Compose (prod) — celery-beat

```yaml
celery-beat:
  image: ghcr.io/kettleofketchup/draftforge/backend:latest
  entrypoint: ["celery"]
  command: ["-A", "config.celery_light", "beat", "-l", "info"]
  environment:
    DJANGO_SETTINGS_MODULE: config.settings_celery
  volumes:
    - ./backend/.env:/app/backend/.env
  # NO database volume — static schedule, no DatabaseScheduler
```

### Migration Path

1. Add new internal API endpoints (backend views + URL routing)
2. Add `internal_client.py` functions for the new endpoints
3. Rewrite `steam/tasks.py` to use `internal_client` instead of ORM
4. Remove `DATABASES` from `settings_celery.py`
5. Remove sqlite volume mount from celery-worker in all compose files
6. Test: run `sync_league_matches_task` manually, verify it calls backend and stores data
7. Deploy

### What Stays The Same

- Beat schedule defined in `config/celery_light.py` (static, code-defined)
- Redis as broker (unchanged)
- All existing event/discord/avatar tasks (already HTTP-only)
- `internal_client.py` patterns (same auth, same `_get`/`_post` helpers)
- Backend internal auth (`InternalServiceAuth` + IP allowlist)

### Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Backend downtime = workers can't write | Workers already handle this — `internal_client` returns None, task retries with backoff |
| Steam API rate limits during store-match loop | Existing `retry_with_backoff` in steam utils. Store-match is local HTTP (fast) |
| SQLite write contention from store-match bursts | Backend already uses `transaction_mode: IMMEDIATE` + 30s timeout. Store-match is one match at a time |
| Large match payloads | Steam matches are ~5KB JSON max. Well within POST limits |

### Future Optimization (Not In Scope)

- Switch workers to gevent pool for higher I/O concurrency
- Run workers on separate VMs/k8s pods (off-host)
- Add result backend for task status tracking
- Queue routing: separate `steam` queue for rate-limit-aware workers
