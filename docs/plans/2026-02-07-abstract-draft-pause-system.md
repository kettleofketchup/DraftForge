# Abstract Draft Pause & Timer System

**Date**: 2026-02-07
**Branch**: `feature/abstract-draft-pause` (from `feature/admin-team-modal`)
**Related Issues**: #110 (Abstract PauseEvent), #133 (Auction Draft), #134 (Team Draft Timers)

## Summary

Unify the herodraft and team draft systems by extracting a shared tick service, abstract pause model, and tournament config. The only difference between draft types is the timeout action (pick hero vs pick player vs close bid). Everything else — timers, pause/resume, heartbeats, connection tracking — is shared infrastructure.

## Design

### 1. Shared Tick Service

Extract the herodraft tick loop (`herodraft_tick.py`) into a generic `DraftTickService` base class. The tick loop runs every 1 second and performs 5 steps:

1. Check resume countdown (RESUMING → DRAFTING)
2. Check captain heartbeats (detect stale connections)
3. Broadcast tick (timing data to WebSocket clients)
4. Check timeout (delegate to subclass)
5. Extend distributed lock

Steps 1, 2, 3, and 5 are identical across all draft types. Only step 4 varies.

```python
# backend/app/tasks/draft_tick.py

class DraftTickService:
    """Generic tick loop for any timed draft."""

    LOCK_KEY = "draft:tick_lock:{draft_type}:{draft_id}"
    CONN_KEY = "draft:connections:{draft_type}:{draft_id}"
    HEARTBEAT_KEY = "draft:{draft_type}:{draft_id}:captain:{user_id}:heartbeat"

    def __init__(self, draft_type: str, draft_id: int):
        self.draft_type = draft_type  # "herodraft", "teamdraft", "auction"
        self.draft_id = draft_id

    # Subclasses implement these:
    async def get_draft(self): ...
    async def get_active_round(self): ...
    async def get_active_team(self): ...
    async def on_timeout(self, draft, round, team): ...
    async def broadcast_tick_data(self, draft, round, team): ...

    # Shared tick loop (extracted from herodraft_tick.py):
    async def run_tick_loop(self, stop_event):
        while not stop_event.is_set():
            should_continue, reason = await self.check_continue()
            if not should_continue:
                break
            await self.check_resume_countdown()
            await self.check_captain_heartbeats()
            await self.broadcast_tick()
            await self.check_timeout()
            await self.extend_lock()
            await asyncio.sleep(1)
```

Concrete subclasses:

- **`HeroDraftTickService`**: `on_timeout()` auto-picks a random hero. Refactored from existing `herodraft_tick.py`.
- **`TeamDraftTickService`**: `on_timeout()` picks a random available player (reads `pick_timeout_strategy` from `TournamentConfig`).
- **Future `AuctionTickService`**: `on_timeout()` closes the current bid round.

### 2. Abstract PauseEvent Model

Audit trail for all pause/resume events, replacing the fragile `started_at` adjustment pattern.

```python
# backend/app/models.py

class PauseEvent(models.Model):
    """Abstract audit trail for pause/resume events."""

    PAUSE_TYPE_CHOICES = [
        ("disconnect", "Captain Disconnected"),
        ("manual", "Manual Pause"),
        ("timeout", "Timeout"),
    ]

    pause_type = models.CharField(max_length=16, choices=PAUSE_TYPE_CHOICES)
    paused_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    paused_at = models.DateTimeField()
    resumed_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")

    class Meta:
        abstract = True

    @property
    def duration(self):
        if self.resumed_at:
            return self.resumed_at - self.paused_at
        return None
```

Concrete models:

- **`HeroDraftPauseEvent(PauseEvent)`**: FK to `HeroDraft`
- **`TeamDraftPauseEvent(PauseEvent)`**: FK to `Draft`

**Time calculation change**: Instead of adjusting `started_at` on resume, the tick service calculates elapsed active time by subtracting total paused duration from wall-clock elapsed time:

```python
total_paused = sum(
    (pe.duration for pe in pause_events if pe.duration),
    timedelta()
)
active_elapsed = (now - round.started_at) - total_paused
```

### 3. Pause State on Draft Models

Both `HeroDraft` and `Draft` models get the same pause fields. `HeroDraft` already has these; `Draft` gains them:

| Field | Type | Purpose |
|-------|------|---------|
| `paused_at` | DateTimeField (nullable) | When draft was paused |
| `resuming_until` | DateTimeField (nullable) | When resume countdown ends |
| `is_manual_pause` | BooleanField | Manual vs auto-pause |

The tick service reads these through a common interface (duck typing / protocol), so it doesn't care which model it's operating on.

### 4. TournamentConfig Model

New model for tournament-level configuration. Replaces hardcoded values across both draft types.

