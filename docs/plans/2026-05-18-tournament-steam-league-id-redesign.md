# Plan: Remove `Tournament.steam_league_id`, source from `League` only

**Date:** 2026-05-18
**Status:** Proposed
**Related PRs:** #234 (in flight — adds `Tournament.linked_steam_league_id` property), #230 (periodic sync iterates leagues)

## Problem

Two independent fields carry "the Steam league id for this tournament":

| Field | Location | Purpose |
|---|---|---|
| `Tournament.steam_league_id` | `backend/app/models.py:520` (`db_column="league_id"`) | Legacy per-tournament id |
| `League.steam_league_id` | `backend/app/models.py:385` | Per-league id (the obvious source of truth) |

`Tournament.league` (FK) was added later and `Tournament.steam_league_id` was kept as a backwards-compat column rename (note the `db_column="league_id"` — the underlying DB column predates the FK and was repurposed).

Symptoms this causes today:

1. Editing the League page sets `League.steam_league_id` but leaves `Tournament.steam_league_id` stale, so any code reading the tournament field returns the old id. This is the bug #234 fixes via the `linked_steam_league_id` property.
2. Schema lies: it implies tournaments can override the league's Steam id. In practice nothing in the codebase intentionally uses an override; the field is just legacy column inertia.
3. Two places to keep in sync; tests have to set both; admins have to think about which one wins.

## Goal

After this work, **`Tournament.steam_league_id` is gone**. Every Steam-league lookup for a tournament goes through `Tournament.league.steam_league_id`, accessed via `Tournament.linked_steam_league_id`.

## Out of scope

- `Event.lobby_steam_league_id` (`backend/app/models.py:560`) — different concept (Dota lobby ticket id, not match-history league id). Leave it.
- `League.steam_league_id` itself — keep, it's the canonical field.

## Pre-flight audit

Before writing migrations, run these greps to inventory every reader/writer of `Tournament.steam_league_id`:

```bash
rg -n "tournament\.steam_league_id|Tournament\.steam_league_id" backend/ frontend/ --type-not migration
rg -n "steam_league_id" backend/tests/populate/ backend/steam/tests/ backend/app/tests/
rg -n "steam_league_id" backend/app/serializers.py backend/app/views_main.py backend/app/views/
rg -n "steam_league_id" frontend/
```

Expected findings (from current main):

