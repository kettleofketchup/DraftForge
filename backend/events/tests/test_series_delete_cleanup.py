"""Deleting an event series (EventRepeater) must clean up its future events and
their live Discord scheduled events, so the every-60s sync_discord_events task
can't resurrect them as "ghost" events.

Regression for: deleted series kept generating ghost Discord events because
EventRepeaterViewSet was a plain ModelViewSet (hard delete, Event.event_repeater
SET_NULL) with no teardown, and nothing ever DELETEs the live Discord event.
"""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone as tz
from rest_framework.test import APIClient

from discordbot.models import DiscordEvent
from events.constants import EventState, RepeatFrequency
from events.models import Event, EventRepeater
from events.tests.base import EventTestCase


class SeriesDeleteCleanupTest(EventTestCase):
    def setUp(self):
        self.client = APIClient()
        self.org.discord_server_id = "734185035623825559"
        self.org.save(update_fields=["discord_server_id"])

        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Sunday Turbo Tournament",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day="18:00",
            starts_at=tz.now().date(),
            created_by=self.admin,
        )

        # A future, still-active occurrence with a live Discord scheduled event.
        self.future_event = Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Sunday Turbo Tournament",
            scheduled_at=tz.now() + timedelta(days=5),
            state=EventState.UPCOMING,
            discord_create_event=True,
        )
        self.discord_event = DiscordEvent.objects.create(
            event=self.future_event,
            guild_id="734185035623825559",
            scheduled_event_id="1529289108529352788",
        )

        # A past occurrence — must be preserved (orphaned), not deleted.
        self.past_event = Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Sunday Turbo Tournament",
            scheduled_at=tz.now() - timedelta(days=5),
            state=EventState.COMPLETED,
        )

    @patch("events.tasks.delete_discord_scheduled_event")
    def test_delete_series_removes_future_events_and_discord(self, mock_delete_task):
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"/api/events/repeaters/{self.repeater.pk}/")
        self.assertEqual(resp.status_code, 204, resp.content)

        # Series gone.
        self.assertFalse(EventRepeater.objects.filter(pk=self.repeater.pk).exists())
        # Future occurrence + its Discord row gone.
        self.assertFalse(Event.objects.filter(pk=self.future_event.pk).exists())
        self.assertFalse(DiscordEvent.objects.filter(pk=self.discord_event.pk).exists())
        # Live Discord scheduled event deletion was dispatched.
        mock_delete_task.delay.assert_called_once_with(
            "734185035623825559", "1529289108529352788"
        )
        # Past occurrence preserved, now orphaned.
        self.past_event.refresh_from_db()
        self.assertIsNone(self.past_event.event_repeater_id)

    @patch("events.tasks.delete_discord_scheduled_event")
    def test_delete_single_event_deletes_live_discord_event(self, mock_delete_task):
        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"/api/events/{self.future_event.pk}/")
        self.assertEqual(resp.status_code, 204, resp.content)
        mock_delete_task.delay.assert_called_once_with(
            "734185035623825559", "1529289108529352788"
        )
        self.assertFalse(DiscordEvent.objects.filter(pk=self.discord_event.pk).exists())
