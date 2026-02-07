# Abstract Draft Pause — Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add foundation models (TournamentConfig, PauseEvent), refactor tick service into base/subclass, and update serializers/schemas — with zero behavior changes.

**Architecture:** New models added to `models.py`, signal for auto-creation, tick service extracted into `draft_tick.py` base class with `HeroDraftTickService` subclass preserving all legacy Redis keys and module-level function signatures.

**Tech Stack:** Django, Django REST Framework, cacheops, Zod, TypeScript

**Design doc:** `docs/plans/2026-02-07-abstract-draft-pause-system.md`

---

### Task 1: Add TournamentConfig model

**Files:**
- Modify: `backend/app/models.py` (after `HeroDraftEvent` model, ~line 1602)

**Step 1: Add TournamentConfig model after HeroDraftEvent**

Add the import at the top of models.py (after the `django.db` imports, around line 6-10 — there are no existing validator imports):

```python
from django.core.validators import MinValueValidator, MaxValueValidator
```

Add the model after `HeroDraftEvent` (after line 1602):

```python
class TournamentConfig(models.Model):
    """Per-tournament configuration for draft timers and pause behavior."""

    tournament = models.OneToOneField(
        Tournament, on_delete=models.CASCADE, related_name="config"
    )

    PICK_TIMEOUT_CHOICES = [
        ("random", "Random Player"),
    ]

    pick_timeout_strategy = models.CharField(
        max_length=16, choices=PICK_TIMEOUT_CHOICES, default="random"
    )
    grace_time_ms = models.IntegerField(
        default=30000,
        validators=[MinValueValidator(5000), MaxValueValidator(120000)],
    )
    reserve_time_ms = models.IntegerField(
        default=90000,
        validators=[MinValueValidator(0), MaxValueValidator(300000)],
    )
    enable_pick_timer = models.BooleanField(default=False)
    pause_on_disconnect = models.BooleanField(default=True)
    resume_countdown_ms = models.IntegerField(
        default=3000,
        validators=[MinValueValidator(1000), MaxValueValidator(10000)],
    )

    def __str__(self):
        return f"Config for {self.tournament}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_obj(self)
        invalidate_obj(self.tournament)
```

**Step 2: Commit**

```
feat: add TournamentConfig model
```

---

### Task 2: Add PauseEvent abstract and concrete models

**Files:**
- Modify: `backend/app/models.py` (after `TournamentConfig`)

**Step 1: Add abstract PauseEvent and concrete models**

Add after `TournamentConfig`:

```python
class PauseEvent(models.Model):
    """Abstract audit trail for pause/resume events."""

    PAUSE_TYPE_CHOICES = [
        ("disconnect", "Captain Disconnected"),
        ("manual", "Manual Pause"),
        ("timeout", "Timeout"),
    ]

    pause_type = models.CharField(max_length=16, choices=PAUSE_TYPE_CHOICES)
    paused_by = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    paused_at = models.DateTimeField(default=timezone.now)
    resumed_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")

    class Meta:
        abstract = True
        ordering = ["-paused_at"]

    @property
    def duration(self):
        """Returns pause duration. For open pauses, returns elapsed time
        since pause started to avoid silent under-counting."""
        if self.resumed_at:
            return self.resumed_at - self.paused_at
        return timezone.now() - self.paused_at

    def __str__(self):
        return f"{self.pause_type} at {self.paused_at}"


class HeroDraftPauseEvent(PauseEvent):
    """Pause event for hero drafts."""

    draft = models.ForeignKey(
        HeroDraft, on_delete=models.CASCADE, related_name="pause_events"
    )
    round = models.ForeignKey(
        HeroDraftRound,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pause_events",
    )


class TeamDraftPauseEvent(PauseEvent):
    """Pause event for team drafts."""

    draft = models.ForeignKey(
        Draft, on_delete=models.CASCADE, related_name="pause_events"
    )
    round = models.ForeignKey(
        DraftRound,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pause_events",
    )
```

**Step 2: Commit**

```
feat: add PauseEvent abstract model with concrete herodraft/teamdraft variants
```

---

### Task 3: Add pause fields to Draft and temporal fields to DraftRound

**Files:**
- Modify: `backend/app/models.py`
  - `Draft` model (~line 788): add `paused_at`, `resuming_until`, `is_manual_pause`
  - `DraftRound` model (~line 1274): add `started_at`, `completed_at`

**Step 1: Add pause fields to Draft model**

Add these fields to the `Draft` model (after the existing `draft_style` field):

```python
    # Pause state (used when enable_pick_timer is on)
    paused_at = models.DateTimeField(null=True, blank=True)
    resuming_until = models.DateTimeField(null=True, blank=True)
    is_manual_pause = models.BooleanField(default=False)
```

**Step 2: Add temporal fields to DraftRound model**

Add these fields to the `DraftRound` model (after the existing fields, before `was_tie`):

```python
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
```

**Step 3: Commit**

```
feat: add pause fields to Draft, temporal fields to DraftRound
```

---

### Task 4: Add post_save signal for TournamentConfig auto-creation

**Files:**
- Modify: `backend/app/signals.py`

**Step 1: Update imports and add signal**

Add `post_save` to the existing signals import (line 13):

```python
from django.db.models.signals import m2m_changed, post_save
```

Add signal handler at the end of the file (after the last existing handler ~line 155):

```python
@receiver(post_save, sender="app.Tournament")
def create_tournament_config(sender, instance, created, **kwargs):
    """Auto-create TournamentConfig when a Tournament is created."""
    if created:
        from app.models import TournamentConfig

        TournamentConfig.objects.get_or_create(tournament=instance)
```

