# Event reminder scheduling — declarative registry, dead-field cleanup, and series cascade fix

**Date:** 2026-04-30
**Status:** Approved (spec); awaiting implementation plan
**Owner:** Mark Paxson

## Summary

Replace the current ad-hoc reminder polling with a small declarative registry of `ScheduledReminder` entries so dead fields become impossible, edits to un-fired reminders are honored automatically, and adding a fifth reminder type is a one-line registry entry. Pair it with a row-level fix in `sync_future_events` that recomputes `scheduled_at` on series day/time edits to eliminate duplicate occurrences and "reminder posts on the wrong day" symptoms.

This is delivered as **two PRs**:

1. **PR-1 — Registry + dead-field cleanup.** Architectural change. Migrates the four wired reminders into a registry, wires the announcement reminder (currently a dead field), drops the duplicate `discord_subscriber_dm*` fields, and adds a CI test that fails when a `discord_*_hours` field has no consumer.
2. **PR-2 — Series row-level fixes.** `sync_future_events` recomputes `scheduled_at` (or deletes-and-regenerates) on day/time/timezone edits; `discord_signup_reminder*` fields hidden on single events.

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
    task: Callable                      # the celery task to .delay()
    hours_field: str                    # "discord_announcement_hours"
    enabled_field: str                  # "discord_announcement"
    required_states: frozenset[str]     # {"upcoming", "signups_open"}
    log_source: str                     # DiscordMessageLog.source value
    requires_repeater: bool = False     # signup_reminder=True, others=False
