# Abstract Draft Pause & Timer System

**Date**: 2026-02-07
**Branch**: `feature/abstract-draft-pause` (from `feature/admin-team-modal`)
**Related Issues**: #110 (Abstract PauseEvent), #133 (Auction Draft), #134 (Team Draft Timers)

## Summary

Unify the herodraft and team draft systems by extracting a shared tick service, abstract pause model, and tournament config. The only difference between draft types is the timeout action (pick hero vs pick player vs close bid). Everything else — timers, pause/resume, heartbeats, connection tracking — is shared infrastructure.

## Design

### 1. Shared Tick Service

Extract the herodraft tick loop (`herodraft_tick.py`) into a generic `DraftTickService` base class. The tick loop runs every 1 second and performs 5 steps:

1. Check resume countdown (RESUMING -> DRAFTING)
2. Check captain heartbeats (detect stale connections)
3. Broadcast tick (timing data to WebSocket clients)
4. Check timeout (delegate to subclass)
5. Extend distributed lock

Steps 1, 2, 3, and 5 are identical across all draft types. Only step 4 varies.

```python
# backend/app/tasks/draft_tick.py

class DraftTickService:
    """Generic tick loop for any timed draft."""

    # Default key patterns for new draft types.
    # Subclasses may override to preserve legacy patterns.
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

- **`HeroDraftTickService`**: `on_timeout()` auto-picks a random hero. Refactored from existing `herodraft_tick.py`. **Overrides all Redis key properties to preserve legacy patterns** (`herodraft:tick_lock:{draft_id}`, `herodraft:connections:{draft_id}`, etc.) to avoid duplicate tick loops during deployment.
- **`TeamDraftTickService`**: `on_timeout()` picks a random available player (reads `pick_timeout_strategy` from `TournamentConfig`). Uses the new generic key patterns.
- **Future `AuctionTickService`**: `on_timeout()` closes the current bid round.

**Import compatibility**: `herodraft_tick.py` must maintain backward-compatible module-level functions (`start_tick_broadcaster`, `increment_connection_count`, `decrement_connection_count`, `get_connection_count`) that delegate to `HeroDraftTickService`. All existing import sites in `consumers.py` continue to work without changes in Phase 1.

**Config reads**: The tick service re-reads `TournamentConfig` from the database each tick (single-row `select_related` read) rather than caching in memory, so admin config changes take effect within 1 second.

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
    paused_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL,
        related_name="+"  # No reverse relation needed
    )
    paused_at = models.DateTimeField()
    resumed_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")

    class Meta:
        abstract = True
        ordering = ["-paused_at"]

    @property
    def duration(self):
        """Returns pause duration. For open (in-progress) pauses, returns
        elapsed time since pause started to avoid silent under-counting."""
        if self.resumed_at:
            return self.resumed_at - self.paused_at
        return timezone.now() - self.paused_at
```

Concrete models:

- **`HeroDraftPauseEvent(PauseEvent)`**: FK to `HeroDraft`, optional FK to `HeroDraftRound` (the round active when pause occurred — useful for scoping time calculations and analytics)
- **`TeamDraftPauseEvent(PauseEvent)`**: FK to `Draft`, optional FK to `DraftRound`

**Time calculation**: Instead of adjusting `started_at` on resume, the tick service calculates elapsed active time by subtracting total paused duration. Pause events are scoped to the active round:

```python
pause_events = draft.pause_events.filter(round=current_round)
total_paused = sum(
    (pe.duration for pe in pause_events),
    timedelta()
)
active_elapsed = (now - current_round.started_at) - total_paused
```

**`resumed_at` timing**: Set when the RESUMING -> DRAFTING transition completes (after the countdown), not when the resume button is pressed. This naturally includes the countdown duration in the paused time, matching the current behavior where `started_at` adjustment includes the 3-second countdown.

**Transaction safety**: PauseEvent creation must happen inside the same `select_for_update` transaction that transitions the draft state to PAUSED, preventing race conditions between consumer disconnect and heartbeat stale detection.

**Crash recovery**: On tick service startup, check for open pause events (no `resumed_at`). If the draft is no longer paused, close them with `resumed_at = now`. The `duration` property's fallback to `timezone.now() - paused_at` handles the case where the tick service queries mid-pause.

### 3. Pause State on Draft Models

Both `HeroDraft` and `Draft` models get the same pause fields. `HeroDraft` already has these; `Draft` gains them:

| Field | Type | Purpose |
|-------|------|---------|
| `paused_at` | DateTimeField (nullable) | When draft was paused |
| `resuming_until` | DateTimeField (nullable) | When resume countdown ends |
| `is_manual_pause` | BooleanField | Manual vs auto-pause |