**Note:** Uses string sender `"app.Tournament"` to match the existing pattern in this file (e.g., line 19: `sender="app.Team"`). Lazy import of `TournamentConfig` avoids circular imports.

**Step 2: Commit**

```
feat: add post_save signal for TournamentConfig auto-creation
```

---

### Task 5: Admin registration for new models

**Files:**
- Modify: `backend/app/admin.py`

**Step 1: Add admin classes**

Update the import line (line 4):

```python
from .models import CustomUser, HeroDraft, HeroDraftEvent, HeroDraftPauseEvent, TournamentConfig
```

Add after `HeroDraftEventAdmin` (before the register lines):

```python
class HeroDraftPauseEventInline(admin.TabularInline):
    model = HeroDraftPauseEvent
    extra = 0
    readonly_fields = ["pause_type", "paused_by", "paused_at", "resumed_at", "round", "reason"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class TournamentConfigAdmin(admin.ModelAdmin):
    list_display = ["id", "tournament", "enable_pick_timer", "grace_time_ms", "reserve_time_ms"]
    list_filter = ["enable_pick_timer"]
    search_fields = ["tournament__name"]
```

Add `HeroDraftPauseEventInline` to `HeroDraftAdmin.inlines`:

```python
class HeroDraftAdmin(admin.ModelAdmin):
    ...
    inlines = [HeroDraftEventInline, HeroDraftPauseEventInline]
```

Add registration lines:

```python
admin.site.register(TournamentConfig, TournamentConfigAdmin)
```

**Step 2: Commit**

```
feat: register TournamentConfig and PauseEvent in admin
```

---

### Task 6: Create schema migration and data migration

**Files:**
- Create: `backend/app/migrations/XXXX_tournament_config_pause_events.py` (auto-generated)
- Create: `backend/app/migrations/XXXX_create_tournament_configs.py` (data migration)

**Step 1: Generate schema migration**

```bash
cd /home/kettle/git_repos/website/.worktrees/abstract-draft-pause && just db::makemigrations app
```

Expected: Creates migration with `TournamentConfig`, `HeroDraftPauseEvent`, `TeamDraftPauseEvent`, plus `paused_at`/`resuming_until`/`is_manual_pause` on `Draft` and `started_at`/`completed_at` on `DraftRound`.

**Step 2: Create data migration**

```bash
cd /home/kettle/git_repos/website/.worktrees/abstract-draft-pause && just py::manage 'makemigrations --empty app -n create_tournament_configs'
```

Then edit the generated file to add:

```python
from django.db import migrations


def create_configs(apps, schema_editor):
    Tournament = apps.get_model("app", "Tournament")
    TournamentConfig = apps.get_model("app", "TournamentConfig")
    for tournament in Tournament.objects.all():
        TournamentConfig.objects.get_or_create(tournament=tournament)


def remove_configs(apps, schema_editor):
    TournamentConfig = apps.get_model("app", "TournamentConfig")
    TournamentConfig.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("app", "XXXX_tournament_config_pause_events"),  # previous migration
    ]

    operations = [
        migrations.RunPython(create_configs, remove_configs),
    ]
```

**Step 3: Run migrations in all environments**

```bash
cd /home/kettle/git_repos/website/.worktrees/abstract-draft-pause && just db::migrate::all
```

**Step 4: Commit**

```
feat: add migrations for TournamentConfig, PauseEvent, Draft/DraftRound fields
```

---

### Task 7: TournamentConfigSerializer and TournamentSerializer update

**Files:**
- Modify: `backend/app/serializers.py`

**Step 1: Add TournamentConfigSerializer**

Add before `TournamentSerializer` (before line 725), with the necessary import:

```python
TournamentConfig,  # add to existing `from .models import (...)` block at line 11
```

```python
class TournamentConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = TournamentConfig
        fields = (
            "pick_timeout_strategy",
            "grace_time_ms",
            "reserve_time_ms",
            "enable_pick_timer",
            "pause_on_disconnect",
            "resume_countdown_ms",
        )
```

**Step 2: Add config field to TournamentSerializer**

Add to `TournamentSerializer` (after `league` field, ~line 742):

```python
    config = TournamentConfigSerializer(read_only=True)
```

Add `"config"` to the `Meta.fields` tuple (after `"league_pk"`, ~line 783):

```python
        fields = (
            ...
            "league_pk",
            "config",
        )
```

**Step 3: Commit**

```
feat: add TournamentConfigSerializer nested in TournamentSerializer
```

---

### Task 8: TournamentView updates (select_related, cached_as)

**Files:**
- Modify: `backend/app/views_main.py`

**Step 1: Add select_related("config") to get_queryset**

In `TournamentView.get_queryset()` (line 348), chain `select_related`:

```python
    def get_queryset(self):
        queryset = Tournament.objects.all().select_related("config").order_by("-date_played")
```

**Step 2: Add TournamentConfig to cached_as in list()**

Add `TournamentConfig` to the existing `from .models import (...)` block at the top of `views_main.py`. Then add to the `@cached_as` decorator in `list()` (line 360):

```python
        @cached_as(
            Tournament,
            TournamentConfig,
            Team,
            CustomUser,
            Draft,
            Game,
            DraftRound,
            extra=cache_key,
            timeout=60 * 10,
        )
```

**Step 3: Add TournamentConfig to cached_as in retrieve()**

Same pattern in `retrieve()` (line 382):

```python
        @cached_as(
            Tournament.objects.filter(pk=pk),
            TournamentConfig,
            Team,
            CustomUser,
            Game,
            Draft,
            DraftRound,
            extra=cache_key,
            timeout=60 * 10,
        )
```

