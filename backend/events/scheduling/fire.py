"""Fire path — replaces the body of check_event_reminders.

Iterates the REMINDERS registry every 30 seconds (via celery beat). For each
candidate event in the right state, evaluates `now >= scheduled_at - lead`
(lead in hours or minutes) and dispatches the reminder task by name via
current_app.send_task.

Idempotency:
- The in-process check_message_log_exists short-circuit at the top of the
  loop is a load-shedder — most polls hit it and skip dispatch entirely.
- The DB-level partial unique constraint on
  DiscordMessageLog(source, source_id) WHERE success IS NOT FALSE is the
  actual correctness primitive: the reminder task's pre-send claim raises
  IntegrityError if two workers race past the cached exists() check.
- Stale leases (NULL >5min, False >1hr) are reaped by
  sweep_stale_discord_leases so transient failures don't permanently brick
  reminders.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from celery import current_app
from dateutil.parser import isoparse
from django.utils import timezone

from events.scheduling.registry import REMINDERS, ScheduledReminder


def fire_due_reminders() -> str:
    """Walk REMINDERS, dispatching tasks for each due-and-unfired reminder.

    Returns a status string for celery worker logs.
    """
    from app.internal_client import check_message_log_exists, get_events_list

    now = timezone.now()
    dispatched = 0

    for reminder in REMINDERS:
        candidates = _candidates_for(reminder, get_events_list)
        for ev in candidates:
            if not _ev_attr(ev, reminder.enabled_field):
                continue
            event_id = _ev_attr(ev, "id")
            if check_message_log_exists(reminder.log_source, event_id):
                continue  # once-fired-stays-fired (load-shedder)

            lead = reminder.lead_time(_ev_attr(ev, reminder.lead_field))
            if lead is None:
                continue

            scheduled_at = _parse_scheduled_at(_ev_attr(ev, "scheduled_at"))
            if scheduled_at is None:
                continue
            threshold = scheduled_at - lead
            if now >= threshold:
                # Look up the task by registered name and dispatch via
                # .delay(). Equivalent to current_app.send_task(name, args)
                # but plays better with CELERY_TASK_ALWAYS_EAGER in tests
                # (send_task goes through the result backend; .delay()
                # honors eager mode without needing a Redis backend).
                task = current_app.tasks.get(reminder.task_name)
                if task is None:
                    # Caught by RegistryGuardrailsTest.test_every_task_name_is_registered_with_celery
                    raise RuntimeError(
                        f"Reminder {reminder.key!r} task_name "
                        f"{reminder.task_name!r} is not registered with celery"
                    )
                task.delay(event_id)
                dispatched += 1

    return f"fire_due_reminders: dispatched={dispatched} reminders={len(REMINDERS)}"


def _candidates_for(
    reminder: ScheduledReminder,
    get_events_list: Callable[..., list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Build the get_events_list filter from the reminder's required_states.

    The internal client supports comma-separated `states` and the
    `has_repeater` boolean filter (used by the existing
    check_event_reminders inline branches we're replacing).
    """
    states_csv = ",".join(sorted(reminder.required_states))
    kwargs = {"states": states_csv}
    if reminder.requires_repeater:
        kwargs["has_repeater"] = "true"
    return get_events_list(**kwargs)


def _ev_attr(ev: object, name: str) -> Any:
    """Read an attribute off an event payload from get_events_list.

    The internal client returns dict-likes; support both dict and object access.
    """
    if isinstance(ev, dict):
        return ev.get(name)
    return getattr(ev, name, None)


def _parse_scheduled_at(value: str | datetime | None) -> datetime | None:
    """Parse the scheduled_at field — slim serializer returns ISO strings."""
    if value is None:
        return None
    if isinstance(value, str):
        return isoparse(value)
    return value
