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
from datetime import timedelta
from typing import Any, FrozenSet


@dataclass(frozen=True)
class ScheduledReminder:
    key: str
    """Unique identifier (e.g. 'announcement', 'signup_reminder')."""

    task_name: str
    """Full dotted celery task name. Resolved via current_app.send_task."""

    enabled_field: str
    """Name of the boolean field on Event that gates the reminder."""

    required_states: FrozenSet[str]
    """Event states in which this reminder is eligible."""

    log_source: str
    """DiscordMessageLog.source value used for idempotency dedup."""

    hours_field: str | None = None
    """Integer field on Event that controls 'fire N hours before'."""

    minutes_field: str | None = None
    """Integer field on Event that controls 'fire N minutes before'."""

    requires_repeater: bool = False
    """If True, fire path filters to events with event_repeater set."""

    def __post_init__(self) -> None:
        if (self.hours_field is None) == (self.minutes_field is None):
            raise ValueError(
                f"Reminder {self.key!r}: set exactly one of hours_field or minutes_field"
            )

    @property
    def lead_field(self) -> str:
        if self.hours_field is not None:
            return self.hours_field
        assert self.minutes_field is not None
        return self.minutes_field

    def lead_time(self, value: Any) -> timedelta | None:
        """Lead time for the field's value, or None when unset or not positive."""
        amount = value or 0
        if amount <= 0:
            return None
        if self.hours_field is not None:
            return timedelta(hours=amount)
        return timedelta(minutes=amount)


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
    ScheduledReminder(
        key="start_mention",
        task_name="events.tasks.send_start_mention",
        minutes_field="discord_start_mention_minutes",
        enabled_field="discord_start_mention",
        required_states=frozenset({"signups_open", "roll_call"}),
        log_source="start_mention",
    ),
]