The tick service reads these through a common interface (duck typing), so it doesn't care which model it's operating on.

**DraftRound temporal fields**: `DraftRound` (team draft) currently has no `started_at` or `completed_at` fields, but the tick service needs `round.started_at` to calculate elapsed time. `HeroDraftRound` already has these. Add to `DraftRound` in Phase 1:

| Field | Type | Purpose |
|-------|------|---------|
| `started_at` | DateTimeField (nullable) | When round became active |
| `completed_at` | DateTimeField (nullable) | When pick was made |

Populate `started_at` when a round becomes active, `completed_at` when a pick is submitted.

### 4. TournamentConfig Model

New model for tournament-level configuration. Replaces hardcoded values across both draft types.

```python
# backend/app/models.py

from django.core.validators import MinValueValidator, MaxValueValidator

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
    grace_time_ms = models.IntegerField(
        default=30000,
        validators=[MinValueValidator(5000), MaxValueValidator(120000)]
    )
    reserve_time_ms = models.IntegerField(
        default=90000,
        validators=[MinValueValidator(0), MaxValueValidator(300000)]
    )
    enable_pick_timer = models.BooleanField(default=False)   # Off for backwards compat
    pause_on_disconnect = models.BooleanField(default=True)
    resume_countdown_ms = models.IntegerField(
        default=3000,
        validators=[MinValueValidator(1000), MaxValueValidator(10000)]
    )
```

**Auto-creation**: Use a `post_save` signal on `Tournament` with `created=True` guard (consistent with existing `app/signals.py` patterns). Data migration in Phase 1 creates configs for all existing tournaments with defaults.

```python
# backend/app/signals.py

@receiver(post_save, sender=Tournament)
def create_tournament_config(sender, instance, created, **kwargs):
    if created:
        TournamentConfig.objects.get_or_create(tournament=instance)
```

**Serializer**: Add `TournamentConfigSerializer(ModelSerializer)` as a nested `config = TournamentConfigSerializer(read_only=True)` field on `TournamentSerializer`. Update `TournamentView.get_queryset()` to include `select_related("config")`. Add `TournamentConfig` to `cached_as` model dependencies in both `list()` and `retrieve()` methods.

**Frontend Zod schema** — add to the existing `schemas.ts` file (not a new `.tsx` file):

```typescript
// frontend/app/components/tournament/schemas.ts (add to existing file)

export const TournamentConfigSchema = z.object({
  pick_timeout_strategy: z.enum(["random"]),
  grace_time_ms: z.number().min(5000).max(120000),
  reserve_time_ms: z.number().min(0).max(300000),
  enable_pick_timer: z.boolean(),
  pause_on_disconnect: z.boolean(),
  resume_countdown_ms: z.number().min(1000).max(10000),
});

export type TournamentConfig = z.infer<typeof TournamentConfigSchema>;

// Update existing TournamentSchema:
export const TournamentSchema = z.object({
  // ... existing fields ...
  config: TournamentConfigSchema.optional(),
});
```

### 5. Team Draft WebSocket Upgrade

The existing `DraftConsumer` at `api/draft/<draft_id>/` gains the same lifecycle as `HeroDraftConsumer`. **All new behavior is gated behind `enable_pick_timer`** — when disabled (default), `DraftConsumer` behaves exactly as today with zero overhead.

```python
# In DraftConsumer.connect():
config = getattr(self.tournament, 'config', None)
self.timers_enabled = config and config.enable_pick_timer
if not self.timers_enabled:
    return  # Skip all timer/heartbeat/connection logic
```

**Connect** (when timers enabled):
- Track connection count in Redis
- Identify if user is captain for current round
- Start `TeamDraftTickService`

**Disconnect** (when timers enabled):
- Decrement connection count
- Mark captain disconnected
- Auto-pause if `pause_on_disconnect` is true and draft is in active picking state

**Heartbeat** (when timers enabled):
- Same Redis key pattern as herodraft
- Same 9-second stale detection threshold
- Stale captain triggers auto-pause

**Tick broadcast** (when timers enabled):
- Grace time remaining, reserve time per captain, active captain ID
- Pause/resume state changes

**Pick submission stays HTTP** — `choosePlayerHook.tsx` still calls `PickPlayerForRound()`. The WebSocket is receive-only for timer/pause events. The tick service validates picks are within the time window server-side (gated behind `enable_pick_timer`).

**Frontend changes:**

