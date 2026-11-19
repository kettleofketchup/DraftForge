"""CI guardrails for the ScheduledReminder registry.

These tests prevent the bug class that originally motivated the registry:
fields defined on the model, exposed in serializers, but with no scheduling
code reading them (the discord_announcement_hours and discord_subscriber_dm
dead-field incidents).
"""

import re
from datetime import timedelta

from celery import current_app
from django.test import TestCase

# Force-import the tasks module so @shared_task registrations populate
# current_app.tasks. Without this, Django's test runner may not have
# imported events.tasks, and the task-name validity assertion below
# would pass vacuously in CI but fail in production.
import events.tasks  # noqa: F401
from events.models import Event, EventRepeater
from events.scheduling.registry import REMINDERS, ScheduledReminder
from events.serializers import EventSlimSerializer

HOURS_FIELD_RE = re.compile(r"^discord_.*_hours$")
MINUTES_FIELD_RE = re.compile(r"^discord_.*_minutes$")


class RegistryGuardrailsTest(TestCase):
    def test_every_discord_hours_field_is_in_registry(self):
        """Every discord_*_hours field on Event/EventRepeater must be registered."""
        registered = {r.hours_field for r in REMINDERS if r.hours_field}
        self._assert_fields_registered(HOURS_FIELD_RE, registered, "hours")

    def test_every_discord_minutes_field_is_in_registry(self):
        """Every discord_*_minutes field on Event/EventRepeater must be registered."""
        registered = {r.minutes_field for r in REMINDERS if r.minutes_field}
        self._assert_fields_registered(MINUTES_FIELD_RE, registered, "minutes")

    def _assert_fields_registered(
        self, pattern: re.Pattern[str], registered: set[str], unit: str
    ) -> None:
        for model in (Event, EventRepeater):
            model_fields = {
                f.name
                for f in model._meta.get_fields()
                if hasattr(f, "name") and pattern.match(f.name)
            }
            missing = model_fields - registered
            self.assertEqual(
                missing,
                set(),
                f"{model.__name__} has unregistered discord_*_{unit} fields: "
                f"{missing}. Either add them to REMINDERS or drop them from "
                f"the model.",
            )

    def test_hours_fields_end_in_hours_and_minutes_fields_in_minutes(self):
        for r in REMINDERS:
            if r.hours_field:
                self.assertRegex(r.hours_field, HOURS_FIELD_RE)
            if r.minutes_field:
                self.assertRegex(r.minutes_field, MINUTES_FIELD_RE)

    def test_exactly_one_lead_field_required(self):
        base = {
            "key": "k",
            "task_name": "t",
            "enabled_field": "e",
            "required_states": frozenset({"signups_open"}),
            "log_source": "s",
        }
        with self.assertRaises(ValueError):
            ScheduledReminder(**base)
        with self.assertRaises(ValueError):
            ScheduledReminder(**base, hours_field="h", minutes_field="m")
        self.assertEqual(ScheduledReminder(**base, hours_field="h").lead_field, "h")
        self.assertEqual(ScheduledReminder(**base, minutes_field="m").lead_field, "m")

    def test_lead_time_uses_the_set_unit(self):
        base = {
            "key": "k",
            "task_name": "t",
            "enabled_field": "e",
            "required_states": frozenset({"signups_open"}),
            "log_source": "s",
        }
        hourly = ScheduledReminder(**base, hours_field="h")
        minutely = ScheduledReminder(**base, minutes_field="m")
        self.assertEqual(hourly.lead_time(2), timedelta(hours=2))
        self.assertEqual(minutely.lead_time(15), timedelta(minutes=15))
        for value in (None, 0, -5):
            self.assertIsNone(hourly.lead_time(value))
            self.assertIsNone(minutely.lead_time(value))

    def test_every_enabled_field_resolves(self):
        """Every reminder.enabled_field must be a real boolean on Event."""
        event_fields = {f.name for f in Event._meta.get_fields() if hasattr(f, "name")}
        for r in REMINDERS:
            self.assertIn(
                r.enabled_field,
                event_fields,
                f"Reminder {r.key!r} enabled_field {r.enabled_field!r} not on Event",
            )

    def test_every_lead_field_resolves(self):
        event_fields = {f.name for f in Event._meta.get_fields() if hasattr(f, "name")}
        for r in REMINDERS:
            self.assertIn(
                r.lead_field,
                event_fields,
                f"Reminder {r.key!r} lead field {r.lead_field!r} not on Event",
            )

    def test_every_lead_and_enabled_field_in_slim_serializer(self):
        """Fire path reads slim payloads; every lead/enabled field must be exposed."""
        exposed = set(EventSlimSerializer.Meta.fields)
        for r in REMINDERS:
            self.assertIn(
                r.lead_field,
                exposed,
                f"EventSlimSerializer missing {r.lead_field!r} for {r.key!r}",
            )
            self.assertIn(
                r.enabled_field,
                exposed,
                f"EventSlimSerializer missing {r.enabled_field!r} for {r.key!r}",
            )

    def test_every_task_name_is_registered_with_celery(self):
        """Every reminder.task_name must resolve via current_app.tasks.get."""
        for r in REMINDERS:
            task = current_app.tasks.get(r.task_name)
            self.assertIsNotNone(
                task,
                f"Reminder {r.key!r} task_name {r.task_name!r} is not a "
                f"registered celery task. Check the @shared_task decorator "
                f"and module path.",
            )

    def test_keys_are_unique(self):
        keys = [r.key for r in REMINDERS]
        self.assertEqual(len(keys), len(set(keys)), "Duplicate reminder keys")

    def test_log_sources_are_unique(self):
        sources = [r.log_source for r in REMINDERS]
        self.assertEqual(len(sources), len(set(sources)), "Duplicate log_source values")


class RegistryMixinCoverageTest(TestCase):
    """Ensure every reminder field is on DiscordEventConfigMixin so the
    existing sync_future_events cascade catches it.

    sync_future_events iterates DISCORD_CONFIG_FIELDS, which is
    auto-built from DiscordEventConfigMixin._meta.get_fields(). A reminder
    field added outside the mixin would be silently missed by the cascade.
    """

    def test_every_reminder_field_is_on_discord_event_config_mixin(self):
        from events.models import DiscordEventConfigMixin

        mixin_field_names = {
            f.name
            for f in DiscordEventConfigMixin._meta.get_fields()
            if hasattr(f, "name")
        }
        for r in REMINDERS:
            self.assertIn(
                r.lead_field,
                mixin_field_names,
                f"Reminder {r.key!r} lead field {r.lead_field!r} not on "
                f"DiscordEventConfigMixin — sync_future_events cascade would "
                f"silently miss it.",
            )
            self.assertIn(
                r.enabled_field,
                mixin_field_names,
                f"Reminder {r.key!r} enabled_field {r.enabled_field!r} not "
                f"on DiscordEventConfigMixin.",
            )
