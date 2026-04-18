# Celery RAM Optimization (Phase 1-3) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce RAM usage on the 2GB production server by ~250 MiB by merging celery-beat into the worker, migrating the last ORM-dependent task to internal HTTP API, and running a lightweight celery worker that doesn't load the full Django app.

**Architecture:** Currently 4 Python processes (Daphne, celery-worker, celery-beat, discord-bot) each load the full Django stack (~130-210 MiB each). Phase 1 eliminates celery-beat as a separate container by embedding it in the worker (`-B` flag). Phase 2 migrates `generate_upcoming_events()` from direct ORM to internal HTTP API, removing the last Django ORM dependency from celery tasks. Phase 3 creates a lightweight celery configuration that only needs `requests` + `celery` (no Django ORM), cutting worker memory from ~200 MiB to ~50 MiB.

**Tech Stack:** Celery 5.3, Django 5.2, Docker Compose, Redis

---

## Phase 1: Merge celery-beat into celery-worker

### Task 1: Update Docker Compose files to embed beat in worker

The celery-beat container uses 145 MiB just to run the scheduler. Celery supports embedding beat inside the worker with the `-B` flag. Since we already run `max-concurrency: 1`, there's no risk of beat interfering with task execution.

**Files:**
- Modify: `docker/docker-compose.debug.yaml` — remove `celery-beat` service, add `-B` to worker command
- Modify: `docker/docker-compose.prod.yaml` — same
- Modify: `docker/docker-compose.release.yaml` — same
- Modify: `docker/docker-compose.test.yaml` — same
- Modify: `docker/docker-compose.ci.yaml` — same
- Modify: `docker/docker-compose.debug.m1.yaml` — same

**Step 1: Update all compose files**

In every compose file listed above, make these two changes:

1. In the `celery-worker` service, change `command` to include `-B` and `--pool=solo`:

```yaml
  celery-worker:
    # ... (keep image, env_file, volumes, depends_on, restart, etc.)
    entrypoint: ["celery"]
    command: ["-A", "config", "worker", "-B", "-l", "info", "--pool=solo"]
```

The `--pool=solo` flag replaces the prefork pool (which spawns a child process) with an in-process executor. Since we already run at `max-concurrency: 1`, this is equivalent but saves ~20 MiB of fork overhead.

2. Remove the entire `celery-beat` service block from each file.

For test/ci compose files that have `networks:` on celery-beat, just remove the whole service.

**Step 2: Verify locally**

```bash
just dev::debug
# Watch logs — beat schedule should appear in celery-worker output:
# "beat: Starting..."
# "Scheduler: Sending due task ..."
```

Expected: celery-worker logs show both worker AND beat messages. No separate celery-beat container.

**Step 3: Commit**

```bash
git add docker/
git commit -m "perf: merge celery-beat into celery-worker with -B flag

Eliminates the celery-beat container (~145 MiB) by embedding the beat
scheduler into the worker process. Also switches to solo pool since
we already run at max-concurrency=1, saving fork overhead."
```

---

## Phase 2: Migrate `generate_upcoming_events` to internal HTTP API

This is the only Celery task that still imports Django ORM directly. It needs two new internal API endpoints:
1. `GET /api/internal/repeaters/active/` — list active repeaters with config
2. `POST /api/internal/repeaters/<pk>/generate/` — generate events for a repeater (calls `generate_events_for_repeater()` on the Django side)

### Task 2: Add internal API endpoint to list active repeaters

**Files:**
- Modify: `backend/app/views/internal.py`
- Modify: `backend/backend/urls.py`

**Step 1: Write the failing test**

Create test in `backend/app/tests/test_internal_endpoints.py` (append to existing file):

```python
def test_get_active_repeaters(self):
    """GET /api/internal/repeaters/active/ returns active repeaters."""
    from events.models import EventRepeater

    repeater = EventRepeater.objects.create(
        organization=self.org,
        name="Weekly Inhouse",
        is_active=True,
        frequency="weekly",
        day_of_week=3,
        time_of_day="20:00:00",
        starts_at="2026-01-01",
        generate_days_ahead=7,
        created_by=self.admin,
    )
    # Also create an inactive one to make sure it's excluded
    EventRepeater.objects.create(
        organization=self.org,
        name="Inactive",
        is_active=False,
        frequency="weekly",
        day_of_week=5,
        time_of_day="20:00:00",
        starts_at="2026-01-01",
        generate_days_ahead=7,
        created_by=self.admin,
    )

    resp = self.client.get("/api/internal/repeaters/active/")
    self.assertEqual(resp.status_code, 200)
    data = resp.json()
    self.assertEqual(len(data), 1)
    self.assertEqual(data[0]["name"], "Weekly Inhouse")
    self.assertIn("pk", data[0])
    self.assertIn("organization_id", data[0])
```