**Step 4: Commit**

```
feat: add select_related and cached_as for TournamentConfig in views
```

---

### Task 9: Frontend TournamentConfigSchema

**Files:**
- Modify: `frontend/app/components/tournament/schemas.ts`

**Step 1: Add TournamentConfigSchema**

Add before `TournamentSchema` (before line 50):

```typescript
export const TournamentConfigSchema = z.object({
  pick_timeout_strategy: z.enum(['random']),
  grace_time_ms: z.number().min(5000).max(120000),
  reserve_time_ms: z.number().min(0).max(300000),
  enable_pick_timer: z.boolean(),
  pause_on_disconnect: z.boolean(),
  resume_countdown_ms: z.number().min(1000).max(10000),
});

export type TournamentConfig = z.infer<typeof TournamentConfigSchema>;
```

**Step 2: Add config to TournamentSchema**

Add after `league_pk` field (line 74):

```typescript
  config: TournamentConfigSchema.optional(),
```

**Step 3: Commit**

```
feat: add TournamentConfigSchema to frontend tournament schemas
```

---

### Task 10: Extract DraftTickService base class

**Files:**
- Create: `backend/app/tasks/draft_tick.py`

**Step 1: Create DraftTickService base class**

This extracts the common tick loop infrastructure. The base class owns: Redis client, connection tracking, lock management, tick loop, start/stop lifecycle. Subclasses implement: draft-specific DB reads, timeout handling, broadcast formatting.

```python
"""Base tick service for timed drafts.

Provides the common tick loop (1-second interval) with:
- Redis distributed locking
- Connection tracking
- Captain heartbeat stale detection
- Resume countdown handling
- Lock extension

Subclasses implement draft-specific behavior via abstract methods.
"""

import asyncio
import atexit
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import namedtuple

import redis
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from django.conf import settings

log = logging.getLogger(__name__)

# Redis client singleton
_redis_client = None


def get_redis_client():
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        redis_host = getattr(settings, "REDIS_HOST", "localhost")
        _redis_client = redis.Redis(
            host=redis_host, port=6379, db=2, decode_responses=True
        )
    return _redis_client


# Thread-safe registry for local cleanup
_lock = threading.Lock()
_active_tick_tasks = {}  # (draft_type, draft_id) -> TaskInfo
TaskInfo = namedtuple("TaskInfo", ["stop_event", "thread"])

LOCK_TIMEOUT = 10  # Lock expires after 10 seconds (renewed each tick)
HEARTBEAT_STALE_SECONDS = 9  # 3 missed beats at 3-second interval


class DraftTickService(ABC):
    """Generic tick loop for any timed draft.

    Subclasses override key properties for Redis key patterns
    and implement abstract methods for draft-specific behavior.
    """

    # Default key patterns — subclasses may override for legacy compat
    LOCK_KEY = "draft:tick_lock:{draft_type}:{draft_id}"
    CONN_KEY = "draft:connections:{draft_type}:{draft_id}"
    HEARTBEAT_KEY = "draft:{draft_type}:{draft_id}:captain:{user_id}:heartbeat"

    def __init__(self, draft_type: str, draft_id: int):
        self.draft_type = draft_type
        self.draft_id = draft_id

    def get_lock_key(self):
        return self.LOCK_KEY.format(
            draft_type=self.draft_type, draft_id=self.draft_id
        )

    def get_conn_key(self):
        return self.CONN_KEY.format(
            draft_type=self.draft_type, draft_id=self.draft_id
        )

    def get_heartbeat_key(self, user_id: int):
        return self.HEARTBEAT_KEY.format(
            draft_type=self.draft_type, draft_id=self.draft_id, user_id=user_id
        )

    # --- Connection tracking ---

    def increment_connection_count(self) -> int:
        r = get_redis_client()
        key = self.get_conn_key()
        count = r.incr(key)
        r.expire(key, 300)
        log.debug(
            f"{self.draft_type} {self.draft_id} connections incremented to {count}"
        )
        return count

    def decrement_connection_count(self) -> int:
        r = get_redis_client()
        key = self.get_conn_key()
        count = r.decr(key)
        if count <= 0:
            r.delete(key)
            count = 0
        log.debug(
            f"{self.draft_type} {self.draft_id} connections decremented to {count}"
        )
        return count

    def get_connection_count(self) -> int:
        r = get_redis_client()
        key = self.get_conn_key()
        count = r.get(key)
        return int(count) if count else 0

    # --- Abstract methods (subclasses implement) ---

    @abstractmethod
    async def broadcast_tick(self):
        """Broadcast current timing state to WebSocket clients."""
        ...

    @abstractmethod
    async def check_timeout(self):
        """Check if current round timed out and handle it."""
        ...

    @abstractmethod
    async def check_resume_countdown(self):
        """Check if RESUMING countdown completed and transition to DRAFTING."""
        ...

    @abstractmethod
    async def check_captain_heartbeats(self):
        """Check for stale captain heartbeats and auto-pause if needed."""
        ...

    @abstractmethod
    def should_continue_ticking(self) -> tuple[bool, str]:
        """Check if tick loop should continue. Called inside @database_sync_to_async.

        Returns (should_continue, reason_if_stopping).
        Tick loop stays alive during PAUSED/RESUMING states.
        Only returns False for terminal states (COMPLETED, ABANDONED)
        or zero connections during DRAFTING.
        """
        ...

    # --- Tick loop ---

    async def run_tick_loop(self, stop_event: threading.Event):
        """Run tick broadcasts every second while draft is active."""
        r = get_redis_client()
        lock_key = self.get_lock_key()

        @database_sync_to_async
        def check_continue():
            return self.should_continue_ticking()

        @sync_to_async(thread_sensitive=False)
        def extend_lock():
            r.expire(lock_key, LOCK_TIMEOUT)

        log.info(f"Tick loop started for {self.draft_type} {self.draft_id}")

        while not stop_event.is_set():
            should_continue, reason = await check_continue()
            if not should_continue:
                log.info(
                    f"Stopping tick loop for {self.draft_type} {self.draft_id}: {reason}"
                )
                break

            await self.check_resume_countdown()
            await self.check_captain_heartbeats()
            await self.broadcast_tick()
            await self.check_timeout()
            await extend_lock()
            await asyncio.sleep(1)

        log.info(f"Tick loop ended for {self.draft_type} {self.draft_id}")

    # --- Start/stop lifecycle ---

    def start(self) -> bool:
        """Start the tick broadcaster with Redis distributed lock.

        Returns True if started, False if already running elsewhere.
        """
        r = get_redis_client()
        lock_key = self.get_lock_key()
        stop_event = threading.Event()
        task_key = (self.draft_type, self.draft_id)

        acquired = r.set(lock_key, "locked", nx=True, ex=LOCK_TIMEOUT)
        if not acquired:
            log.debug(
                f"Tick broadcaster already running for {self.draft_type} {self.draft_id}"
            )
            return False

        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.run_tick_loop(stop_event))
            except Exception as e:
                log.error(
                    f"Tick broadcaster error for {self.draft_type} {self.draft_id}: {e}"
                )
            finally:
                loop.close()
                try:
                    r.delete(lock_key)
                except Exception:
                    pass
                with _lock:
                    _active_tick_tasks.pop(task_key, None)

        with _lock:
            if task_key in _active_tick_tasks:
                r.delete(lock_key)
                return False
            thread = threading.Thread(target=run_in_thread, daemon=True)
            _active_tick_tasks[task_key] = TaskInfo(stop_event, thread)

        thread.start()
        log.info(f"Started tick broadcaster for {self.draft_type} {self.draft_id}")
        return True

    def stop(self):
        """Stop the tick broadcaster."""
        r = get_redis_client()
        lock_key = self.get_lock_key()
        task_key = (self.draft_type, self.draft_id)

        with _lock:
            task_info = _active_tick_tasks.get(task_key)

        if task_info:
            log.info(f"Stopping tick broadcaster for {self.draft_type} {self.draft_id}")
            task_info.stop_event.set()
            task_info.thread.join(timeout=2.0)

        try:
            r.delete(lock_key)
        except Exception:
            pass

        with _lock:
            _active_tick_tasks.pop(task_key, None)


def stop_all_broadcasters():
    """Stop all active tick broadcasters. Called on shutdown."""
    r = get_redis_client()

    with _lock:
        task_keys = list(_active_tick_tasks.keys())

    for task_key in task_keys:
        draft_type, draft_id = task_key
        with _lock:
            task_info = _active_tick_tasks.get(task_key)
        if task_info:
            task_info.stop_event.set()
            task_info.thread.join(timeout=2.0)
        # Clean up Redis lock
        try:
            lock_key = f"draft:tick_lock:{draft_type}:{draft_id}"
            r.delete(lock_key)
        except Exception:
            pass
        with _lock:
            _active_tick_tasks.pop(task_key, None)

    log.info(f"Stopped {len(task_keys)} tick broadcasters on shutdown")


atexit.register(stop_all_broadcasters)
```

