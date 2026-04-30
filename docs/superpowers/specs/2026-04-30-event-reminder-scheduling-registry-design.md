# Event reminder scheduling — declarative registry, dead-field cleanup, and series cascade fix

**Date:** 2026-04-30
**Status:** Approved (spec); awaiting implementation plan
**Owner:** Mark Paxson

## Summary

Replace the current ad-hoc reminder polling with a small declarative registry of `ScheduledReminder` entries so dead fields become impossible, edits to un-fired reminders are honored automatically, and adding a fifth reminder type is a one-line registry entry. Pair it with a row-level fix in `sync_future_events` that recomputes `scheduled_at` on series day/time edits to eliminate duplicate occurrences and "reminder posts on the wrong day" symptoms.

This is delivered as **three PRs across three releases** (deploy ordering matters — see Risks and rollout):

1. **PR-0 — Frontend Zod loosen.** One-file frontend change that makes `discord_subscriber_dm*` `.optional()` in Zod schemas. Ships first, isolates the frontend from PR-1's column drop. Sits on production one release cycle before PR-1.
2. **PR-1 — Registry + dead-field cleanup + idempotency guard.** Backend architectural change. Migrates the four wired reminders into a declarative registry (string task names, `current_app.send_task`); wires the announcement reminder (currently a dead field) as scheduled rather than immediate; drops the duplicate `discord_subscriber_dm*` fields (destructive migration); adds a pre-send lease pattern on `DiscordMessageLog` (full unique index on `(source, source_id)`, nullable `success`, `claimed_at` timestamp, plus a 5-min sweeper task) to prevent duplicate Discord sends under concurrent-task races; adds `invalidate_after_commit` calls in `sync_future_events` and `EventRepeaterViewSet.perform_update`; adds a CI test that fails when a `discord_*_hours` field has no consumer or when the slim serializer omits a registered field.
3. **PR-2 — Series row-level fixes + frontend cleanup.** `sync_future_events` recomputes `scheduled_at` on day/time/timezone edits (eliminates duplicate occurrences); frontend conditional rendering of signup-reminder fields on single events with Zod discriminated union; modal `defaultValues` cleanup; Playwright spec fix; TanStack Query invalidation gap closed.

**Edit-cascade policy:** **once fired, sticky.** Edits to reminder timing fields are honored on the next poll *only if the reminder has not already fired*. Already-fired reminders are never re-fired — preserves the "no double-DM" guarantee. Recovery from a wrongly-fired reminder is a manual admin action (delete the `DiscordMessageLog` row); the row-level fix in PR-2 prevents the most common cause (stale `scheduled_at` after series edits) from happening in the first place.

## Motivation

Three production bugs, three different root causes, one shared pattern:

1. **Dead reminder fields.** `discord_announcement_hours` is on the Event model and exposed in serializers/forms, but no scheduling code reads it. Same for `discord_subscriber_dm` / `discord_subscriber_dm_hours`. Users edit these expecting behavior; nothing happens.
2. **Edits don't take effect on un-fired reminders because the cascade is leaky.** When a series repeater is edited, only fields that `sync_future_events` happens to copy reach the upcoming occurrences. The cascade is hand-coded; adding a reminder field requires manually adding it to the cascade. Future occurrences not yet generated do inherit edits, but *current* upcoming occurrences may carry stale field values. (Note: the more visible "I changed signup reminder to 8 days before, but it never posts" incident is a *different* bug — that reminder had already fired against a stale `scheduled_at` from bug #3 below; the fix is the row-level `scheduled_at` recompute in PR-2, plus manual admin cleanup of the stuck log row.)
3. **Series day/time edits create duplicates and misaligned reminders.** `sync_future_events` cascades repeater field changes onto upcoming Event rows but does **not** recompute `scheduled_at` from the new `day_of_week`/`time_of_day`. Existing rows keep their old timestamps; the next hourly `generate_upcoming_events` task creates **new** rows at the new schedule. Reminders fire against the stale `scheduled_at`, producing the "wrong day" symptom, and admins see duplicate occurrences in the UI.

The shared root cause for all three: reminders are implemented as hand-coded branches in `check_event_reminders` with no central source of truth. Adding a new reminder requires touching the polling task, the cascade in `sync_future_events`, and the model fields, with no test that ties them together. The result is dead fields, missed cascades, and bug classes that recur each time someone adds a reminder type.

## Non-goals