**Step 2: Run test to verify it fails**

```bash
just test::run 'python manage.py test app.tests.test_internal_endpoints.InternalEndpointTest.test_get_active_repeaters -v 2'
```

Expected: 404 (endpoint doesn't exist yet)

**Step 3: Implement the endpoint**

Add to `backend/app/views/internal.py`:

```python
@api_view(["GET"])
@authentication_classes(_auth)
@permission_classes(_perm)
def get_active_repeaters(request):
    """List active repeaters for event generation task."""
    from events.models import EventRepeater

    repeaters = EventRepeater.objects.filter(is_active=True).select_related(
        "organization", "tournament_league", "created_by"
    )
    data = []
    for r in repeaters:
        data.append({
            "pk": r.pk,
            "name": r.name,
            "organization_id": r.organization_id,
        })
    return Response(data)
```

Add URL to `backend/backend/urls.py` (in the internal API section):

```python
path("api/internal/repeaters/active/", get_active_repeaters, name="internal_active_repeaters"),
```

**Step 4: Run test to verify it passes**

```bash
just test::run 'python manage.py test app.tests.test_internal_endpoints.InternalEndpointTest.test_get_active_repeaters -v 2'
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/views/internal.py backend/backend/urls.py backend/app/tests/test_internal_endpoints.py
git commit -m "feat: add GET /api/internal/repeaters/active/ endpoint"
```

### Task 3: Add internal API endpoint to generate events for a repeater

**Files:**
- Modify: `backend/app/views/internal.py`
- Modify: `backend/backend/urls.py`

**Step 1: Write the failing test**

Append to `backend/app/tests/test_internal_endpoints.py`:

```python
def test_generate_events_for_repeater(self):
    """POST /api/internal/repeaters/<pk>/generate/ creates events."""
    import datetime
    from events.models import Event, EventRepeater

    repeater = EventRepeater.objects.create(
        organization=self.org,
        name="Generate Test",
        is_active=True,
        frequency="daily",
        time_of_day="20:00:00",
        starts_at=datetime.date.today(),
        generate_days_ahead=3,
        created_by=self.admin,
    )
    resp = self.client.post(f"/api/internal/repeaters/{repeater.pk}/generate/")
    self.assertEqual(resp.status_code, 200)
    data = resp.json()
    self.assertIn("created_count", data)
    self.assertGreaterEqual(data["created_count"], 0)
    # Verify events were actually created
    events = Event.objects.filter(event_repeater=repeater)
    self.assertEqual(events.count(), data["created_count"])
```

**Step 2: Run test to verify it fails**

```bash
just test::run 'python manage.py test app.tests.test_internal_endpoints.InternalEndpointTest.test_generate_events_for_repeater -v 2'
```

Expected: 404

**Step 3: Implement the endpoint**

Add to `backend/app/views/internal.py`:

```python
@api_view(["POST"])
@authentication_classes(_auth)
@permission_classes(_perm)
def generate_repeater_events(request, repeater_id):
    """Generate upcoming events for a specific repeater."""
    from events.models import EventRepeater
    from events.services import generate_events_for_repeater

    try:
        repeater = EventRepeater.objects.select_related(
            "organization", "tournament_league", "created_by"
        ).get(pk=repeater_id)
    except EventRepeater.DoesNotExist:
        return Response({"error": "Repeater not found"}, status=404)

    try:
        events = generate_events_for_repeater(repeater)
        return Response({"created_count": len(events)})
    except Exception as e:
        logger.exception("Failed to generate events for repeater %s", repeater_id)
        return Response({"error": str(e)}, status=500)
```

Add URL:

```python
path("api/internal/repeaters/<int:repeater_id>/generate/", generate_repeater_events, name="internal_generate_repeater_events"),
```

**Step 4: Run test to verify it passes**

```bash
just test::run 'python manage.py test app.tests.test_internal_endpoints.InternalEndpointTest.test_generate_events_for_repeater -v 2'
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/views/internal.py backend/backend/urls.py backend/app/tests/test_internal_endpoints.py
git commit -m "feat: add POST /api/internal/repeaters/<pk>/generate/ endpoint"
```

### Task 4: Add internal client functions and migrate the task

**Files:**
- Modify: `backend/app/internal_client.py` — add `get_active_repeaters()` and `generate_repeater_events()`
- Modify: `backend/events/tasks.py` — rewrite `generate_upcoming_events()` to use HTTP

**Step 1: Add client functions**

Append to `backend/app/internal_client.py`:

```python
# ---- Repeater / event generation ----

def get_active_repeaters():
    """Get all active repeaters."""
    resp = _get("/repeaters/active/")
    if resp and resp.ok:
        return resp.json()
    return []


def generate_repeater_events(repeater_pk):
    """Trigger event generation for a specific repeater. Returns created count."""
    resp = _post(f"/repeaters/{repeater_pk}/generate/", {})
    if resp and resp.ok:
        return resp.json().get("created_count", 0)
    return 0
```

**Step 2: Rewrite the task**

Replace `generate_upcoming_events()` in `backend/events/tasks.py`:

```python
@shared_task
def generate_upcoming_events():
    """Generate upcoming events for all active repeaters. Runs hourly.

    Calls internal API — no direct ORM access.
    """
    from app.internal_client import get_active_repeaters, generate_repeater_events

    repeaters = get_active_repeaters()
    total = 0
    for repeater in repeaters:
        try:
            count = generate_repeater_events(repeater["pk"])
            total += count
        except Exception:
            logger.exception("Failed to generate events for repeater %s", repeater["pk"])
    return f"Generated {total} events from {len(repeaters)} repeaters"
```

Also remove the now-unused import at the top of the file:

```python
# REMOVE this line:
from events.services import generate_events_for_repeater
```

**Step 3: Run all events tests**

```bash
just test::run 'python manage.py test events.tests -v 2'
just test::run 'python manage.py test app.tests.test_internal_endpoints -v 2'
```

Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/internal_client.py backend/events/tasks.py
git commit -m "refactor: migrate generate_upcoming_events to internal HTTP API

Last Celery task using direct ORM now calls internal API endpoints.
All Celery tasks are now pure HTTP clients — no Django ORM imports."
```

---

## Phase 3: Lightweight Celery configuration (no Django ORM)

Now that all tasks use HTTP, the celery worker no longer needs Django's ORM, middleware, auth, templates, or any other Django subsystem. We create a minimal settings module that only configures Celery + Redis.

### Task 5: Create lightweight celery settings

**Files:**
- Create: `backend/config/settings_celery.py` — minimal settings for celery-only workers
- Create: `backend/config/celery_light.py` — celery app that uses lightweight settings

**Step 1: Create minimal settings**

Create `backend/config/settings_celery.py`:

```python
"""Minimal Django settings for lightweight Celery workers.

This loads just enough Django to register tasks and connect to Redis.
No ORM, no middleware, no templates, no auth — tasks communicate with
Django/Daphne over HTTP via internal_client.py.
"""

import os

# Required for Django to initialize (even in minimal mode)
SECRET_KEY = "celery-worker-not-serving-http"
DEBUG = False
ALLOWED_HOSTS = []

# Minimal installed apps — only what's needed for task autodiscovery
INSTALLED_APPS = [
    "config",
    "app",
    "events",
    "discordbot",
]

# No database — workers don't touch the DB
DATABASES = {}

# Celery configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", f"redis://{REDIS_HOST}:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True

# Internal API token — used by internal_client.py via os.environ, not settings
# (internal_client reads INTERNAL_SERVICE_TOKEN from env directly when
#  settings is not fully loaded)
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
```

**Step 2: Create lightweight celery app**

Create `backend/config/celery_light.py`:

```python
"""Lightweight Celery app that doesn't load the full Django stack.

Uses config.settings_celery instead of backend.settings.
This cuts worker memory from ~200 MiB to ~50 MiB.
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_celery")

# Initialize Django with minimal settings before creating the Celery app
import django
django.setup()

app = Celery("dtx")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.autodiscover_tasks(["events"], related_name="tournament_tasks")

# Beat schedule — identical to config/celery.py
_beat_schedule = {
    "sync-league-matches-every-minute": {
        "task": "steam.tasks.sync_league_matches_task",
        "schedule": 60.0,
    },
    "check-discord-scheduled-events": {
        "task": "discordbot.tasks.check_scheduled_events",
        "schedule": 60.0,
    },
    "refresh-discord-avatars": {
        "task": "app.tasks.avatar_refresh.refresh_discord_avatars",
        "schedule": 300.0,
        "kwargs": {"batch_size": 50},
    },
    "refresh-all-discord-data-daily": {
        "task": "app.tasks.avatar_refresh.refresh_all_discord_data",
        "schedule": crontab(hour=4, minute=0),
    },
    "generate-upcoming-events-hourly": {
        "task": "events.tasks.generate_upcoming_events",
        "schedule": 3600.0,
    },
    "open-scheduled-signups-every-minute": {
        "task": "events.tasks.open_scheduled_signups",
        "schedule": 60.0,
    },
    "check-event-reminders": {
        "task": "events.tasks.check_event_reminders",
        "schedule": 30.0,
    },
    "sync-discord-events": {
        "task": "events.tasks.sync_discord_events",
        "schedule": 60.0,
    },
    "cleanup-stale-events-hourly": {
        "task": "events.tasks.cleanup_stale_events",
        "schedule": 3600.0,
    },
}

app.conf.beat_schedule = _beat_schedule
```

**Step 3: Commit skeleton**

```bash
git add backend/config/settings_celery.py backend/config/celery_light.py
git commit -m "feat: add lightweight celery config without Django ORM"
```

### Task 6: Remove Django ORM dependency from internal_client.py

The `internal_client.py` currently imports `from django.conf import settings` to read `INTERNAL_SERVICE_TOKEN`. This forces the full Django settings to load. Change it to read from `os.environ` directly.

**Files:**
- Modify: `backend/app/internal_client.py`

**Step 1: Replace the django.conf import**

Change `backend/app/internal_client.py`:

```python
# BEFORE (line 16):
from django.conf import settings

# AFTER:
# No django import needed
```

And update the `_headers()` function:

```python
# BEFORE:
def _headers():
    return {
        "X-Internal-Token": getattr(settings, "INTERNAL_SERVICE_TOKEN", ""),
        "Content-Type": "application/json",
    }

# AFTER:
def _headers():
    return {
        "X-Internal-Token": os.environ.get("INTERNAL_SERVICE_TOKEN", ""),
        "Content-Type": "application/json",
    }
```

**Step 2: Run internal client tests**

```bash
just test::run 'python manage.py test app.tests.test_internal_client -v 2'
just test::run 'python manage.py test app.tests.test_internal_endpoints -v 2'
```

Expected: All pass (env var is set in .env files which Docker loads)

**Step 3: Commit**

```bash
git add backend/app/internal_client.py
git commit -m "refactor: read INTERNAL_SERVICE_TOKEN from env instead of django.conf

Removes the last django.conf import from internal_client.py so it
can be used by lightweight celery workers without loading full Django."
```

### Task 7: Verify task modules don't import Django ORM at module level

All task modules must only import Django/ORM inside function bodies (lazy imports), never at module level. Check and fix any violations.

**Files:**
- Check: `backend/events/tasks.py`
- Check: `backend/events/tournament_tasks.py`
- Check: `backend/discordbot/tasks.py`
- Check: `backend/app/tasks/avatar_refresh.py`
- Check: `backend/app/tasks/herodraft_tick.py`

**Step 1: Audit imports**

Search all task files for top-level Django/ORM imports:

```bash
grep -n "^from django\|^import django\|^from app\.models\|^from events\.models\|^from discordbot\.models\|^from org\.models" \
    backend/events/tasks.py \
    backend/events/tournament_tasks.py \
    backend/discordbot/tasks.py \
    backend/app/tasks/avatar_refresh.py \
    backend/app/tasks/herodraft_tick.py
```

For each match found at module level (not inside a function), move it inside the function that uses it. The pattern:

```python
# BEFORE (module level):
from django.utils import timezone

@shared_task
def my_task():
    now = timezone.now()

# AFTER (lazy import):
@shared_task
def my_task():
    from django.utils import timezone
    now = timezone.now()
```

**Exception:** `from celery import shared_task` and `from app.internal_client import ...` are fine — these don't load Django ORM.

**Note on `django.utils.timezone`:** This import triggers Django setup. Replace with `datetime.datetime.now(datetime.timezone.utc)` or move to lazy import inside each task function.

**Step 2: Verify no module-level Django imports remain**

```bash
grep -rn "^from django\|^import django\|^from app\.models\|^from events\.models" \
    backend/events/tasks.py \
    backend/events/tournament_tasks.py \
    backend/discordbot/tasks.py \
    backend/app/tasks/avatar_refresh.py \
    backend/app/tasks/herodraft_tick.py
```

Expected: No matches (all moved inside functions)

**Step 3: Run full test suite**

```bash
just test::run 'python manage.py test app.tests events.tests discordbot.tests -v 2'
```

Expected: All pass

**Step 4: Commit**

```bash
git add backend/events/tasks.py backend/events/tournament_tasks.py backend/discordbot/tasks.py backend/app/tasks/
git commit -m "refactor: move all Django imports in task files to lazy imports

Task modules no longer import Django at module level, allowing them
to be loaded by the lightweight celery config without full Django setup."
```

### Task 8: Update Docker Compose files to use lightweight celery config

**Files:**
- Modify: `docker/docker-compose.debug.yaml`
- Modify: `docker/docker-compose.prod.yaml`
- Modify: `docker/docker-compose.release.yaml`
- Modify: `docker/docker-compose.test.yaml`
- Modify: `docker/docker-compose.ci.yaml`
- Modify: `docker/docker-compose.debug.m1.yaml`

**Step 1: Update celery-worker command in all compose files**

Change from:

```yaml
  celery-worker:
    entrypoint: ["celery"]
    command: ["-A", "config", "worker", "-B", "-l", "info", "--pool=solo"]
```

To:

```yaml
  celery-worker:
    entrypoint: ["celery"]
    command: ["-A", "config.celery_light", "worker", "-B", "-l", "info", "--pool=solo"]
```

The only change is `config` → `config.celery_light` in the `-A` argument.

**Step 2: Test locally**

```bash
just dev::debug
# Watch celery-worker logs — should start without errors
# Verify beat schedule loads
# Trigger a task manually and confirm it executes
```

**Step 3: Run Playwright tests to verify end-to-end**

```bash
just test::pw::headless
```

Expected: All pass — tasks still work, just with less memory

**Step 4: Commit**

```bash
git add docker/
git commit -m "perf: switch celery-worker to lightweight config (no Django ORM)

Worker now uses config.celery_light which loads minimal Django settings.
Expected memory savings: ~150 MiB (from ~200 MiB to ~50 MiB)."
```

### Task 9: Final verification and cleanup

**Step 1: Check memory usage locally**

```bash
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}'
```

Compare celery-worker memory before and after. Expected: ~50 MiB vs previous ~200 MiB.

**Step 2: Remove db.sqlite3 volume mount from celery-worker in prod/release**

Since the worker no longer uses Django ORM, it doesn't need the SQLite database file mounted.

In `docker-compose.prod.yaml` and `docker-compose.release.yaml`, remove from celery-worker:

```yaml
    volumes:
      - ./backend/db.sqlite3:/app/backend/prod.db.sqlite3
      - ./backend/.env:/app/backend/.env
```

Keep only:

```yaml
    volumes:
      - ./backend/.env:/app/backend/.env
```

The `.env` file is still needed for `INTERNAL_SERVICE_TOKEN` and other env vars.

**Step 3: Final commit**

```bash
git add docker/
git commit -m "chore: remove unnecessary db.sqlite3 mount from celery-worker

Worker no longer accesses the database directly — all data flows
through internal HTTP API to the Django/Daphne backend."
```

---

## Summary

| Phase | Task | Memory Saved | Risk |
|-------|------|-------------|------|
| 1 | Merge beat into worker + solo pool | ~145 MiB | Low — well-supported Celery feature |
| 2 | Migrate `generate_upcoming_events` to HTTP | Unblocks Phase 3 | Low — follows existing pattern |
| 3 | Lightweight celery config | ~100 MiB | Medium — needs thorough testing of lazy imports |
| **Total** | | **~245 MiB** | |

Production memory: 1.3 GiB → ~1.05 GiB (available: 626 MiB → ~870 MiB)
