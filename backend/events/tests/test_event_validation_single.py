"""EventSerializer rejects discord_signup_reminder=True on single events.

Single events have no subscriber list (subscriptions are a series-level
concept on EventRepeater), so the signup_reminder DM fields have no
honest meaning for them. Backend rejection is the source of truth — the
frontend conditional render in Task 2.3 is UX, but a client that bypasses
it should still get a 400.
"""

from django.test import TestCase

from events.serializers import EventSerializer
from events.tests.test_discord_tasks import _DiscordTaskTestCase


class EventSingleEventSignupReminderRejectionTest(_DiscordTaskTestCase):
    def test_signup_reminder_rejected_when_event_repeater_is_none(self):
        # Use the existing self.event (no event_repeater) and try to enable
        # discord_signup_reminder via a partial update
        serializer = EventSerializer(
            self.event,
            data={"discord_signup_reminder": True},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("discord_signup_reminder", serializer.errors)

    def test_signup_reminder_accepted_when_event_repeater_set(self):
        from datetime import time, timedelta
        from django.utils import timezone

        from events.models import EventRepeater

        repeater = EventRepeater.objects.create(
            organization=self.event.organization,
            name="Test Repeater",
            frequency="weekly",
            day_of_week=1,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=timezone.now().date() - timedelta(days=1),
        )
        # Re-attach the event to the repeater so the validator sees it
        self.event.event_repeater = repeater
        self.event.save()

        serializer = EventSerializer(
            self.event,
            data={"discord_signup_reminder": True},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_signup_reminder_false_accepted_on_single_events(self):
        # Setting it explicitly False on a single event is fine — there's
        # nothing to reject.
        serializer = EventSerializer(
            self.event,
            data={"discord_signup_reminder": False},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