- **Not switching to event-driven `apply_async(eta=...)` scheduling.** The current 30-second polling loop is fine; the bugs are not latency bugs. Keeping polling means `check_event_reminders`, `open_scheduled_signups`, and `generate_upcoming_events` continue to coexist coherently.
- **Not introducing `django-celery-beat` PeriodicTask rows per event.** Same reason — no payoff for the cost.
- **Not adding new reminder types in this PR.** The point is to make the existing four work correctly and make adding a fifth safe.
- **Not touching `open_scheduled_signups` or `generate_upcoming_events`.** Both remain polled, untouched.
- **No retroactive fix to events whose reminders already fired on the wrong day.** The fix prevents recurrence; manual cleanup of stuck `DiscordMessageLog` rows via Django admin is the recovery path.
- **No `superseded_at` column on `DiscordMessageLog` and no Activity Log UI changes.** Once-fired-stays-fired; the existing log gate is correct.
- **No UI work in PR-1 at all.** The single-event form-field hide lives in PR-2.

## Architecture

### The registry

A new module `events/scheduling/` owns reminder declarations and the fire logic.

```
events/scheduling/
├── __init__.py
├── registry.py         # ScheduledReminder dataclass + REMINDERS list
└── fire.py             # fire_due_reminders() — replaces check_event_reminders body
```

`ScheduledReminder` is the single declarative shape:

```python
@dataclass(frozen=True)
class ScheduledReminder:
    key: str                            # unique id, e.g. "announcement"
    task_name: str                      # full dotted celery task name,
                                        # e.g. "events.tasks.send_event_announcement"
    hours_field: str                    # "discord_announcement_hours"
    enabled_field: str                  # "discord_announcement"
    required_states: frozenset[str]     # {"upcoming", "signups_open"}
    log_source: str                     # DiscordMessageLog.source value
    requires_repeater: bool = False     # signup_reminder=True, others=False
```

**Why `task_name: str` and not `task: Callable`:** Celery dispatches by string name through its task registry, not by Python reference. Storing a callable risks circular imports (the registry module gets imported by `events.tasks`, which would re-import the registry) and silently breaks if the callable is referenced before it's been `@shared_task`-decorated. The fire path uses `current_app.send_task(reminder.task_name, args=[event_id])`, and a module-level validator in `registry.py` runs `current_app.tasks.get(name)` for every entry at import time and fails loud on missing task registrations.

The full `REMINDERS` list (PR-1):

```python
REMINDERS: list[ScheduledReminder] = [
    ScheduledReminder(
        key="announcement",
        task_name="events.tasks.send_event_announcement",
        hours_field="discord_announcement_hours",
        enabled_field="discord_announcement",
        required_states=frozenset({"upcoming", "signups_open"}),
        log_source="event_announcement",
    ),
    ScheduledReminder(
        key="signup_reminder",
        task_name="events.tasks.send_subscriber_notifications",
        hours_field="discord_signup_reminder_hours",
        enabled_field="discord_signup_reminder",
        required_states=frozenset({"signups_open"}),
        log_source="signup_reminder",
        requires_repeater=True,
    ),
    ScheduledReminder(
        key="attendance_reminder",
        task_name="events.tasks.send_attendance_reminder",  # extracted from inline code
        hours_field="discord_confirm_attendance_hours",
        enabled_field="discord_confirm_attendance",
        required_states=frozenset({"signups_open", "roll_call"}),
        log_source="attendance_reminder",
    ),
    ScheduledReminder(
        key="profile_reminder",
        task_name="events.tasks.send_profile_reminder",  # extracted from inline code
        hours_field="discord_profile_reminder_hours",
        enabled_field="discord_profile_reminder",
        required_states=frozenset({"signups_open"}),
        log_source="profile_reminder",
    ),
]
```

### Removing the `discord_subscriber_dm` dead fields

`discord_subscriber_dm` and `discord_subscriber_dm_hours` fields exist on `Event` and `EventRepeater` but no task consumes them — `send_subscriber_notifications` reads `discord_signup_reminder*` instead. The fields are a duplicate of the signup reminder concept; their continued existence is exactly the trap that produced the dead-field bug class.

PR-1 drops both fields via a destructive migration. If a second, distinct DM reminder is ever needed (e.g., a "signups closing soon" DM separate from the initial signup-reminder DM), it can be added cleanly as a new `ScheduledReminder` entry without resurrecting the old field names.

### Wiring up the announcement reminder (behavior change)

Today `send_event_announcement` is dispatched **immediately** via `notify_event_announced(event)` from four call sites: `EventViewSet.perform_update` (3 sites in `views.py`) and `services.py:generate_events_for_repeater`. The `discord_announcement_hours` field is therefore inert — by the time any scheduled fire path could run, the message log already gates it.

PR-1 makes the announcement scheduled like the other reminders:

- **Remove** the four `notify_event_announced(event)` call sites in `views.py` and `services.py`. The function itself can stay (or be deleted) — no other callers exist.
- **Add** `announcement` to `REMINDERS` so `fire_due_reminders` evaluates `scheduled_at - timedelta(hours=discord_announcement_hours)` on each 30-second poll.
- **Behavioral consequence:** users will no longer see announcements appear at event-save time. Announcements post `discord_announcement_hours` before the event (default 24h). This is the behavior the field was always named for.

