"""Declarative reminder registry — single source of truth.

Adding a new reminder = one entry in REMINDERS plus the corresponding
@shared_task. The CI guardrails in tests/test_scheduling_registry.py verify
field coverage, task registration, and slim-serializer exposure.

Why `task_name: str` and not `task: Callable`:
Celery dispatches by string name through its task registry, not by Python
reference. Storing a callable risks circular imports (the registry module
gets imported by events.tasks, which would re-import the registry) and
silently breaks if the callable is referenced before it's been
@shared_task-decorated. The fire path uses
`current_app.send_task(reminder.task_name, args=[event_id])`.

Why no reminder_field_union helper:
DISCORD_CONFIG_FIELDS in events/services.py:536 is auto-built from
DiscordEventConfigMixin._meta.get_fields() and catches every reminder field
defined on the mixin. The CI guardrail RegistryMixinCoverageTest enforces
that registry fields stay on the mixin — so the existing sync_future_events
cascade automatically picks up new reminder fields.
"""

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class ScheduledReminder:
    key: str
    """Unique identifier (e.g. 'announcement', 'signup_reminder')."""

    task_name: str
    """Full dotted celery task name. Resolved via current_app.send_task."""

    hours_field: str
    """Name of the integer field on Event that controls 'fire N hours before'."""

    enabled_field: str
    """Name of the boolean field on Event that gates the reminder."""

    required_states: FrozenSet[str]
    """Event states in which this reminder is eligible."""

    log_source: str
    """DiscordMessageLog.source value used for idempotency dedup."""

    requires_repeater: bool = False
    """If True, fire path filters to events with event_repeater set."""


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
        task_name="events.tasks.send_attendance_reminder",
        hours_field="discord_confirm_attendance_hours",
        enabled_field="discord_confirm_attendance",
        required_states=frozenset({"signups_open", "roll_call"}),
        log_source="attendance_reminder",
    ),
    ScheduledReminder(
        key="profile_reminder",
        task_name="events.tasks.send_profile_reminder",
        hours_field="discord_profile_reminder_hours",
        enabled_field="discord_profile_reminder",
        required_states=frozenset({"signups_open"}),
        log_source="profile_reminder",
    ),
]