```

The full `REMINDERS` list (PR-1):

```python
REMINDERS: list[ScheduledReminder] = [
    ScheduledReminder(
        key="announcement",
        task=send_event_announcement,
        hours_field="discord_announcement_hours",
        enabled_field="discord_announcement",
        required_states=frozenset({"upcoming", "signups_open"}),
        log_source="event_announcement",
    ),
    ScheduledReminder(
        key="signup_reminder",
        task=send_subscriber_notifications,
        hours_field="discord_signup_reminder_hours",
        enabled_field="discord_signup_reminder",
        required_states=frozenset({"signups_open"}),
        log_source="signup_reminder",
        requires_repeater=True,
    ),
    ScheduledReminder(
        key="attendance_reminder",
        task=send_attendance_reminder,  # extracted from inline code in check_event_reminders
        hours_field="discord_confirm_attendance_hours",
        enabled_field="discord_confirm_attendance",
        required_states=frozenset({"signups_open", "roll_call"}),
        log_source="attendance_reminder",
    ),
    ScheduledReminder(
        key="profile_reminder",
        task=send_profile_reminder,  # extracted from inline code
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
                reminder.task.delay(ev.id)
```

`_candidates_for(reminder)` builds the `get_events_list(...)` filter from the reminder's `required_states` and `requires_repeater`. The shape of the existing `get_events_list` API stays the same.

The existing `check_event_reminders` shared task name is preserved (still scheduled by celery beat at 30s), but its body becomes `fire_due_reminders()`. No celery beat schedule changes.

### How edits take effect

There is no separate sync function. Edits propagate naturally:

- **Direct event edit** (`EventViewSet.perform_update`): `serializer.save()` writes the new field values to the DB row. If the reminder has not yet fired, the next 30-second poll reads the new `discord_*_hours` / `enabled_field` / `scheduled_at` and evaluates the new threshold. If the reminder has already fired (`DiscordMessageLog` row exists), the poll skips it — no change.
- **Series repeater edit** (`EventRepeaterViewSet.perform_update` → `sync_future_events`): the existing cascade copies repeater fields onto upcoming Event rows. To make this generic and prevent the "missed cascade" trap, `sync_future_events` is updated to copy **the union of all `hours_field` and `enabled_field` values across `REMINDERS`** rather than the current hand-coded list. Adding a new reminder = adding to `REMINDERS`; the cascade picks it up automatically.
- **New occurrences from `generate_upcoming_events`**: inherit current repeater fields at generation time. No special handling needed.

The `DiscordMessageLog` table is unchanged. No new columns. No new helpers.

### Recovery from a wrongly-fired reminder

When PR-2's row-level fix is in place, the most common cause of wrong-day fires (stale `scheduled_at` after series day/time edits) is gone. For events where a reminder fired wrongly *before* PR-2 ships, recovery is manual: a site admin deletes the relevant `DiscordMessageLog` row in Django admin (`source=<reminder_log_source>, source_id=<event_id>`) and the next poll re-evaluates against the current threshold.

If admin-action recovery becomes a frequent ask, a follow-up PR can add a "Re-arm reminder" button to the Activity Log tab. Out of scope for these two PRs.

### CI guardrail — kills the bug class

A test in `events/tests/test_scheduling_registry.py` enumerates every model field on `Event` (and `EventRepeater`) matching the regex `^discord_.*_hours$` and asserts that each appears as some `ScheduledReminder.hours_field`. Adding a new reminder field without a registry entry fails CI.

Symmetric assertion: every `enabled_field` referenced in `REMINDERS` resolves to a real boolean field on `Event`. Catches typos.

This single test would have prevented the `discord_announcement_hours` and `discord_subscriber_dm_hours` dead-field incidents.

### Edit-cascade policy

| Reminder state at edit time | Behavior |
|------------------------------|----------|
| Already fired (`DiscordMessageLog` row exists) | Sticky. Edit has no effect on this reminder for this event. Manual admin cleanup is the recovery path. |
| Not yet fired (no log row) | Next poll evaluates the new threshold. Fires when due. |
| Future series occurrences (not yet generated) | Inherit edited repeater fields via `sync_future_events` and `generate_upcoming_events`. |
| In-flight occurrence (UPCOMING/SIGNUPS_OPEN, partly fired) | Per-reminder: fired ones stay fired, un-fired ones pick up new timing on next poll. |

The rule reduces to: **once fired, sticky** and **edits affect un-fired reminders only**.

### Series row-level fixes (PR-2)

PR-2 is independent of the registry but fixes the third bug class:

1. In `sync_future_events`, before saving each upcoming occurrence, recompute `scheduled_at` from the repeater's `day_of_week`/`time_of_day`/`timezone`/`starts_at` if any of those changed. Keep the (`event_repeater`, `scheduled_at`) unique constraint to detect collisions, and on collision delete the old row and regenerate. This eliminates duplicates.
2. Hide `discord_signup_reminder` and `discord_signup_reminder_hours` from single-event forms (frontend `EventForm` conditional on `event_repeater_id`) and reject them in `EventSerializer.validate` for single events. Single events have no subscriber list; the field has no honest meaning.
3. (`discord_subscriber_dm*` fields are dropped in PR-1, so no UI work is needed for them in PR-2.)

PR-2 does not touch the registry. The registry's `requires_repeater=True` on `signup_reminder` already excludes single events from the fire path; PR-2 is purely about not lying to the user via the form.

## Files touched

### PR-1 (registry + dead-field cleanup)

- **New:** `backend/events/scheduling/__init__.py`, `registry.py`, `fire.py`
- **Modified:** `backend/events/tasks.py` — `check_event_reminders` body becomes `fire_due_reminders()`; extract inline `attendance_reminder` and `profile_reminder` blocks into top-level shared tasks `send_attendance_reminder(event_id)` and `send_profile_reminder(event_id)` so they're registry-callable
- **Modified:** `backend/events/views.py` — remove the three `notify_event_announced(event)` call sites (lines ~376, ~420, ~551). The scheduled fire path replaces them.
- **Modified:** `backend/events/services.py` — remove the `notify_event_announced(event)` call in `generate_events_for_repeater` (line ~651); update `sync_future_events` to cascade the union of `REMINDERS` `hours_field` and `enabled_field` values rather than a hand-coded list
- **Modified or deleted:** `backend/events/discord/dispatch.py` — `notify_event_announced` has no remaining callers; either delete or leave for future use
- **Migration:** `0XXX_remove_subscriber_dm_fields.py` (destructive — drops `discord_subscriber_dm` and `discord_subscriber_dm_hours` from both `Event` and `EventRepeater`)
- **Modified:** `backend/events/serializers.py`, `backend/events/schemas.py` — remove the dropped subscriber-DM fields from all serializers and schema definitions
- **New tests:** `backend/events/tests/test_scheduling_registry.py` — registry coverage assertion (every `discord_*_hours` field on `Event`/`EventRepeater` is in some `ScheduledReminder`); fire-path integration tests for each reminder type, including the new scheduled-announcement behavior

### PR-2 (row-level fixes)

- **Modified:** `backend/events/services.py` — `sync_future_events` recomputes `scheduled_at` on day/time/timezone changes; collision handling
- **Modified:** `backend/events/serializers.py` — single-event validation rejecting `discord_signup_reminder*`
- **Modified:** `frontend/app/components/events/EventForm/*` — hide signup-reminder fields on single events
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

## Risks and rollout

- **Subscriber-DM field removal** is destructive — the migration drops two columns each from `Event` and `EventRepeater`. Backups + a "deploy-time release notes" check, but no data loss since nothing reads these.
- **Wiring up `discord_announcement_hours`** is a behavior change with two facets:
    - **The field becomes live** — production events with non-default values will fire announcements at the new timing. Worth a quick `SELECT id, discord_announcement_hours FROM events_event WHERE discord_announcement_hours <> 24 AND state IN ('upcoming', 'signups_open')` before deploy.
    - **Announcements no longer post immediately on save.** Anyone who relied on the timing of "I save the event, the announcement appears in Discord seconds later" will see a delay equal to `scheduled_at - discord_announcement_hours`. Worth a one-line note in the release announcement and possibly a Discord ping to admin users. The "new event notice" (different message, different channel pattern) is unaffected — it still fires immediately.
- **No `DiscordMessageLog` schema changes.** No worker-coordination risk.
- **Recovery for already-stuck reminders is manual.** PR-2 prevents new wrong-day fires; events whose reminders fired wrongly *before* this ships need admin intervention to clear the `DiscordMessageLog` row. This is acceptable scope per the chosen edit policy (Option B).

## Open questions

None. All eight decisions are resolved (see "Decisions made" above).