The "Discord notice" code path (`source="event_notice"`, fired separately by `send_new_event_notification` via `notify_new_event`) is **not** affected — that's a distinct "an event was just created" notification, separate from the scheduled announcement embed. The notice continues to dispatch immediately.

### The fire path

`fire.py:fire_due_reminders()` replaces the body of `check_event_reminders`:

```python
from celery import current_app

def fire_due_reminders():
    now = datetime.now(tz.utc)
    for reminder in REMINDERS:
        candidates = _candidates_for(reminder)
        for ev in candidates:
            if not getattr(ev, reminder.enabled_field):
                continue
            if check_message_log_exists(reminder.log_source, ev.id):
                continue  # once-fired-stays-fired
            hours = getattr(ev, reminder.hours_field) or 0
            if hours <= 0:
                continue
            threshold = ev.scheduled_at - timedelta(hours=hours)
            if now >= threshold:
                current_app.send_task(reminder.task_name, args=[ev.id])
```

`_candidates_for(reminder)` builds the `get_events_list(...)` filter from the reminder's `required_states` and `requires_repeater`. The shape of the existing `get_events_list` API stays the same.

The existing `check_event_reminders` shared task name is preserved (still scheduled by celery beat at 30s), but its body becomes `fire_due_reminders()`. No celery beat schedule changes.

### Concurrency and idempotency (preventing double-fires)

The 30-second beat cadence creates an overlap window: if any per-event work in `fire_due_reminders` exceeds 30s — and the existing inline synchronous Discord HTTP calls (e.g., `tasks.py:816` in the attendance branch) can — then beat will queue a second `check_event_reminders` while the first is still running. Both will pass `check_message_log_exists` before either dispatches reminder tasks, and both dispatched tasks will send to Discord *before* either has written its log row. The unique-constraint-after-send pattern audit-dedups but does NOT prevent the duplicate Discord HTTP send: the message has already gone out by the time the second task hits `IntegrityError`.

**Fix in PR-1: pre-send "lease" pattern.** The dispatched reminder task acquires a lease row in `DiscordMessageLog` *before* sending to Discord. The unique constraint serializes the lease acquisition, so only one worker reaches the send step.

**Schema changes to `DiscordMessageLog`:**

1. **Make `success` nullable.** Three states: `NULL` = lease held, send in flight; `True` = sent successfully; `False` = send attempted and failed. Add a data migration to leave existing rows as-is (existing values are `True` or `False`).
2. **Full unique index on `(source, source_id)`.** Not partial. The constraint applies regardless of `success` value, so a pending lease, a successful send, or a failed send all block re-claim equally. A row with `success=False` from a prior failure intentionally blocks future fires until manually cleared — failed Discord sends are usually recoverable only by admin intervention anyway.
3. **Add `claimed_at = DateTimeField(null=True, db_index=True)`** so a sweeper can reclaim leases stuck in `NULL` state from worker crashes.

**Worker-side flow (each reminder task):**

```python
@shared_task
def send_event_announcement(event_id):
    event = get_event_for_task(event_id)
    if not event or not (event.discord_announcement and event.discord_announcement_channel_id):
        return f"event {event_id} not announceable"

    # Claim the lease BEFORE the Discord HTTP send.
    log_id = claim_discord_message_log(source="event_announcement", source_id=event.pk)
    if log_id is None:
        return f"event {event_id} announcement: lease held by another worker"

    try:
        result = build_announcement_v2(event)
        response = sync_send_embed_with_components_no_log(
            channel_id=event.discord_announcement_channel_id,
            embed=result["embed"],
            components=result.get("components"),
        )
        finalize_discord_message_log(log_id, success=True, message_id=response.get("id"))
    except Exception as e:
        finalize_discord_message_log(log_id, success=False, error=str(e))
        raise

    return f"sent announcement for event {event_id}"
```

**Two new helpers in `app.internal_client` (and corresponding internal API endpoints):**

- `claim_discord_message_log(source, source_id) -> int | None` — POSTs to `/api/internal/discord/message-log/claim/`. The Django-side handler does `DiscordMessageLog.objects.create(source=source, source_id=source_id, success=None, claimed_at=now())` inside a `try/except IntegrityError`. Returns the new log row's PK on success or `None` on conflict (lease already exists).
- `finalize_discord_message_log(log_id, *, success, message_id=None, error=None)` — POSTs to `/api/internal/discord/message-log/{log_id}/finalize/`. Updates the row to `success=True/False` plus the `message_id` or `error` payload.