**Step 2: Commit**

```
feat: extract DraftTickService base class into draft_tick.py
```

---

### Task 11: Refactor HeroDraftTickService

**Files:**
- Modify: `backend/app/tasks/herodraft_tick.py` (rewrite to subclass)

**Step 1: Rewrite herodraft_tick.py**

Replace the entire file. The key design decisions:
- `HeroDraftTickService` extends `DraftTickService`
- Overrides `LOCK_KEY`, `CONN_KEY`, `HEARTBEAT_KEY` to preserve legacy Redis patterns
- All existing module-level functions become thin wrappers around a per-draft instance
- `start_tick_broadcaster`, `stop_tick_broadcaster`, `stop_all_broadcasters` maintain exact same signatures
- `increment_connection_count`, `decrement_connection_count`, `get_connection_count`, `get_redis_client` maintain exact same signatures

```python
"""HeroDraft tick service — broadcasts timing updates during active hero drafts.

Extends DraftTickService with herodraft-specific timeout (auto-random-pick),
resume countdown, heartbeat, and broadcast logic.

BACKWARD COMPATIBILITY: Module-level functions maintain the same signatures
as the original implementation. All import sites (consumers.py, etc.) continue
to work without changes.
"""

import logging
import time

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.utils import timezone

from app.tasks.draft_tick import (  # noqa: F401
    DraftTickService,
    _active_tick_tasks,
    _lock,
    get_redis_client,
    stop_all_broadcasters,
)

log = logging.getLogger(__name__)

HEARTBEAT_STALE_SECONDS = 9


class HeroDraftTickService(DraftTickService):
    """Tick service for hero drafts.

    Overrides Redis key patterns to preserve legacy format and avoid
    duplicate tick loops during rolling deployment.
    """

    # Override base class keys with legacy patterns
    LOCK_KEY = "herodraft:tick_lock:{draft_id}"
    CONN_KEY = "herodraft:connections:{draft_id}"
    HEARTBEAT_KEY = "herodraft:{draft_id}:captain:{user_id}:heartbeat"

    def __init__(self, draft_id: int):
        super().__init__("herodraft", draft_id)

    # Override key methods to use legacy format (no draft_type in key)
    def get_lock_key(self):
        return self.LOCK_KEY.format(draft_id=self.draft_id)

    def get_conn_key(self):
        return self.CONN_KEY.format(draft_id=self.draft_id)

    def get_heartbeat_key(self, user_id: int):
        return self.HEARTBEAT_KEY.format(
            draft_id=self.draft_id, user_id=user_id
        )

    # --- Implement abstract methods ---

    async def broadcast_tick(self):
        from app.models import HeroDraft, HeroDraftState

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        room_group_name = f"herodraft_{self.draft_id}"

        @database_sync_to_async
        def get_tick_data():
            try:
                draft = HeroDraft.objects.get(id=self.draft_id)
            except HeroDraft.DoesNotExist:
                return None

            if draft.state == HeroDraftState.RESUMING:
                now = timezone.now()
                countdown_remaining_ms = 0
                if draft.resuming_until:
                    remaining = (draft.resuming_until - now).total_seconds() * 1000
                    countdown_remaining_ms = max(0, int(remaining))
                return {
                    "type": "herodraft.tick",
                    "draft_state": draft.state,
                    "countdown_remaining_ms": countdown_remaining_ms,
                }

            if draft.state != HeroDraftState.DRAFTING:
                return None

            current_round = draft.rounds.filter(state="active").first()
            if not current_round:
                return None

            teams = list(draft.draft_teams.all().order_by("id"))
            team_a = teams[0] if teams else None
            team_b = teams[1] if len(teams) > 1 else None

            now = timezone.now()
            elapsed_ms = 0
            grace_remaining = current_round.grace_time_ms

            if current_round.started_at:
                elapsed_ms = int(
                    (now - current_round.started_at).total_seconds() * 1000
                )
                grace_remaining = max(0, current_round.grace_time_ms - elapsed_ms)

            reserve_consumed_ms = max(0, elapsed_ms - current_round.grace_time_ms)
            active_team_id = current_round.draft_team_id
            team_a_reserve = team_a.reserve_time_remaining if team_a else 0
            team_b_reserve = team_b.reserve_time_remaining if team_b else 0

            if team_a and team_a.id == active_team_id:
                team_a_reserve = max(0, team_a_reserve - reserve_consumed_ms)
            elif team_b and team_b.id == active_team_id:
                team_b_reserve = max(0, team_b_reserve - reserve_consumed_ms)

            log.debug(
                f"Tick draft {self.draft_id}: round={current_round.round_number}, "
                f"elapsed={elapsed_ms}ms, grace_remaining={grace_remaining}ms, "
                f"reserve_consumed={reserve_consumed_ms}ms, "
                f"team_a_reserve={team_a_reserve}ms, team_b_reserve={team_b_reserve}ms"
            )

            return {
                "type": "herodraft.tick",
                "current_round": current_round.round_number - 1,
                "active_team_id": active_team_id,
                "grace_time_remaining_ms": grace_remaining,
                "team_a_id": team_a.id if team_a else None,
                "team_a_reserve_ms": team_a_reserve,
                "team_b_id": team_b.id if team_b else None,
                "team_b_reserve_ms": team_b_reserve,
                "draft_state": draft.state,
            }

        tick_data = await get_tick_data()
        if tick_data:
            try:
                await channel_layer.group_send(room_group_name, tick_data)
            except Exception as e:
                log.warning(
                    f"Failed to broadcast tick for draft {self.draft_id}: {e}"
                )

    async def check_timeout(self):
        from django.db import transaction

        from app.broadcast import broadcast_herodraft_state
        from app.functions.herodraft import auto_random_pick
        from app.models import DraftTeam, HeroDraft, HeroDraftState

        @database_sync_to_async
        def check_and_auto_pick():
            completed_round = None

            with transaction.atomic():
                try:
                    draft = HeroDraft.objects.select_for_update().get(
                        id=self.draft_id
                    )
                except HeroDraft.DoesNotExist:
                    return None

                if draft.state != HeroDraftState.DRAFTING:
                    return None

                current_round = (
                    draft.rounds.select_for_update().filter(state="active").first()
                )
                if not current_round:
                    return None

                now = timezone.now()
                if not current_round.started_at:
                    return None

                elapsed_ms = int(
                    (now - current_round.started_at).total_seconds() * 1000
                )
                team = DraftTeam.objects.select_for_update().get(
                    id=current_round.draft_team_id
                )
                total_time = current_round.grace_time_ms + team.reserve_time_remaining

                if elapsed_ms >= total_time:
                    log.info(
                        f"Timeout reached for draft {self.draft_id}, "
                        f"round {current_round.round_number}"
                    )
                    completed_round = auto_random_pick(draft, team)

            if completed_round:
                try:
                    draft = HeroDraft.objects.prefetch_related(
                        "draft_teams__tournament_team__captain",
                        "draft_teams__tournament_team__members",
                        "rounds",
                    ).get(id=self.draft_id)
                    broadcast_herodraft_state(draft, "hero_selected")
                    log.debug(
                        f"Broadcast auto-pick state for draft {self.draft_id}"
                    )
                except Exception as e:
                    log.error(
                        f"Failed to broadcast auto-pick for draft {self.draft_id}: {e}"
                    )

            return completed_round

        return await check_and_auto_pick()

    async def check_resume_countdown(self):
        from django.db import transaction

        from app.broadcast import broadcast_herodraft_state
        from app.models import HeroDraft, HeroDraftEvent, HeroDraftState

        @database_sync_to_async
        def check_and_resume():
            transitioned = False

            with transaction.atomic():
                try:
                    draft = HeroDraft.objects.select_for_update().get(
                        id=self.draft_id
                    )
                except HeroDraft.DoesNotExist:
                    return False

                if draft.state != HeroDraftState.RESUMING:
                    return False

                now = timezone.now()
                if not draft.resuming_until or now < draft.resuming_until:
                    return False

                draft.state = HeroDraftState.DRAFTING
                draft.resuming_until = None
                draft.save()
                HeroDraftEvent.objects.create(
                    draft=draft,
                    event_type="draft_resumed",
                    metadata={},
                )
                log.info(f"HeroDraft {self.draft_id} resumed after countdown")
                transitioned = True

            if transitioned:
                try:
                    draft = HeroDraft.objects.prefetch_related(
                        "draft_teams__tournament_team__captain",
                        "draft_teams__tournament_team__members",
                        "rounds",
                    ).get(id=self.draft_id)
                    broadcast_herodraft_state(draft, "draft_resumed")
                    log.debug(
                        f"Broadcast draft_resumed for draft {self.draft_id}"
                    )
                except Exception as e:
                    log.error(
                        f"Failed to broadcast draft_resumed for draft {self.draft_id}: {e}"
                    )

            return transitioned

        return await check_and_resume()

    async def check_captain_heartbeats(self):
        from django.db import transaction

        from app.broadcast import broadcast_herodraft_state
        from app.models import DraftTeam, HeroDraft, HeroDraftEvent, HeroDraftState

        @database_sync_to_async
        def check_and_handle_stale():
            r = get_redis_client()
            now = time.time()
            stale_captain = None

            try:
                draft = HeroDraft.objects.prefetch_related(
                    "draft_teams__tournament_team__captain"
                ).get(id=self.draft_id)
            except HeroDraft.DoesNotExist:
                return None

            if draft.state != HeroDraftState.DRAFTING:
                return None

            for draft_team in draft.draft_teams.all():
                captain = draft_team.tournament_team.captain
                if not captain:
                    continue

                heartbeat_key = self.get_heartbeat_key(captain.id)
                last_heartbeat = r.get(heartbeat_key)

                if last_heartbeat is None:
                    if draft_team.is_connected:
                        log.warning(
                            f"Captain {captain.username} has no heartbeat but marked "
                            f"connected - treating as stale for draft {self.draft_id}"
                        )
                        stale_captain = (draft_team, captain)
                        break
                else:
                    heartbeat_age = now - float(last_heartbeat)
                    if heartbeat_age > HEARTBEAT_STALE_SECONDS:
                        log.warning(
                            f"Captain {captain.username} heartbeat stale "
                            f"({heartbeat_age:.1f}s) for draft {self.draft_id}"
                        )
                        stale_captain = (draft_team, captain)
                        break

            if not stale_captain:
                return None

            draft_team, captain = stale_captain

            with transaction.atomic():
                draft = HeroDraft.objects.select_for_update().get(
                    id=self.draft_id
                )
                if draft.state != HeroDraftState.DRAFTING:
                    return None

                draft_team = DraftTeam.objects.select_for_update().get(
                    id=draft_team.id
                )
                draft_team.is_connected = False
                draft_team.save()

                draft.state = HeroDraftState.PAUSED
                draft.paused_at = timezone.now()
                draft.save()

                HeroDraftEvent.objects.create(
                    draft=draft,
                    event_type="captain_disconnected",
                    draft_team=draft_team,
                    metadata={
                        "user_id": captain.id,
                        "username": captain.username,
                        "reason": "heartbeat_stale",
                    },
                )
                HeroDraftEvent.objects.create(
                    draft=draft,
                    event_type="draft_paused",
                    draft_team=draft_team,
                    metadata={"reason": "heartbeat_stale"},
                )
                log.info(
                    f"HeroDraft {self.draft_id} paused: captain "
                    f"{captain.username} heartbeat stale"
                )

            try:
                draft = HeroDraft.objects.prefetch_related(
                    "draft_teams__tournament_team__captain",
                    "draft_teams__tournament_team__members",
                    "rounds",
                ).get(id=self.draft_id)
                broadcast_herodraft_state(
                    draft, "draft_paused", draft_team=draft_team
                )
            except Exception as e:
                log.error(
                    f"Failed to broadcast draft_paused for draft {self.draft_id}: {e}"
                )

            return captain.username

        return await check_and_handle_stale()

    def should_continue_ticking(self) -> tuple[bool, str]:
        """Synchronous — called from within database_sync_to_async wrapper."""
        from app.models import HeroDraft, HeroDraftState

        try:
            draft = HeroDraft.objects.get(id=self.draft_id)
            if draft.state not in (
                HeroDraftState.DRAFTING,
                HeroDraftState.RESUMING,
            ):
                return False, f"draft_state_{draft.state}"
        except HeroDraft.DoesNotExist:
            return False, "draft_not_found"

        if draft.state == HeroDraftState.RESUMING:
            return True, ""

        conn_count = self.get_connection_count()
        if conn_count <= 0:
            return False, "no_connections"

        return True, ""


# ============================================================
# Backward-compatible module-level functions
# ============================================================
# All existing import sites (consumers.py etc.) use these.
# They delegate to HeroDraftTickService instances.


def increment_connection_count(draft_id: int) -> int:
    """Increment WebSocket connection count for a draft. Returns new count."""
    svc = HeroDraftTickService(draft_id)
    return svc.increment_connection_count()


def decrement_connection_count(draft_id: int) -> int:
    """Decrement WebSocket connection count for a draft. Returns new count."""
    svc = HeroDraftTickService(draft_id)
    return svc.decrement_connection_count()


def get_connection_count(draft_id: int) -> int:
    """Get current WebSocket connection count for a draft."""
    svc = HeroDraftTickService(draft_id)
    return svc.get_connection_count()


def start_tick_broadcaster(draft_id: int) -> bool:
    """Start the tick broadcaster for a draft.

    Returns True if started, False if already running elsewhere.
    """
    svc = HeroDraftTickService(draft_id)
    return svc.start()


def stop_tick_broadcaster(draft_id: int):
    """Stop the tick broadcaster for a draft."""
    svc = HeroDraftTickService(draft_id)
    svc.stop()


async def broadcast_tick(draft_id: int):
    """Broadcast current timing state to all connected clients."""
    svc = HeroDraftTickService(draft_id)
    return await svc.broadcast_tick()


async def check_timeout(draft_id: int):
    """Check if current round has timed out and auto-pick if needed."""
    svc = HeroDraftTickService(draft_id)
    return await svc.check_timeout()


async def check_resume_countdown(draft_id: int):
    """Check if RESUMING countdown is complete and transition to DRAFTING."""
    svc = HeroDraftTickService(draft_id)
    return await svc.check_resume_countdown()


async def check_captain_heartbeats(draft_id: int):
    """Check if any captain's heartbeat is stale and trigger disconnect if so."""
    svc = HeroDraftTickService(draft_id)
    return await svc.check_captain_heartbeats()


def should_continue_ticking(draft_id: int, r=None) -> tuple[bool, str]:
    """Check if tick loop should continue.

    The `r` parameter is accepted for backward compat but ignored
    (the service gets its own Redis client internally).
    """
    svc = HeroDraftTickService(draft_id)
    return svc.should_continue_ticking()
```