- **Backend readers** — `steam/services/match_suggestions.py:62`, `steam/functions/game_linking.py:369`. Both already migrated to `linked_steam_league_id` in #234.
- **Backend writers** — admin/edit-tournament views (need to confirm; if any UI exposes the field, it has to be removed).
- **Serializers** — `app/serializers.py` likely exposes `steam_league_id` on the Tournament serializer; needs to be dropped or aliased to `linked_steam_league_id` (read-only).
- **Frontend** — tournament edit form. May have a "Steam League ID" input bound to the tournament; needs to be removed (or moved to the League edit page if it isn't already there).
- **Test fixtures** — `backend/tests/populate/tournaments.py` calls `steam_league_id=DTX_STEAM_LEAGUE_ID` on Tournament creation; update to set the field on the parent League instead and remove from Tournament setup.
- **Migrations** — historical migrations reference the column (`0093_alter_tournament_steam_league_id.py`, `0094_alter_league_steam_league_id.py`). Untouched; we add a new migration on top.

## Steps

### Step 1 — Audit + freeze readers (single PR, separate from this one)

Already done by #234 for `match_suggestions.py` and `game_linking.py`. Run the greps above on the post-#234 main to confirm zero readers remain on `tournament.steam_league_id`. If any survive, migrate them to `linked_steam_league_id` before proceeding.

**Gate:** `rg -n "tournament\.steam_league_id" backend/ --type py | grep -v migrations | grep -v models.py` returns empty (the model definition itself and migrations are the only remaining references).

### Step 2 — Backfill (migration + data check)

Add a data migration that, for every Tournament row where `steam_league_id` is set AND differs from `league.steam_league_id`, surfaces a warning:

```python
# 0095_audit_orphan_tournament_steam_league_ids.py
from django.db import migrations

def audit(apps, schema_editor):
    Tournament = apps.get_model("app", "Tournament")
    mismatches = []
    for t in Tournament.objects.exclude(steam_league_id__isnull=True).select_related("league"):
        league_id = t.league.steam_league_id if t.league else None
        if t.steam_league_id != league_id:
            mismatches.append((t.pk, t.steam_league_id, league_id))
    if mismatches:
        # Log to stdout; admin reviews before the next migration drops the column.
        print(f"WARN: {len(mismatches)} tournaments have steam_league_id != league.steam_league_id")
        for pk, t_id, l_id in mismatches[:20]:
            print(f"  tournament={pk} tournament_steam_id={t_id} league_steam_id={l_id}")

class Migration(migrations.Migration):
    dependencies = [("app", "0094_alter_league_steam_league_id")]
    operations = [migrations.RunPython(audit, migrations.RunPython.noop)]
```

**Gate:** admin runs `manage.py migrate` against a prod-shaped DB and reviews any mismatch warnings. For each mismatch, decide:

- (a) tournament's id is right → set `league.steam_league_id` to it and null the tournament's id.
- (b) league's id is right → null the tournament's id.
- (c) ambiguous → ask the league admin.

This is a manual gate. Don't proceed to step 3 until it's clean.

### Step 3 — Drop the column

Generate `0096_remove_tournament_steam_league_id.py` via `makemigrations` after removing the field from `Tournament`:

```python
# In app/models.py — delete these lines:
# steam_league_id = models.IntegerField(
#     null=True, blank=True, default=None,
#     help_text="Steam league ID for match linking",
#     db_column="league_id",
# )
```

In the same PR:

- Drop `steam_league_id` from `TournamentSerializer` and any related serializer.
- Remove the field from any tournament create/edit form (frontend).
- Update populate fixtures to set `league.steam_league_id` only.
- Drop tests that specifically assert on `Tournament.steam_league_id` (the `linked_steam_league_id` tests stay).

**Gate:** full backend test suite + Playwright tournament-edit specs green.

### Step 4 — Rename the column back (optional)

The DB column is currently `league_id` (legacy) on the Tournament table. The FK column is `league_fk_id`. With `Tournament.steam_league_id` gone, the legacy `league_id` column is empty and orphaned. Optionally rename `league_fk_id` → `league_id` for cleanliness:

```python
# 0097_rename_league_fk_id_to_league_id.py
operations = [migrations.AlterField(
    model_name="tournament", name="league",
    field=models.ForeignKey(... db_column="league_id" ...),
)]
```

This is purely cosmetic. Skip unless someone cares.

## Risks

- **Hidden override use** — if any tournament actually used `steam_league_id` to point at a different Steam league than its parent League (e.g. a multi-league grand finals tournament), Step 2's audit catches it and forces a human decision. Without the audit, we'd silently break those rows.
- **Frontend cache** — if the tournament edit form still ships `steam_league_id` in its payload, the API needs to either accept-and-ignore it or 400. Choose accept-and-ignore to avoid breaking older clients during rollout.
- **Migration runtime** — the audit is O(n) over tournaments; only matters at very large scale. For DraftForge today, trivial.

## What about Tournament.game_type?

Tangentially raised — confirmed: `Tournament.game_type` exists (`app/models.py:536`) and uses the shared `GameType` integer choices (`DOTA2=1`, `DEADLOCK=2`). It is **not** in scope for this redesign — Steam league ids are Dota-specific, so the implicit assumption is that `linked_steam_league_id` is meaningful only when `tournament.game_type == GameType.DOTA2`. If Deadlock (or future games) ever grows its own league concept, the property name can stay generic (it returns `None` when no league is linked, which is the right behavior for non-Dota tournaments).