**Refactor `sync_send_embed_with_components`:** split into:
- `sync_send_embed_with_components_no_log(...)` — does the Discord HTTP send only, returns the response. No logging side effect.
- The existing `sync_send_embed_with_components(..., source=..., source_id=...)` becomes a thin wrapper that calls `claim_discord_message_log`, then `_no_log`, then `finalize_discord_message_log`. Existing callers that don't use the lease pattern (one-off admin notifications, etc.) continue to work but get the lease semantics implicitly.

**Stale-lease sweeper (Celery beat task):**

A new beat task `sweep_stale_discord_leases` runs every 5 minutes:

```python
@shared_task
def sweep_stale_discord_leases():
    """Delete DiscordMessageLog rows stuck in NULL state for >5 minutes —
    almost always from a worker crash between claim and finalize."""
    threshold = timezone.now() - timedelta(minutes=5)
    deleted, _ = DiscordMessageLog.objects.filter(
        success__isnull=True, claimed_at__lt=threshold,
    ).delete()
    if deleted:
        logger.warning("Swept %d stale Discord leases", deleted)
    return deleted
```

This is added to `_beat_schedule` in `config/celery.py`.

**Worker safety configuration:**

- `task_acks_late=True` and `task_reject_on_worker_lost=True` on `check_event_reminders` — a worker that crashes mid-loop requeues the polling task instead of dropping it.
- Same flags on each reminder task. A worker crash between `claim_discord_message_log` and `finalize_discord_message_log` leaves a stale lease that the sweeper handles within 5 minutes.

**The `check_message_log_exists` short-circuit in `fire_due_reminders` stays.** It's a load-shedder — most polls hit it and skip dispatch entirely. The DB constraint is the correctness primitive; the cached-exists check is the optimization.

### How edits take effect

There is no separate sync function. Edits propagate naturally:

- **Direct event edit** (`EventViewSet.perform_update`): `serializer.save()` writes the new field values to the DB row. If the reminder has not yet fired, the next 30-second poll reads the new `discord_*_hours` / `enabled_field` / `scheduled_at` and evaluates the new threshold. If the reminder has already fired (`DiscordMessageLog` row exists), the poll skips it — no change.
- **Series repeater edit** (`EventRepeaterViewSet.perform_update` → `sync_future_events`): the existing cascade copies repeater fields onto upcoming Event rows. To make this generic and prevent the "missed cascade" trap, `sync_future_events` is updated to copy **the union of all `hours_field` and `enabled_field` values across `REMINDERS`** rather than the current hand-coded list. Adding a new reminder = adding to `REMINDERS`; the cascade picks it up automatically.
- **New occurrences from `generate_upcoming_events`**: inherit current repeater fields at generation time. No special handling needed.

The `DiscordMessageLog` table is unchanged. No new columns. No new helpers.

### Cache invalidation

`Event` and `EventRepeater` are cached by django-cacheops with a 60-minute TTL (`backend/backend/settings.py` `CACHEOPS` config). Cacheops auto-invalidates on `Model.save()` via post_save signals, but inside a `transaction.atomic()` block invalidation is deferred until commit, and there's a documented gotcha: bulk paths or paths that bypass the model's `save()` skip the signal entirely.

**Two specific fixes required in PR-1:**

1. **`sync_future_events` must call `invalidate_after_commit(event)` inside its per-row loop.** It currently uses `event.save(update_fields=[...])` inside `@transaction.atomic` with no explicit invalidation. With PR-1 expanding the cascade to the union of all `hours_field`/`enabled_field` values, a missed invalidation is exactly the stale-cache bug this spec is trying to prevent — the fire path would read pre-edit hours from a cached Event row.
2. **`EventRepeaterViewSet.perform_update` must call `invalidate_after_commit(*future_events)` after `sync_future_events` returns.** Currently it only invalidates the repeater itself; the cascaded child events keep their old cached representation until the 60-min TTL expires.

**Stale comment to fix:** the comment at `backend/events/tasks.py:742-743` says "DiscordMessageLog is NOT cached by cacheops, so queries always hit the DB." This is wrong — `discordbot.discordmessagelog` is in `CACHEOPS` with a 60-minute TTL. The comment misleads anyone reasoning about idempotency. Update the comment to: "DiscordMessageLog is cached by cacheops (60-min TTL); cacheops invalidates on insert, so the first successful write flips `exists=False` to `exists=True` immediately for all subsequent polls. Concurrent polls can still race — see DB unique constraint in the reminder tasks for the actual idempotency guarantee."

### Recovery from a wrongly-fired reminder

When PR-2's row-level fix is in place, the most common cause of wrong-day fires (stale `scheduled_at` after series day/time edits) is gone. For events where a reminder fired wrongly *before* PR-2 ships, recovery is manual: a site admin deletes the relevant `DiscordMessageLog` row in Django admin (`source=<reminder_log_source>, source_id=<event_id>`) and the next poll re-evaluates against the current threshold.