**Step 2: Verify ALL existing imports still work**

Check that all import sites resolve. The test file imports:
- `from app.tasks.herodraft_tick import (_active_tick_tasks, _lock, broadcast_tick, check_timeout, get_redis_client, should_continue_ticking, start_tick_broadcaster, stop_tick_broadcaster)`

And `consumers.py` imports:
- `from app.tasks.herodraft_tick import (start_tick_broadcaster, increment_connection_count, decrement_connection_count, get_connection_count, get_redis_client)`

All of these are now either module-level wrapper functions or re-exports from `draft_tick.py`. The `_active_tick_tasks` dict uses `(draft_type, draft_id)` tuple keys — existing tests that check `self.draft.id in _active_tick_tasks` will need to use `("herodraft", self.draft.id)` instead. **This is an accepted test update, not a backward-compat break** (tests are internal, not a public API).

**Step 3: Commit**

```
refactor: rewrite herodraft_tick.py as HeroDraftTickService subclass

Preserves all legacy Redis key patterns and module-level function
signatures for backward compatibility. Zero behavior change.
```

---

### Task 12: Write tests for new models and signal

**Files:**
- Create: `backend/app/tests/test_tournament_config.py`

**Step 1: Write tests**

```python
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from app.models import (
    CustomUser,
    Draft,
    DraftRound,
    HeroDraft,
    HeroDraftPauseEvent,
    HeroDraftRound,
    Tournament,
    TournamentConfig,
)


class TournamentConfigTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=timezone.now(),
        )

    def test_config_auto_created_on_tournament_create(self):
        """Signal should auto-create TournamentConfig for new tournaments."""
        self.assertTrue(
            TournamentConfig.objects.filter(tournament=self.tournament).exists()
        )

    def test_config_defaults(self):
        """Config should have sensible defaults."""
        config = self.tournament.config
        self.assertEqual(config.grace_time_ms, 30000)
        self.assertEqual(config.reserve_time_ms, 90000)
        self.assertEqual(config.resume_countdown_ms, 3000)
        self.assertFalse(config.enable_pick_timer)
        self.assertTrue(config.pause_on_disconnect)
        self.assertEqual(config.pick_timeout_strategy, "random")

    def test_config_str(self):
        config = self.tournament.config
        self.assertIn("Test Tournament", str(config))

    def test_config_validation_grace_time_min(self):
        config = self.tournament.config
        config.grace_time_ms = 1000  # Below min of 5000
        with self.assertRaises(ValidationError):
            config.full_clean()

    def test_config_validation_grace_time_max(self):
        config = self.tournament.config
        config.grace_time_ms = 999999  # Above max of 120000
        with self.assertRaises(ValidationError):
            config.full_clean()

    def test_config_one_to_one(self):
        """Cannot create duplicate configs for same tournament."""
        with self.assertRaises(Exception):
            TournamentConfig.objects.create(tournament=self.tournament)


class PauseEventTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser", password="testpass"
        )

    def test_herodraft_pause_event_duration_closed(self):
        """Duration of a closed pause event should be resumed_at - paused_at."""
        from app.models import Game

        tournament = Tournament.objects.create(
            name="T", date_played=timezone.now()
        )
        game = Game.objects.create(tournament=tournament)
        draft = HeroDraft.objects.create(game=game)

        paused = timezone.now() - timedelta(minutes=5)
        resumed = paused + timedelta(minutes=2)

        pe = HeroDraftPauseEvent.objects.create(
            draft=draft,
            pause_type="manual",
            paused_by=self.user,
            paused_at=paused,
            resumed_at=resumed,
        )
        self.assertEqual(pe.duration, timedelta(minutes=2))

    def test_herodraft_pause_event_duration_open(self):
        """Duration of an open pause event should be now - paused_at."""
        from app.models import Game

        tournament = Tournament.objects.create(
            name="T", date_played=timezone.now()
        )
        game = Game.objects.create(tournament=tournament)
        draft = HeroDraft.objects.create(game=game)

        paused = timezone.now() - timedelta(minutes=3)
        pe = HeroDraftPauseEvent.objects.create(
            draft=draft,
            pause_type="disconnect",
            paused_at=paused,
        )
        # Open pause — duration should be approximately 3 minutes
        self.assertAlmostEqual(
            pe.duration.total_seconds(), 180, delta=5
        )

    def test_pause_event_str(self):
        from app.models import Game

        tournament = Tournament.objects.create(
            name="T", date_played=timezone.now()
        )
        game = Game.objects.create(tournament=tournament)
        draft = HeroDraft.objects.create(game=game)

        pe = HeroDraftPauseEvent.objects.create(
            draft=draft, pause_type="manual", paused_at=timezone.now()
        )
        self.assertIn("manual", str(pe))

    def test_round_fk_set_null_on_delete(self):
        """When a round is deleted, pause event round FK should become NULL."""
        from app.models import DraftTeam, Game, Team

        tournament = Tournament.objects.create(
            name="T", date_played=timezone.now()
        )
        game = Game.objects.create(tournament=tournament)
        draft = HeroDraft.objects.create(game=game)
        team = Team.objects.create(tournament=tournament, name="Team A")
        draft_team = DraftTeam.objects.create(
            draft=draft, tournament_team=team
        )
        round_obj = HeroDraftRound.objects.create(
            draft=draft,
            draft_team=draft_team,
            round_number=1,
            action_type="pick",
        )
        pe = HeroDraftPauseEvent.objects.create(
            draft=draft,
            pause_type="disconnect",
            paused_at=timezone.now(),
            round=round_obj,
        )
        round_obj.delete()
        pe.refresh_from_db()
        self.assertIsNone(pe.round)


class DraftPauseFieldsTests(TestCase):
    def test_draft_has_pause_fields(self):
        """Draft model should have pause fields."""
        tournament = Tournament.objects.create(
            name="T", date_played=timezone.now()
        )
        draft = Draft.objects.create(tournament=tournament)
        self.assertIsNone(draft.paused_at)
        self.assertIsNone(draft.resuming_until)
        self.assertFalse(draft.is_manual_pause)

    def test_draft_round_has_temporal_fields(self):
        """DraftRound model should have started_at and completed_at."""
        tournament = Tournament.objects.create(
            name="T", date_played=timezone.now()
        )
        draft = Draft.objects.create(tournament=tournament)
        user = CustomUser.objects.create_user(
            username="cap", password="pass"
        )
        round_obj = DraftRound.objects.create(
            draft=draft, captain=user, pick_number=1
        )
        self.assertIsNone(round_obj.started_at)
        self.assertIsNone(round_obj.completed_at)
        now = timezone.now()
        round_obj.started_at = now
        round_obj.save()
        round_obj.refresh_from_db()
        self.assertEqual(round_obj.started_at, now)
```

