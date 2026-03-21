from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, Organization
from events.models import Event, EventRepeater
from events.serializers import EventSerializer


class EventRepeaterNameSerializerTest(TestCase):
    """Test that EventSerializer includes event_repeater_name."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser", password="testpass"
        )
        self.org = Organization.objects.create(name="Test Org", owner=self.user)

    def test_event_repeater_name_null_when_no_repeater(self):
        event = Event.objects.create(
            organization=self.org,
            name="Standalone Event",
            scheduled_at=timezone.now(),
        )
        serializer = EventSerializer(event)
        self.assertIn("event_repeater_name", serializer.data)
        self.assertIsNone(serializer.data["event_repeater_name"])

    def test_event_repeater_name_present(self):
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly Inhouse",
            frequency="weekly",
            day_of_week=3,
            time_of_day="19:00:00",
            starts_at="2026-01-01",
        )
        event = Event.objects.create(
            organization=self.org,
            event_repeater=repeater,
            name="Week 12 Inhouse",
            scheduled_at=timezone.now(),
        )
        serializer = EventSerializer(event)
        self.assertEqual(serializer.data["event_repeater_name"], "Weekly Inhouse")