If admin-action recovery becomes a frequent ask, a follow-up PR can add a "Re-arm reminder" button to the Activity Log tab. Out of scope for these two PRs.

### CI guardrail — kills the bug class

A test in `events/tests/test_scheduling_registry.py` enforces three layered assertions:

1. **Model coverage:** every field on `Event` and `EventRepeater` matching `^discord_.*_hours$` appears as some `ScheduledReminder.hours_field`. Adding a new reminder field without a registry entry fails CI.
2. **Symmetric resolution:** every `enabled_field` referenced in `REMINDERS` resolves to a real boolean field on `Event`. Catches typos.
3. **Serializer round-trip:** every `hours_field` and `enabled_field` in `REMINDERS` is exposed by `EventSlimSerializer` (the serializer used by `get_events_list`, which the fire path consumes). Without this assertion, the registry could declare a reminder whose timing field is silently omitted from the slim serializer payload — `getattr(ev, hours_field)` would return the model default rather than the edited value, and the fire path would compute a threshold against the wrong number. This guardrail closes that gap.
4. **Task-name validity:** every `task_name` in `REMINDERS` resolves via `current_app.tasks.get(name)` at import time. Catches typos and missing `@shared_task` decorations before deploy.

This combined test would have prevented the `discord_announcement_hours` and `discord_subscriber_dm_hours` dead-field incidents and would prevent the slim-serializer trap that the registry refactor newly introduces.

### Edit-cascade policy

| Reminder state at edit time | Behavior |
|------------------------------|----------|
| Already fired (`DiscordMessageLog` row exists) | Sticky. Edit has no effect on this reminder for this event. Manual admin cleanup is the recovery path. |
| Not yet fired (no log row) | Next poll evaluates the new threshold. Fires when due. |
| Future series occurrences (not yet generated) | Inherit edited repeater fields via `sync_future_events` and `generate_upcoming_events`. |
| In-flight occurrence (UPCOMING/SIGNUPS_OPEN, partly fired) | Per-reminder: fired ones stay fired, un-fired ones pick up new timing on next poll. |

The rule reduces to: **once fired, sticky** and **edits affect un-fired reminders only**.

### Series row-level fixes (PR-2)

PR-2 is independent of the registry but fixes the third bug class. Frontend scope is non-trivial — the spec previously understated it.

**Backend:**

1. In `sync_future_events`, before saving each upcoming occurrence, recompute `scheduled_at` from the repeater's `day_of_week`/`time_of_day`/`timezone`/`starts_at` if any of those changed. Keep the (`event_repeater`, `scheduled_at`) unique constraint to detect collisions; on collision delete the old row and regenerate. This eliminates duplicates.
2. Reject `discord_signup_reminder` / `discord_signup_reminder_hours` in `EventSerializer.validate` for single events (no `event_repeater`). Single events have no subscriber list; the field has no honest meaning.

**Frontend (expanded per review):**