- **`draftWebSocketStore.ts`**: Add tick state (`TeamDraftTick`), heartbeat start/stop actions, and pause selectors (analogous to `heroDraftStore.ts`). This store already manages the team draft WebSocket connection via `getWebSocketManager()`.
- **`useDraftLive.ts`**: Remains as the polling fallback when `enable_pick_timer` is false. When timers are enabled, components read from `draftWebSocketStore` instead.
- **`teamdraft/schemas.ts`**: Add Zod schemas for team draft tick/pause WebSocket messages (matching the herodraft pattern in `herodraft/schemas.ts`).
- **Timer display component** in team draft UI (grace timer + reserve time).
- **Shared `DraftPauseOverlay`** component in `frontend/app/components/reusable/DraftPauseOverlay.tsx`. Props interface abstracts over both draft model shapes (accepts `isPaused`, `isResuming`, `countdown`, `allConnected`, `isManualPause`, `onResume`, `onClose`).
- Timer configuration in draft style settings modal (`draftStyleModal.tsx`).

### 6. Migration Path

Three independently deployable phases. **Deployment constraint**: Phase 2 should be deployed when no herodrafts are in progress, to avoid time calculation inconsistencies between old `started_at`-adjusted rounds and new PauseEvent-tracked rounds.

**Phase 1 — Foundation (no behavior changes):**
- Add `TournamentConfig` model with validators + `post_save` signal + migration
- Data migration: auto-create config for all existing tournaments with defaults
- Add abstract `PauseEvent` model + concrete `HeroDraftPauseEvent`, `TeamDraftPauseEvent` (with round FK)
- Add pause fields to `Draft` model (`paused_at`, `resuming_until`, `is_manual_pause`)
- Add `started_at`, `completed_at` to `DraftRound` model (nullable, for Phase 3 time validation)
- Extract `DraftTickService` base class into `backend/app/tasks/draft_tick.py`
- Refactor into `HeroDraftTickService` subclass — **preserves legacy Redis key patterns**, maintains backward-compatible module-level functions — zero behavior change
- Backend: `TournamentConfigSerializer` nested in `TournamentSerializer`, `select_related("config")`, `cached_as` dependency
- Frontend: add `TournamentConfigSchema` to `tournament/schemas.ts`, update `TournamentSchema` with optional `config` field

**Phase 2 — Herodraft reads from config:**
- Herodraft tick service reads `grace_time_ms`, `reserve_time_ms`, `resume_countdown_ms` from `TournamentConfig` instead of hardcoded defaults
- Herodraft pause/resume creates `HeroDraftPauseEvent` records (write-both: continue adjusting `started_at` AND create PauseEvent records for transition safety)
- Replace hardcoded `reserve_time_remaining = 90000` in `herodraft_views.py` reset with config read
- Time calculations switch to PauseEvent-based subtraction for newly created drafts only
- All existing herodraft tests must still pass

**Phase 3 — Team draft timers:**
- `TeamDraftTickService` with `on_timeout()` picking random player
- `DraftConsumer` upgraded with heartbeat/connection/tick lifecycle, all gated behind `enable_pick_timer`
- Populate `DraftRound.started_at`/`completed_at` in pick flow
- `pick_player_for_round()` validates time window when `enable_pick_timer` is true
- Frontend: `draftWebSocketStore.ts` gains tick/heartbeat/pause state + team draft tick Zod schemas
- Frontend: timer UI + `DraftPauseOverlay` in `components/reusable/`
- `enable_pick_timer` defaults to `False` — existing tournaments unaffected
- New tournaments can opt in via tournament config

## File Changes Summary

### New Files
- `backend/app/tasks/draft_tick.py` — `DraftTickService` base class
- `frontend/app/components/reusable/DraftPauseOverlay.tsx` — Shared pause overlay component

