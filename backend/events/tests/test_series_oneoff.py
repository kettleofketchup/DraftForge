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