3. **Conditional rendering** of the signup-reminder fields in `frontend/app/components/events/DiscordConfigSection.tsx` — gate the existing UI block on `isRepeater === true`. Unmount (don't `display: none`) for accessibility correctness. The component already accepts an `isRepeater` prop (`EditEventModal.tsx:422` passes `false`, `EditRepeaterModal.tsx:504` passes `true`) — extend the existing prop, no new prop needed.
4. **Zod schema refinement** in `frontend/app/components/events/schemas.ts:246-247` — `discord_signup_reminder_hours` is currently `z.number().int().min(1)` unconditionally. Convert the relevant subset of `discordConfigSchema` to a discriminated union keyed on `event_repeater` (or use `superRefine`), so single events don't fail validation when the field is absent.
5. **`defaultValues` cleanup** in the four modal components that currently set the dropped/conditional fields: `EditEventModal.tsx:113-114`, `CreateEventModal.tsx:112-113`, `EditOrgDefaultsModal.tsx:105-106`, `EditRepeaterModal.tsx:118-119`. The dropped `discord_subscriber_dm*` keys (PR-1) come out entirely; the `discord_signup_reminder*` keys stay only in the repeater modals.
6. **Playwright spec update** at `frontend/tests/playwright/e2e/16-events/07-notification-dm.spec.ts:69-70` — currently references the dropped `discord_subscriber_dm[_hours]` fields and will fail once PR-1 ships. Either delete those assertions or rewrite to test `discord_notify_new_events` (the actual subscriber DM toggle).
7. **TanStack Query invalidation** in `useUpdateEventMutation` (`frontend/app/components/events/useEvent.ts:185-194`) — currently invalidates `['events']` and `['event', eventId]` but not `['event-discord', eventId]` (consumed at `DiscordLogSection.tsx:38` with 15s polling) or `['event-task-schedule', eventId]` (`TaskScheduleSection.tsx:35`). After the registry refactor, edits that change reminder timing should invalidate both keys so the new fires_at appears in the UI immediately rather than waiting for the next 15s poll.

PR-2 does not touch the registry. The registry's `requires_repeater=True` on `signup_reminder` already excludes single events from the fire path; PR-2 is about not lying to the user via the form and ensuring the UI reflects edits without a stale-data window.

## Files touched

### PR-0 (frontend Zod loosen — coordination prep)

Ships *before* PR-1 and isolates the frontend from PR-1's destructive migration. Without it, the moment PR-1 deploys, every `getEvent`/`getEventRepeaters` call fails Zod parse and the form/list explode.

- **Modified:** `frontend/app/components/events/schemas.ts` — make `discord_subscriber_dm` and `discord_subscriber_dm_hours` `.optional()` in `discordConfigSchema` (lines ~260-261) and `eventSchema` (lines ~84-85). Frontend tolerates either presence or absence.

PR-0 deploys, sits on production for one release cycle, then PR-1 ships.

### PR-1 (registry + dead-field cleanup + idempotency guard)

- **New:** `backend/events/scheduling/__init__.py`, `registry.py`, `fire.py`
- **Modified:** `backend/events/tasks.py` —
    - `check_event_reminders` body becomes `fire_due_reminders()`
    - Extract inline `attendance_reminder` and `profile_reminder` blocks into top-level shared tasks `send_attendance_reminder(event_id)` and `send_profile_reminder(event_id)` so they're registry-callable
    - Refactor each reminder task to use the lease pattern: `claim_discord_message_log(...)` before the Discord send; `finalize_discord_message_log(log_id, success=...)` after. None-return from claim means another worker has the lease — exit cleanly.
    - Update the stale comment at lines 742-743 to reflect that `DiscordMessageLog` IS cached by cacheops and that the lease pattern (not a partial index) is the idempotency primitive
    - Add `task_acks_late=True` and `task_reject_on_worker_lost=True` to `@shared_task` decorator on `check_event_reminders` and on each reminder task
- **Modified:** `backend/discordbot/utils.py` — split `sync_send_embed_with_components` into `_no_log` (Discord HTTP only) and the existing wrapper that adds claim/finalize around it. The wrapper signature stays the same so most callers don't need updates.
- **New:** `backend/app/internal_client.py` helpers — `claim_discord_message_log(source, source_id) -> int | None` and `finalize_discord_message_log(log_id, *, success, message_id=None, error=None)`.
- **Modified:** `backend/app/views/internal.py` — split the existing `create_discord_message_log` endpoint into `claim` (POST `/api/internal/discord/message-log/claim/`) and `finalize` (POST `/api/internal/discord/message-log/{id}/finalize/`). The claim endpoint catches `IntegrityError` and returns 409 Conflict; the worker helper returns `None` on 409.
- **New:** `sweep_stale_discord_leases` shared task in `backend/discordbot/tasks.py` (or wherever beat tasks live) — deletes `DiscordMessageLog` rows with `success IS NULL` and `claimed_at < now() - 5min`. Added to `_beat_schedule` in `backend/config/celery.py` at a 5-minute cadence.
- **Modified:** `backend/events/views.py` —
    - Remove the three `notify_event_announced(event)` call sites (lines ~376, ~420, ~551); the scheduled fire path replaces them
    - `EventRepeaterViewSet.perform_update` (lines ~190-195): after `sync_future_events` returns, call `invalidate_after_commit(*future_events)` so cascaded child events are not served stale from cacheops
- **Modified:** `backend/events/services.py` —
    - Remove the `notify_event_announced(event)` call in `generate_events_for_repeater` (line ~651)
    - Update `sync_future_events` (line ~662) to cascade the union of `REMINDERS` `hours_field` and `enabled_field` values rather than a hand-coded list
    - Add `invalidate_after_commit(event)` inside the per-row loop in `sync_future_events`
    - `sync_future_events` returns the list of touched events so callers can chain `invalidate_after_commit(*future_events)`
- **Modified or deleted:** `backend/events/discord/dispatch.py` — `notify_event_announced` has no remaining callers; either delete or leave for future use
- **Migrations:**
    - `0XXX_remove_subscriber_dm_fields.py` (destructive — drops `discord_subscriber_dm` and `discord_subscriber_dm_hours` from both `Event` and `EventRepeater`)
    - `0XXY_discord_message_log_lease_schema.py` — three operations: (1) `success` becomes nullable; (2) add `claimed_at = DateTimeField(null=True, db_index=True)`; (3) add full unique constraint on `(source, source_id)`. Use `CREATE UNIQUE INDEX CONCURRENTLY` if available to avoid blocking writes during deploy. Existing rows have `success` set to True/False and `claimed_at=NULL` — a one-line data migration is acceptable but not required since old rows already satisfy the new schema.
- **Modified:** `backend/events/serializers.py`, `backend/events/schemas.py` — remove the dropped subscriber-DM fields from all serializers and schema definitions; verify `EventSlimSerializer` exposes every `hours_field` and `enabled_field` referenced in `REMINDERS`
- **Modified:** `backend/config/celery.py` — confirm or add `task_acks_late` / `task_reject_on_worker_lost` defaults for the reminder queue (currently neither is set)
- **Deploy step (not a code file):** run `cacheops.invalidate_model(Event)` and `invalidate_model(EventRepeater)` post-migration to flush cached pre-migration model instances that contain the dropped fields. Add to deploy script or release runbook.
- **New tests:** `backend/events/tests/test_scheduling_registry.py` — model-coverage, symmetric-resolution, slim-serializer round-trip, and task-name validity assertions; fire-path integration tests for each reminder type including the new scheduled-announcement behavior; concurrency test that two parallel `fire_due_reminders` invocations result in exactly one `DiscordMessageLog` row (asserts the unique-constraint guard works)

### PR-2 (row-level fixes)

- **Modified:** `backend/events/services.py` — `sync_future_events` recomputes `scheduled_at` on day/time/timezone changes; collision handling
- **Modified:** `backend/events/serializers.py` — single-event validation rejecting `discord_signup_reminder*` when `event_repeater is None`
- **Modified:** `frontend/app/components/events/DiscordConfigSection.tsx` — gate the signup-reminder UI block on the existing `isRepeater` prop; unmount rather than `display: none`
- **Modified:** `frontend/app/components/events/schemas.ts` — convert `discordConfigSchema` to a discriminated union (or `superRefine`) keyed on `event_repeater` so single events validate without `discord_signup_reminder*`
- **Modified:** `frontend/app/components/events/EditEventModal.tsx`, `CreateEventModal.tsx`, `EditOrgDefaultsModal.tsx`, `EditRepeaterModal.tsx` — `defaultValues` cleanup so `discord_signup_reminder*` is only present in repeater paths
- **Modified:** `frontend/app/components/events/useEvent.ts` — `useUpdateEventMutation` invalidates `['event-discord', eventId]` and `['event-task-schedule', eventId]` in addition to existing keys
- **Modified:** `frontend/tests/playwright/e2e/16-events/07-notification-dm.spec.ts` — remove or rewrite assertions that reference the dropped `discord_subscriber_dm[_hours]` fields
- **New tests:** `backend/events/tests/test_sync_future_events_recompute.py`

## Decisions made

| # | Decision | Resolution |
|---|----------|-----------|
| Q1 | Subscriber-DM fields | **Drop** `discord_subscriber_dm` and `discord_subscriber_dm_hours`. Destructive migration in PR-1. |
| Q2 | Activity Log UI | No changes. Once-fired-stays-fired means no superseded state to display. |
| Q3 | Spec branch | Commit to `main`. |
| Q4 | PR split | Two PRs as designed (registry + row-level fixes), shipped independently. |
| Q5 | Scheduling model | **Stay polled.** Registry preserves the option to swap to `apply_async(eta=...)` later by replacing `fire_due_reminders` with a sync function that stores task IDs. No mixed-architecture cost paid speculatively. Threshold to revisit: ~1000+ concurrent active events sustained. |
| Q6 | `requires_repeater=True` on `signup_reminder` | Confirmed correct — single events have no subscribers. |
| Q7 | Edit policy | **Once fired, sticky.** Edits take effect on the next poll *only* for un-fired reminders. Already-fired reminders never re-fire. Recovery from wrong fires is manual admin cleanup of the `DiscordMessageLog` row. |
| Q8 | `hours_field <= 0 or None` | Skip in fire path — treats as "this reminder is disabled for this event." |
| Q9 | Announcement: immediate vs scheduled | **Scheduled** (Y). Remove immediate-dispatch `notify_event_announced` calls; the registry fires the announcement `discord_announcement_hours` before `scheduled_at`. The separate "new event notice" (`event_notice` log source) keeps its immediate dispatch — different concept. |
| Q10 | "Message interested users" UI binding | Verified. The toggle in `DiscordConfigSection.tsx:317` writes to `discord_notify_new_events` (a live, working field). PR-1 dropping `discord_subscriber_dm*` is correct — those fields really are dead. |
| Q11 | Idempotency primitive against polling overlap | **Pre-send lease pattern** (Option A). Full unique index on `DiscordMessageLog(source, source_id)`; `success` becomes nullable (`NULL` = lease held); reminder tasks `INSERT` the lease *before* the Discord HTTP send. The unique constraint serializes claim attempts, so only one worker reaches the send step — preventing duplicate Discord messages, not just duplicate audit rows. Stale leases (NULL >5 min, from worker crashes) are reaped by a beat-scheduled sweeper. Chosen over partial-index-after-send (which only audit-dedups), Redis distributed lock (adds Redis as correctness dependency), and `select_for_update` (would hold a row lock across the Discord HTTP call). |
| Q12 | Frontend deploy ordering for column drop | **PR-0 ships first**, loosens Zod schemas to `.optional()` for `discord_subscriber_dm*`. PR-1 ships one release later, drops the columns. Avoids the brief window where backend has dropped the field but frontend bundles still validate it as required. |
| Q13 | Cacheops invalidation on destructive migration | Post-deploy step: `invalidate_model(Event)` + `invalidate_model(EventRepeater)` to flush cached pre-migration model instances that contain the dropped fields. Added to PR-1 release runbook. |

## Risks and rollout

**Deploy ordering (three releases):**

1. **Release N — PR-0 (frontend Zod loosen).** Make `discord_subscriber_dm*` `.optional()` in Zod schemas. No backend changes. Risk: zero. Sits on production for one release cycle minimum to ensure all clients have the new bundle.
2. **Release N+1 — PR-1 (registry + dead-field drop + idempotency guard).** Backend-only. Adds the lease-pattern migration on `DiscordMessageLog` (full unique index via `CREATE UNIQUE INDEX CONCURRENTLY`, nullable `success`, `claimed_at` timestamp). Drops the `discord_subscriber_dm*` columns (destructive — backups required). Removes synchronous `notify_event_announced` dispatch. Adds the stale-lease sweeper to celery beat at 5-minute cadence.
3. **Release N+2 — PR-2 (row-level series fixes).** Backend `sync_future_events` recompute, frontend `DiscordConfigSection` conditional render, schema discriminated union, modal default cleanup, Playwright fix, query invalidation.

**Risks per release:**

- **PR-1 destructive migration** drops two columns each from `Event` and `EventRepeater`. Pre-deploy backup. No data loss since nothing reads these.
- **PR-1 schema migration on `DiscordMessageLog`** does three things: makes `success` nullable, adds `claimed_at`, and adds a full unique index on `(source, source_id)`. Each operation is additive or relaxing — safe under concurrent writes if `CREATE UNIQUE INDEX CONCURRENTLY` is used for the index step. Verify column name `success` is correct (it's confirmed at `discordbot/models.py:96`; note that other models like `DiscordTournamentLog` and `DiscordEventLog` also have `success` columns — the migration must explicitly target `discordbot.discordmessagelog`).
- **PR-1 worker config change** (`task_acks_late`, `task_reject_on_worker_lost`) — these are worker-level options, applied via `@shared_task(acks_late=True, reject_on_worker_lost=True)` decoration on `check_event_reminders`. Restart workers as part of deploy so the new options take effect.
- **PR-1 cacheops post-deploy step:** run `invalidate_model(Event)` + `invalidate_model(EventRepeater)` after migration to flush cached pre-migration instances. Add to deploy runbook.
- **Wiring up `discord_announcement_hours`** is a behavior change with two facets:
    - **The field becomes live** — production events with non-default values will fire announcements at the new timing. Worth a quick `SELECT id, discord_announcement_hours FROM events_event WHERE discord_announcement_hours <> 24 AND state IN ('upcoming', 'signups_open')` before deploy.
    - **Announcements no longer post immediately on save.** Anyone who relied on "I save the event, the announcement appears in Discord seconds later" will see a delay equal to `scheduled_at - discord_announcement_hours`. Worth a one-line note in the release announcement and a Discord ping to admin users. The "new event notice" (different message, different channel pattern) is unaffected — it still fires immediately.
- **In-flight task name coexistence.** Beat config is static in `config/celery.py` and deploys atomically with worker code. The risk window is rolling-deploy: new beat schedule loaded but some workers still running pre-PR-1 code that doesn't have `send_attendance_reminder` / `send_profile_reminder` registered. The mitigation is deploy ordering: **deploy workers across the full fleet first, then restart beat last.** With `task_acks_late=True` on the polling task, queued reminder tasks sit in the broker until *some* worker can pick them up — so a partial-fleet old-worker window gets the tasks consumed by new workers as soon as they're up. Confirm broker has sufficient `visibility_timeout` (default 1h on Redis) to bridge the rolling window. Recommended explicit assertion: set `broker_transport_options = {'visibility_timeout': 3600}` in `config/celery.py` if not already set.
- **Recovery for already-stuck reminders is manual.** PR-2 prevents new wrong-day fires; events whose reminders fired wrongly *before* this ships need admin intervention to clear the `DiscordMessageLog` row. This is acceptable scope per the chosen edit policy (Option B).

## Open questions

None. All eight decisions are resolved (see "Decisions made" above).