### Modified Files
- `backend/app/models.py` — `TournamentConfig`, `PauseEvent`, `HeroDraftPauseEvent`, `TeamDraftPauseEvent`, pause fields on `Draft`, temporal fields on `DraftRound`
- `backend/app/signals.py` — `post_save` signal for `TournamentConfig` auto-creation
- `backend/app/tasks/herodraft_tick.py` — Refactored to `HeroDraftTickService` extending `DraftTickService`, maintains backward-compatible module-level functions
- `backend/app/consumers.py` — `DraftConsumer` gains heartbeat/connection/tick lifecycle (gated behind `enable_pick_timer`)
- `backend/app/functions/herodraft_views.py` — Pause/resume creates PauseEvent records, reads config
- `backend/app/functions/tournament.py` — `pick_player_for_round()` validates time window when timers enabled
- `backend/app/serializers.py` — `TournamentConfigSerializer`, nested in `TournamentSerializer` with `select_related` and `cached_as`
- `frontend/app/components/tournament/schemas.ts` — `TournamentConfigSchema`, updated `TournamentSchema`
- `frontend/app/components/teamdraft/schemas.ts` — Team draft tick/pause WebSocket message schemas
- `frontend/app/store/draftWebSocketStore.ts` — Tick state, heartbeat, pause selectors
- `frontend/app/components/teamdraft/hooks/useDraftLive.ts` — Polling fallback (unchanged when timers disabled)
- `frontend/app/components/teamdraft/liveView.tsx` — Timer display
- `frontend/app/components/teamdraft/buttons/draftStyleModal.tsx` — Timer config UI
- `frontend/app/components/herodraft/HeroDraftModal.tsx` — Extract pause overlay to shared component
- `backend/app/views_main.py` — `select_related("config")` in `TournamentView.get_queryset()`, `TournamentConfig` in `cached_as` dependencies

## Review Suggestions (Round 2)

All 5 review agents found **0 critical issues**. Below are the important items and suggestions grouped by area.

### Tick Service

**Important:**
- Expand backward-compatible import list to include `get_redis_client`, `stop_tick_broadcaster`, and any test-facing symbols — not just the 4 currently listed.

**Suggestions:**
- Specify `check_continue` PAUSED-means-continue behavior in base class contract (tick loop stays alive during PAUSED; only COMPLETED/ABANDONED exit).
- Fold config read into existing `get_tick_data` query via `.select_related("tournament__config")` to avoid a second DB hit per tick.

### Pause Model

**Important:**
- `paused_at` field needs `default=timezone.now` to prevent missing-value errors when created programmatically.
- Crash recovery must also handle drafts stuck in RESUMING with expired `resuming_until` — close the open PauseEvent and transition to DRAFTING.
- `reset_draft` (herodraft reset endpoint) must delete PauseEvents: `draft.pause_events.all().delete()`.

**Suggestions:**
- Capture `now = timezone.now()` once and pass through to avoid timing skew in duration calculation across multiple PauseEvents in the same tick.
- Add `__str__` to abstract PauseEvent (`f"{self.pause_type} at {self.paused_at}"`).

### Tournament Config

**Important:**
- `signals.py` needs `post_save` import added (currently only imports `m2m_changed`).
- `views_main.py` is missing from the File Changes Summary — needs `select_related("config")` in `get_queryset()` and `TournamentConfig` added to `cached_as` in both `list()` and `retrieve()`.

**Suggestions:**
- Document idempotency of `get_or_create` + signal + data migration belt-and-suspenders approach.
- Specify whether `pk` is included in `TournamentConfigSerializer` fields (recommend excluding it — frontend doesn't need it).
- Add `__str__` method to `TournamentConfig` (`f"Config for {self.tournament}"`).

### Migration Phasing

**Important:**
- Phase 2 write-both has a double-counting risk: if new drafts use PauseEvent subtraction but `started_at` is also being adjusted, pause time is subtracted twice. Fix: add `use_pause_events` boolean on `HeroDraft` (default `False` for existing, `True` for new Phase 2 drafts). Only use PauseEvent subtraction when flag is `True`; those drafts stop adjusting `started_at`.
- Migration files missing from File Changes Summary — Phase 1 needs at least 2 migrations (schema + data migration for existing tournaments).

**Suggestions:**
- Add deployment verification query: `HeroDraft.objects.exclude(state__in=['completed', 'abandoned']).exists()` before deploying Phase 2.
- `DraftConsumer.connect()` code sample references `self.tournament` which doesn't exist in current consumer — note that Phase 3 implementation must resolve `Draft -> Tournament -> TournamentConfig` chain.
- `check_resume_countdown()` in Phase 2 must also close the open PauseEvent (set `resumed_at`) when RESUMING -> DRAFTING transition completes.

### Frontend Patterns

**Important:**
- Enumerate new `draftWebSocketStore.ts` interface members: `startHeartbeat`, `stopHeartbeat`, `reconnect`, `_heartbeatInterval`.
- Switch from `as WebSocketMessage` type assertion to Zod `safeParse` in `draftWebSocketStore` message handler (matches herodraft pattern).
- `WebSocketMessage` type in `draftEvent.ts` must evolve to include tick/pause message variants.

**Suggestions:**
- `DraftPauseOverlay` props should include `canResume` (permission-gated) and `onReconnect` (for manual reconnection attempts).
- Timer display component needs explicit file name/placement (suggest `frontend/app/components/teamdraft/TimerBar.tsx`).