**Step 2: Run tests**

```bash
cd /home/kettle/git_repos/website/.worktrees/abstract-draft-pause && just test::run 'python manage.py test app.tests.test_tournament_config -v 2'
```

**Step 3: Commit**

```
test: add tests for TournamentConfig, PauseEvent, and Draft pause fields
```

---

### Task 13: Update existing tick tests for tuple keys and run regression suite

**Step 1: Update `_active_tick_tasks` assertions in `test_herodraft_tick.py`**

The `_active_tick_tasks` dict now uses `("herodraft", draft_id)` tuple keys instead of plain `draft_id` ints. Update all assertions in `backend/app/tests/test_herodraft_tick.py`:

- `self.assertIn(self.draft.id, _active_tick_tasks)` → `self.assertIn(("herodraft", self.draft.id), _active_tick_tasks)`
- `_active_tick_tasks.get(self.draft.id)` → `_active_tick_tasks.get(("herodraft", self.draft.id))`
- `_active_tick_tasks[self.draft.id]` → `_active_tick_tasks[("herodraft", self.draft.id)]`

**Step 2: Run existing tick tests**

```bash
cd /home/kettle/git_repos/website/.worktrees/abstract-draft-pause && just test::run 'python manage.py test app.tests.test_herodraft_tick -v 2'
```

