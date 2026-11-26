"""sync_future_events: returns touched events + cascades reminder fields."""

from datetime import datetime, time, timedelta
from datetime import timezone as dt_tz

from django.utils import timezone as tz

from events.constants import SignupOpenMode, StaffReasonPolicy
from events.models import Event, EventRepeater
from events.services import sync_future_events
from events.tests.test_discord_tasks import _DiscordTaskTestCase


class SyncFutureEventsReturnTypeTest(_DiscordTaskTestCase):
    def test_returns_list_of_touched_events(self):
        # _DiscordTaskTestCase already creates self.event; create another
        # in upcoming state for the same repeater
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


class SyncFutureEventsSignupPolicyTest(_DiscordTaskTestCase):
    def _setup(self) -> tuple[EventRepeater, Event, datetime]:
        repeater = EventRepeater.objects.create(
            organization=self.event.organization,
            name="Policy Repeater",
            day_of_week=1,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date(),
            signup_open_mode=SignupOpenMode.SCHEDULED,
            signups_open_hours_before=10,
        )
        hand_set = tz.now() + timedelta(days=1)
        event = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Policy Future",
            scheduled_at=tz.now() + timedelta(days=6),
            state="upcoming",
            signups_open_at=hand_set,
        )
        return repeater, event, hand_set

    def test_policy_changed_recomputes(self) -> None:
        repeater, event, _ = self._setup()
        sync_future_events(repeater, policy_changed=True)
        event.refresh_from_db()
        self.assertEqual(
            event.signups_open_at, event.scheduled_at - timedelta(hours=10)
        )

    def test_plain_cascade_keeps_open_time(self) -> None:
        repeater, event, hand_set = self._setup()
        sync_future_events(repeater)
        event.refresh_from_db()
        self.assertEqual(event.signups_open_at, hand_set)


class SyncFutureEventsLineRulesTest(_DiscordTaskTestCase):
    def test_line_rules_cascade_to_future_events(self) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.event.organization,
            name="Line Repeater",
            day_of_week=1,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date(),
            line_withdraw_forfeits=False,
            line_switch_restamps=False,
        )
        event = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Line Future",
            scheduled_at=tz.now() + timedelta(days=6),
            state="upcoming",
        )
        self.assertTrue(event.line_withdraw_forfeits)

        sync_future_events(repeater)

        event.refresh_from_db()
        self.assertFalse(event.line_withdraw_forfeits)
        self.assertFalse(event.line_switch_restamps)

    def test_staff_reason_policy_cascades_to_future_events_only(self) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.event.organization,
            name="Reason Repeater",
            day_of_week=1,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date(),
        )
        future = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Reason Future",
            scheduled_at=tz.now() + timedelta(days=6),
            state="upcoming",
        )
        past = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Reason Past",
            scheduled_at=tz.now() - timedelta(days=1),
            state="completed",
        )
        repeater.staff_reason_policy = StaffReasonPolicy.PLACEMENTS
        repeater.save(update_fields=["staff_reason_policy"])

        sync_future_events(repeater)

        future.refresh_from_db()
        past.refresh_from_db()
        self.assertEqual(future.staff_reason_policy, StaffReasonPolicy.PLACEMENTS)
        self.assertEqual(past.staff_reason_policy, StaffReasonPolicy.OPTIONAL)
