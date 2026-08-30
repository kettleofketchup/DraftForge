"""One-off (off-schedule) events attached to a series, and series reactivation."""

from datetime import time, timedelta
from unittest.mock import patch

from django.utils import timezone as tz
from rest_framework.test import APIClient

from events.constants import EventState, RepeatFrequency
from events.models import Event, EventRepeater
from events.serializers import EventSerializer
from events.tests.base import EventTestCase


class OffScheduleFieldTest(EventTestCase):
    def test_event_defaults_to_on_schedule(self):
        self.assertFalse(self.event.is_off_schedule)

    def test_serializer_exposes_field_read_only(self):
        self.assertIn("is_off_schedule", EventSerializer.Meta.fields)
        self.assertIn("is_off_schedule", EventSerializer.Meta.read_only_fields)


class RepeaterCopyFieldsTest(EventTestCase):
    def _create_repeater(self, **kwargs):
        defaults = dict(
            organization=self.org,
            name="Sunday Turbo",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=tz.now().date(),
            created_by=self.admin,
        )
        defaults.update(kwargs)
        return EventRepeater.objects.create(**defaults)

    @patch("events.services.notify_create_discord_event")
    @patch("events.services.notify_new_event")
    def test_generation_inherits_discord_tournament_fields(self, _notify, _create):
        # Both fields default True on BOTH models, so the repeater must be set
        # away from the default or the assertion passes without the fix.
        repeater = self._create_repeater(
            discord_send_draft_link=False,
            discord_send_herodraft_link=False,
        )
        from events.services import generate_events_for_repeater

        created = generate_events_for_repeater(repeater)
        self.assertTrue(created)
        for event in created:
            self.assertFalse(event.discord_send_draft_link)
            self.assertFalse(event.discord_send_herodraft_link)