```python
# backend/app/models.py

class TournamentConfig(models.Model):
    tournament = models.OneToOneField(
        Tournament, on_delete=models.CASCADE, related_name="config"
    )

    PICK_TIMEOUT_CHOICES = [
        ("random", "Random Player"),
        # Future: ("highest_mmr", "Highest MMR"), ("skip", "Skip Turn")
    ]

    pick_timeout_strategy = models.CharField(
        max_length=16, choices=PICK_TIMEOUT_CHOICES, default="random"
    )
    grace_time_ms = models.IntegerField(default=30000)       # 30s per pick
    reserve_time_ms = models.IntegerField(default=90000)     # 90s pool per team
    enable_pick_timer = models.BooleanField(default=False)   # Off for backwards compat
    pause_on_disconnect = models.BooleanField(default=True)
    resume_countdown_ms = models.IntegerField(default=3000)  # 3s countdown
```

Auto-created when a Tournament is created. Serialized as nested `config` field in existing tournament API responses.

**Frontend Zod schema:**

```typescript
// frontend/app/components/tournament/config.tsx

import { z } from "zod";

export const TournamentConfigSchema = z.object({
  pick_timeout_strategy: z.enum(["random"]),
  grace_time_ms: z.number().min(5000).max(120000),
  reserve_time_ms: z.number().min(0).max(300000),
  enable_pick_timer: z.boolean(),
  pause_on_disconnect: z.boolean(),
  resume_countdown_ms: z.number().min(1000).max(10000),
});

export type TournamentConfig = z.infer<typeof TournamentConfigSchema>;
```

### 5. Team Draft WebSocket Upgrade

The existing `DraftConsumer` at `api/draft/<draft_id>/` gains the same lifecycle as `HeroDraftConsumer`:

**Connect:**
- Track connection count in Redis
- Identify if user is captain for current round
- Start `TeamDraftTickService` if `enable_pick_timer` is true in tournament config

**Disconnect:**
- Decrement connection count
- Mark captain disconnected
- Auto-pause if `pause_on_disconnect` is true and draft is in active picking state

**Heartbeat:**
- Same Redis key pattern as herodraft
- Same 9-second stale detection threshold
- Stale captain triggers auto-pause

**Tick broadcast:**
- Grace time remaining, reserve time per captain, active captain ID
- Pause/resume state changes

**Pick submission stays HTTP** — `choosePlayerHook.tsx` still calls `PickPlayerForRound()`. The WebSocket is receive-only for timer/pause events. The tick service validates picks are within the time window server-side.

**Frontend changes:**

- `useDraftLive.ts`: Connect WebSocket when `enable_pick_timer` is true, fall back to polling when disabled
- Timer display component in team draft UI (grace timer + reserve time)
- Shared `DraftPauseOverlay` component extracted from herodraft's pause overlay pattern
- Timer configuration in draft style settings modal (`draftStyleModal.tsx`)

### 6. Migration Path

Three independently deployable phases:

**Phase 1 — Foundation (no behavior changes):**
- Add `TournamentConfig` model + migration
- Data migration: auto-create config for all existing tournaments with defaults
- Add abstract `PauseEvent` model + concrete `HeroDraftPauseEvent`, `TeamDraftPauseEvent`
- Add pause fields to `Draft` model (`paused_at`, `resuming_until`, `is_manual_pause`)
- Extract `DraftTickService` base class from `herodraft_tick.py`
- Refactor existing code into `HeroDraftTickService` subclass — zero behavior change
- Frontend: add `TournamentConfigSchema`, wire into tournament serializer

**Phase 2 — Herodraft reads from config:**
- Herodraft tick service reads `grace_time_ms`, `reserve_time_ms`, `resume_countdown_ms` from `TournamentConfig`
- Herodraft pause/resume creates `HeroDraftPauseEvent` records
- Time calculations migrate from `started_at` adjustment to PauseEvent-based subtraction
- All existing herodraft tests must still pass

**Phase 3 — Team draft timers:**
- `TeamDraftTickService` with `on_timeout()` picking random player
- `DraftConsumer` upgraded with heartbeat/connection tracking
- Frontend WebSocket + timer UI + pause overlay
- `enable_pick_timer` defaults to `False` — existing tournaments unaffected
- New tournaments can opt in via tournament config

## File Changes Summary

### New Files
- `backend/app/tasks/draft_tick.py` — `DraftTickService` base class
- `frontend/app/components/tournament/config.tsx` — `TournamentConfigSchema`

### Modified Files
- `backend/app/models.py` — `TournamentConfig`, `PauseEvent`, `HeroDraftPauseEvent`, `TeamDraftPauseEvent`, pause fields on `Draft`
- `backend/app/tasks/herodraft_tick.py` — Refactored to `HeroDraftTickService` extending `DraftTickService`
- `backend/app/consumers.py` — `DraftConsumer` gains heartbeat/connection/tick lifecycle
- `backend/app/functions/herodraft_views.py` — Pause/resume creates PauseEvent records, reads config
- `backend/app/functions/tournament.py` — `pick_player_for_round()` validates time window when timers enabled
- `backend/app/serializers.py` — Tournament serializer gains nested `config` field
- `frontend/app/components/teamdraft/hooks/useDraftLive.ts` — WebSocket mode when timers enabled
- `frontend/app/components/teamdraft/liveView.tsx` — Timer display
- `frontend/app/components/teamdraft/buttons/draftStyleModal.tsx` — Timer config UI
- `frontend/app/components/herodraft/HeroDraftModal.tsx` — Extract pause overlay to shared component

