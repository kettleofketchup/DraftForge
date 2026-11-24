# Event Reminder Scheduling

Maintainer reference for the declarative reminder registry, the pre-send lease pattern on `DiscordMessageLog`, and the realign-on-edit semantics for recurring event series.

## Why this exists

The previous implementation hardcoded each reminder type (announcement, signup reminder, attendance reminder, profile reminder) inline in `check_event_reminders`. That coupled the scheduler to the message-sending tasks, so adding a new reminder meant editing the scheduler. Three classes of bug followed:

- **Duplicate sends** — two beat workers both passing the in-process "already fired?" check before either wrote to `DiscordMessageLog`.
- **Stale upcoming events** — editing a series' day-of-week left rows on the old day while the hourly generator created new rows on the new day; reminders fired for both.
- **Dead fields** — `discord_announcement_hours` was wired in the model and serializer but never read by the scheduler.

The fix has three pieces, each documented below: a **registry** (single source of truth for reminders), a **lease pattern** (DB-level dedup primitive), and **realign-on-edit** (delete-then-regenerate when schedule fields change).

---

## Registry pattern

`backend/events/scheduling/registry.py` holds a `REMINDERS` list of `ScheduledReminder` dataclass entries. Each entry declares the reminder's celery task name, which `Event` boolean gates it, which integer field controls the lead time (`hours_field` for "fire N hours before" or `minutes_field` for "fire N minutes before", exactly one), which states it's eligible in, and the `DiscordMessageLog.source` value used for dedup.

```python
@dataclass(frozen=True)
class ScheduledReminder:
    key: str                       # e.g. "announcement"
    task_name: str                 # e.g. "events.tasks.send_event_announcement"
    enabled_field: str             # Event field that gates the reminder
    required_states: FrozenSet[str]
    log_source: str                # DiscordMessageLog.source for dedup
    hours_field: str | None = None    # Event field: "N hours before"
    minutes_field: str | None = None  # Event field: "N minutes before"
    requires_repeater: bool = False
```

`backend/events/scheduling/fire.py` walks the registry every 30 seconds (the `check-event-reminders` beat entry in `backend/config/celery.py`). For each reminder:

1. Query `get_events_list` filtered by `required_states` (and `has_repeater=true` when set).
2. For each candidate, evaluate `now >= scheduled_at - lead`, where `lead` comes from whichever of `hours_field` / `minutes_field` is set (`ScheduledReminder.lead_time`).
3. Short-circuit via `check_message_log_exists(source, event_id)` — an in-process load-shedder that skips most polls.
4. Dispatch by name: `current_app.tasks.get(reminder.task_name).delay(event_id)`.

### Why `task_name: str` and not `task: Callable`

Celery dispatches by string name through its task registry, not by Python reference. Storing a callable would risk circular imports (the registry gets imported by `events.tasks`, which would re-import the registry) and silently break if the callable were referenced before its `@shared_task` decorator ran.

### Why `task.delay()` and not `current_app.send_task()`

`send_task` always goes through the result backend, so `CELERY_TASK_ALWAYS_EAGER=True` (used in tests) doesn't honor it cleanly. Looking up the registered task object and calling `.delay()` is equivalent under normal celery and works under eager mode without needing a Redis backend.

### Adding a new reminder