Expected: All tests pass after the key format updates.

**Step 2: Run full test suite**

```bash
cd /home/kettle/git_repos/website/.worktrees/abstract-draft-pause && just test::run 'python manage.py test app.tests -v 2'
```

Expected: All tests pass. If any fail, debug and fix before committing.

**Step 3: TypeScript check**

```bash
cd /home/kettle/git_repos/website/.worktrees/abstract-draft-pause/frontend && npx tsc --noEmit
```

Expected: No new errors (pre-existing errors in bracketAPI, editForm, heroDraftStore, dotaconstants, playwright configs are known).

---

## Task Dependency Graph

```
Task 1 (TournamentConfig model)
  → Task 2 (PauseEvent models)
    → Task 3 (Draft/DraftRound fields)
      → Task 4 (Signal)
        → Task 5 (Admin)
          → Task 6 (Migrations)
            ├→ Task 7 (Serializer)  ─→ Task 8 (Views)
            ├→ Task 9 (Frontend schema)
            └→ Task 10 (DraftTickService base)  ─→ Task 11 (HeroDraftTickService)
                                                      ↓
            Task 12 (Tests) ← depends on all above
              → Task 13 (Regression tests)
```

**Parallelizable after Task 6:**
- Tasks 7+8 (serializer + views)
- Task 9 (frontend schema)
- Tasks 10+11 (tick service)

These three groups are independent and can run as parallel subagents.