## Review Findings

### Critical

1. **Redis key migration during Phase 1**: Changing from `herodraft:tick_lock:{draft_id}` to `draft:tick_lock:herodraft:{draft_id}` during Phase 1 could cause duplicate tick loops on any live herodraft. The old lock key would be abandoned while the new key doesn't exist yet, allowing a second broadcaster to acquire the new lock.

   **Mitigation**: Phase 1 `HeroDraftTickService` must use the **existing** Redis key patterns (`herodraft:*`). Introduce the new `draft:{draft_type}:*` pattern only in the `DraftTickService` base class as a default, and let `HeroDraftTickService` override all key properties to match the legacy format. Migrate keys in a later phase when no drafts are live, or add dual-key cleanup logic.

2. **Phase 2 time calculation transition**: Switching from `started_at` adjustment to PauseEvent-based subtraction mid-flight could break in-progress drafts. If a draft was paused/resumed before the Phase 2 deploy, its `started_at` was already adjusted — but there are no `HeroDraftPauseEvent` records for those historical pauses.

   **Mitigation**: Phase 2 must be **write-both, read-old** initially: continue adjusting `started_at` AND create PauseEvent records. Only switch to PauseEvent-based reads once all active drafts were created after Phase 2 deployed, or add a migration flag per draft.

### Important

3. **Open pause event on crash**: If the tick service crashes or the server restarts while a draft is paused, there will be an unclosed `PauseEvent` (no `resumed_at`). The `duration` property returns `None` for these, so `total_paused` calculation would silently skip them, under-counting pause time.

   **Mitigation**: On tick service startup, check for open pause events and either close them (if draft is no longer paused) or include `now - paused_at` as ongoing pause duration in the calculation.

4. **Module-level import compatibility**: `herodraft_tick.py` currently uses module-level Redis and Django imports. The new `draft_tick.py` base class must avoid importing anything that requires Django to be fully initialized at import time, or use lazy imports.

   **Mitigation**: Use `django.utils.module_loading.import_string` or local imports inside methods for Django-dependent code in the base class.

5. **TournamentConfig auto-creation**: The plan says "auto-created when a Tournament is created" but doesn't specify the mechanism. Using a `post_save` signal is the Django convention, but signals can be fragile in tests.

   **Mitigation**: Use a `post_save` signal on `Tournament` with `created=True` check. Also add `TournamentConfig` creation to the test fixture setup to avoid signal-dependent test fragility.

6. **Django validators on TournamentConfig**: The Zod schema has `min`/`max` constraints but the Django model uses plain `IntegerField` with no validators. Server-side data could violate frontend expectations.

   **Mitigation**: Add `MinValueValidator`/`MaxValueValidator` to `grace_time_ms`, `reserve_time_ms`, and `resume_countdown_ms` fields matching the Zod constraints.

7. **Missing DraftRound temporal fields**: `DraftRound` (team draft) currently has no `started_at` or `completed_at` fields, but the tick service needs `round.started_at` to calculate elapsed time. `HeroDraftRound` already has these fields.

   **Mitigation**: Add `started_at` and `completed_at` DateTimeFields to `DraftRound` in Phase 1 migration. Populate `started_at` when a round becomes active, `completed_at` when a pick is made.

8. **Frontend schema location**: The plan puts `TournamentConfigSchema` in `config.tsx`, but the existing pattern is `schemas.ts` files (e.g., `herodraft/schemas.ts`). Also, `.tsx` implies JSX which a pure Zod schema file doesn't need.

   **Mitigation**: Place the schema in `frontend/app/components/tournament/schemas.ts` to match existing patterns. If `schemas.ts` already exists there, add to it.

9. **DraftConsumer timer gating**: `DraftConsumer` must check `enable_pick_timer` from `TournamentConfig` before starting the tick service. If the config doesn't exist (pre-Phase-1 tournaments), it should gracefully fall back to the current behavior (no timers).

   **Mitigation**: Use `getattr(tournament, 'config', None)` with a fallback to defaults, or catch `TournamentConfig.DoesNotExist`.

10. **Cache invalidation on TournamentConfig changes**: If an admin changes timer settings mid-tournament, the tick service (which may cache config in memory) won't pick up the change until restart.

    **Mitigation**: The tick service should re-read config from DB each tick (it's a single-row read), or subscribe to a Redis pub/sub channel for config change notifications.

### Suggestions

11. **Protocol class for duck typing**: Rather than relying on implicit duck typing between `HeroDraft` and `Draft`, define an explicit `DraftProtocol` (Python `typing.Protocol`) that both models satisfy. This provides IDE autocomplete and catches interface mismatches at type-check time.

12. **Reuse existing WebSocketManager**: The frontend already has `frontend/app/lib/websocket/WebSocketManager.ts`. The team draft WebSocket should use this rather than creating a new connection manager, to stay consistent with herodraft's approach.

13. **PauseEvent round reference**: Consider adding an optional FK to the active round on `PauseEvent`, so you can query which round was active when the pause occurred. Useful for analytics and debugging.