1. Add a `@shared_task` to `backend/events/tasks.py` that takes `event_id`.
2. Append a `ScheduledReminder(...)` entry to `REMINDERS`.
3. Add the corresponding boolean + integer fields to `DiscordEventConfigMixin` (so `sync_future_events`'s field cascade picks them up automatically).

The CI guardrails in `backend/events/tests/test_scheduling_registry.py` enforce that every `task_name` is registered with celery, every `enabled_field` and lead field (`hours_field` or `minutes_field`) exists on the mixin, each entry sets exactly one lead field, every `discord_*_hours` / `discord_*_minutes` model field is registered, and every `log_source` is unique.

---

## Lease pattern on `DiscordMessageLog`

The in-process "already fired?" check in `fire.py` is a load-shedder, not a correctness primitive. Two workers can both pass it before either writes to the log. The DB-level guard is a **partial unique constraint** on `DiscordMessageLog`:

```python
# backend/discordbot/models.py
constraints = [
    models.UniqueConstraint(
        fields=["source", "source_id"],
        condition=models.Q(success__isnull=True) | models.Q(success=True),
        name="uniq_discord_message_log_source_event_when_pending_or_success",
    ),
]
```

`success` has three states:

| `success` | Meaning |
|-----------|---------|
| `NULL`    | Lease held — send is in flight |
| `True`    | Send succeeded |
| `False`   | Send failed (transient or permanent) — row is reclaimable |

The constraint covers `NULL` and `True` rows. Failed (`False`) rows are deliberately excluded so transient Discord errors don't permanently brick reminders.

### Send sequence

```
worker                                        DiscordMessageLog
  │
  │ 1. INSERT (source, source_id, channel_id, embed_data, success=NULL, claimed_at=now)
  │    → IntegrityError if another worker holds NULL or True for the same key
  ├──────────────────────────────────────────►
  │
  │ 2. POST to Discord
  │ ─────► api.discord.com
  │ ◄─────
  │
  │ 3. UPDATE WHERE id=...
  │    success=True, discord_message_id=..., status_code=200
  ├──────────────────────────────────────────►
```

If the worker crashes between step 1 and step 3, the `NULL` row stays — until the sweeper reaps it.

### Stale-lease sweeper

`backend/discordbot/tasks.py:sweep_stale_discord_leases` runs every 60 seconds via celery beat (`sweep-stale-discord-leases`). It deletes:

- `success IS NULL AND claimed_at < now - 5min` — worker crashed mid-send.
- `success = False AND claimed_at < now - 1h` — old failure aged out so polling can retry.

The 60-second cadence keeps total worker-crash recovery latency below ~1.5 minutes (5-minute sweep threshold + 30-second next reminder poll).

---

## Realign-on-edit

`backend/events/services.py:sync_future_events(repeater, *, realign_schedule=False)` propagates repeater changes to all `UPCOMING` events in the series. When `realign_schedule=True` it also deletes `UPCOMING` rows whose `scheduled_at` is no longer in the new occurrence set, then calls `generate_events_for_repeater` to fill any missing occurrences.

The caller — `EventRepeaterViewSet.perform_update` — snapshots the schedule fields before save and only requests realignment when one changed:

```python
schedule_fields = ("day_of_week", "time_of_day", "timezone", "starts_at", "frequency")
before = {f: getattr(serializer.instance, f) for f in schedule_fields}
repeater = serializer.save()
schedule_changed = any(before[f] != getattr(repeater, f) for f in schedule_fields)
future_events = sync_future_events(repeater, realign_schedule=schedule_changed)
invalidate_after_commit(repeater, *future_events)
```

Without this, editing a recurring series' `day_of_week` left stale `UPCOMING` rows on the old day while the next hourly `generate_upcoming_events` task created new rows on the new day — admins saw duplicates and reminders fired twice.

`sync_future_events` returns the list of touched events so the view can chain a single batched `invalidate_after_commit(repeater, *future_events)` instead of invalidating per row.

### What's not realigned

Events that have progressed past `UPCOMING` (signups already opened) are not touched. In-flight events keep their original schedule even if the repeater is later edited.

Rows with `Event.is_off_schedule = True` are excluded from **both** halves of `sync_future_events`: the realign delete skips them, so a schedule edit can't remove an extra session someone deliberately added, and the config cascade skips them, so a series edit can't overwrite the per-event values chosen for one. They are events the series only hosts.

Realign is also skipped wholesale when `repeater.is_active` is `False` — a paused series generates nothing, so realigning it would delete its remaining rows and put nothing back. The skip is logged as `realign_skipped_inactive_repeater`. The config cascade still runs for a paused series, so a rename while paused still reaches its upcoming events.

Deletes performed by realign go through `services.teardown_event`, not a bare queryset `.delete()`, so a row removed by a schedule edit also has its Discord scheduled event, `DiscordEvent` and linked tournament torn down instead of being left behind as a ghost.

---

## Single events vs recurring series

`discord_signup_reminder` DMs every subscriber of the series — a concept that doesn't exist for one-off events *(events created with no series)*. Two layers reject the invalid combination:

- **Backend** — `EventSerializer.validate` rejects `discord_signup_reminder=True` when `event_repeater` is `None` (`backend/events/serializers.py:336`).
- **Frontend** — `eventSchema.superRefine` mirrors the rule client-side, and `DiscordConfigSection` hides the toggle when `isRepeater={false}` (`frontend/app/components/events/schemas.ts`, `DiscordConfigSection.tsx`).

The other reminders (`discord_announcement`, `discord_confirm_attendance`, `discord_profile_reminder`, `discord_start_mention`) work on both single events and series.

### Start mention

`discord_start_mention` (registry key `start_mention`, `minutes_field="discord_start_mention_minutes"`, default 15) runs `events.tasks.send_start_mention` in `signups_open` and `roll_call`. It mentions the members in `discord_start_mention_scope` who have a Discord ID: `main` is the seat-holding main list without Maybe RSVPs; `all_active` (default) is every signup that is not cancelled, rejected or dropped. Mentions go out as replies to the signup post (inside the thread for forum posts), at most 80 per message and 2000 characters, with `allowed_mentions={"users": [...]}` so no role or `@everyone` ping can leak. One `start_mention` lease row covers every chunk; members skipped for having no Discord ID are counted in the `start_mention_sent` log line and the lease row's `response_data`. Staff can fire it from the task schedule; a second fire returns 409.

Start mention needs a signup post that has already been posted: signup posts on with a signup channel, or the pre-day announcement on with an announcement channel (the signup embed then goes in the announcement channel). Without one, `send_start_mention` logs `start_mention_no_signup_post`, writes no lease, and the dispatcher retries it on later ticks while the event is in `signups_open` or `roll_call`, so the mention can go out late or not at all. The event form's start-mention block warns when neither post is configured (or notes the announcement fallback) using the same rule as `has_signup_post` in `get_event_task_schedule`, and the task schedule marks `start_mention` as `misconfigured` with the reason in its description. Both judge the configuration, not whether a signup post actually exists.

### Off-schedule events attached to a series

`Event.is_off_schedule` marks a third case that is neither of the two above: an event that belongs to a series but was not generated by its schedule (`services.create_off_schedule_event`, reached via `POST /api/events/repeaters/{id}/create-event/`). It is **not** a one-off in the sense used above — `event_repeater` is set — so nothing in this document's reminder machinery treats it specially:

- `discord_signup_reminder` is valid on it, and `send_subscriber_notifications` DMs the series' subscribers as usual — `requires_repeater=True` in the registry is satisfied by `event_repeater`, which the flag does not affect.
- The Discord "Notify Me"/subscribe button and every other reminder in `REMINDERS` fire on their normal `scheduled_at - hours` schedule.
- `EventSerializer.validate` does not reject it, because its `event_repeater` is not `None`.

Nothing but `sync_future_events` branches on the flag (see [What's not realigned](#whats-not-realigned)); the serializers expose it read-only so the UI can badge the event. It is a *scheduling* discriminator, not a notification one.

---

## Beat schedule reference

| Beat entry | Cadence | Task |
|------------|---------|------|
| `check-event-reminders` | 30s | `events.tasks.check_event_reminders` → `fire_due_reminders()` |
| `sweep-stale-discord-leases` | 60s | `discordbot.tasks.sweep_stale_discord_leases` |
| `sync-discord-events` | 60s | `events.tasks.sync_discord_events` |
| `open-scheduled-signups-every-minute` | 60s | `events.tasks.open_scheduled_signups` |
| `generate-upcoming-events-hourly` | 1h | `events.tasks.generate_upcoming_events` |
| `cleanup-stale-events-hourly` | 1h | `events.tasks.cleanup_stale_events` |

See `backend/config/celery.py` for the full schedule.

---

## File map

| Concern | Location |
|---------|----------|
| Registry definition | `backend/events/scheduling/registry.py` |
| Fire path | `backend/events/scheduling/fire.py` |
| Reminder tasks | `backend/events/tasks.py` |
| Partial unique constraint | `backend/discordbot/models.py` (`DiscordMessageLog.Meta.constraints`) |
| Claim/finalize internal endpoints | `backend/app/views/internal.py` |
| Worker-side claim helpers | `backend/app/internal_client.py` |
| Stale-lease sweeper | `backend/discordbot/tasks.py:sweep_stale_discord_leases` |
| Realign-on-edit | `backend/events/services.py:sync_future_events`, `backend/events/views.py:EventRepeaterViewSet.perform_update` |
| Backend signup-reminder gate | `backend/events/serializers.py:EventSerializer.validate` |
| Frontend signup-reminder gate | `frontend/app/components/events/schemas.ts`, `DiscordConfigSection.tsx` |
| CI guardrails | `backend/events/tests/test_scheduling_registry.py` |
