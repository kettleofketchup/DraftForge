"""sync_future_events: returns touched events + cascades reminder fields."""

from django.test import TestCase

from events.services import sync_future_events
from events.tests.test_discord_tasks import _DiscordTaskTestCase


class SyncFutureEventsReturnTypeTest(_DiscordTaskTestCase):
    def test_returns_list_of_touched_events(self):
        # _DiscordTaskTestCase already creates self.event; create another
        # in upcoming state for the same repeater
        from events.models import Event, EventRepeater
        from datetime import datetime, time, timezone as dt_tz

        repeater = EventRepeater.objects.create(
            organization=self.event.organization,
            name="Test Repeater",
            day_of_week=1,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=datetime(2026, 5, 1, tzinfo=dt_tz.utc).date(),
        )
        e1 = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Future 1",
            scheduled_at=datetime(2026, 6, 8, 20, 0, tzinfo=dt_tz.utc),
            state="upcoming",
            discord_announcement_channel_id="ch_1",
        )
        e2 = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Future 2",
            scheduled_at=datetime(2026, 6, 15, 20, 0, tzinfo=dt_tz.utc),
            state="upcoming",
            discord_announcement_channel_id="ch_1",
        )

        result = sync_future_events(repeater)

        # Now returns a list of Event instances (was: int count)
        self.assertEqual({e.pk for e in result}, {e1.pk, e2.pk})

    def test_does_not_touch_past_state_events(self):
        from events.models import Event, EventRepeater
        from datetime import datetime, time, timezone as dt_tz

        repeater = EventRepeater.objects.create(
            organization=self.event.organization,
            name="Test Repeater 2",
            day_of_week=1,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=datetime(2026, 5, 1, tzinfo=dt_tz.utc).date(),
            discord_announcement=True,
        )
        past_event = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Past",
            scheduled_at=datetime(2026, 6, 8, 20, 0, tzinfo=dt_tz.utc),
            state="signups_open",  # past UPCOMING
            discord_announcement=False,
            discord_announcement_channel_id="ch_1",
        )

        result = sync_future_events(repeater)
        past_event.refresh_from_db()
        self.assertFalse(past_event.discord_announcement)
        self.assertNotIn(past_event, result)
