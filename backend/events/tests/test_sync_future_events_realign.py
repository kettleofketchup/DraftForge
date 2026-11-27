"""sync_future_events realigns occurrences when the repeater's schedule changes.

Pre-PR-2 behavior: editing a repeater's day_of_week left existing UPCOMING
events on their old days, while the next hourly generate_events_for_repeater
created NEW events at the new schedule — admins saw duplicate occurrences.

PR-2 fix: when the caller signals realign_schedule=True, delete UPCOMING
rows whose scheduled_at is no longer in the new occurrence set, then
generate_events_for_repeater fills in any missing ones.
"""

from datetime import datetime, time, timedelta
from datetime import timezone as dt_tz
from unittest.mock import MagicMock, patch

from django.db import transaction
from django.utils import timezone
from structlog.testing import capture_logs

from discordbot.models import DiscordEvent
from events.capacity import lock_event
from events.constants import EventState, SignupAction, SignupStatus
from events.ledger import SignupActor, record_signup_change
from events.models import Event, EventRepeater, EventSignup, SignupLedgerEntry
from events.services import _get_next_occurrences, _today, sync_future_events
from events.tests.test_discord_tasks import _DiscordTaskTestCase


class SyncFutureEventsRealignTest(_DiscordTaskTestCase):
    def _make_repeater(
        self, day_of_week: int = 1, time_of_day: time = time(20, 0)
    ) -> EventRepeater:
        # starts_at must be today or earlier — generate_events_for_repeater
        # uses _today() as its from_date and won't generate events before that
        return EventRepeater.objects.create(
            organization=self.event.organization,
            name="Realign Test Repeater",
            frequency="weekly",
            day_of_week=day_of_week,
            time_of_day=time_of_day,
            timezone="UTC",
            starts_at=timezone.now().date() - timedelta(days=1),
            generate_days_ahead=14,
            is_active=True,
        )

    def test_realign_false_preserves_existing_scheduled_at(self):
        repeater = self._make_repeater()
        original_at = datetime(2099, 1, 5, 20, 0, tzinfo=dt_tz.utc)
        ev = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Future",
            scheduled_at=original_at,
            state="upcoming",
            discord_announcement_channel_id="ch_1",
        )
        sync_future_events(repeater, realign_schedule=False)
        ev.refresh_from_db()
        self.assertEqual(ev.scheduled_at, original_at)

    def test_realign_true_deletes_stale_occurrence_outside_new_set(self):
        # day_of_week=1 (Monday in Sunday=0 convention)
        repeater = self._make_repeater(day_of_week=1)
        # Stale row at a date that won't match the new occurrence set
        # (a fixed historical date the generator won't produce)
        stale_at = datetime(2099, 1, 5, 20, 0, tzinfo=dt_tz.utc)
        stale_event = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Stale",
            scheduled_at=stale_at,
            state="upcoming",
            discord_announcement_channel_id="ch_1",
        )
        # Repeater is now-aligned; realign=True should delete the stale row
        # and regenerate the correct occurrences.
        sync_future_events(repeater, realign_schedule=True)
        self.assertFalse(Event.objects.filter(pk=stale_event.pk).exists())

    def test_realign_true_keeps_rows_already_in_new_set(self) -> None:
        # Use today's _today() helper so we know what generate_events_for_repeater
        # will produce. Pick day_of_week to match next-week's weekday so
        # generate_events_for_repeater will produce a row 7 days from today.
        repeater = self._make_repeater(day_of_week=1)
        today = _today()
        to_date = today + timedelta(days=repeater.generate_days_ahead)
        new_occurrences = list(_get_next_occurrences(repeater, today, to_date))
        if not new_occurrences:
            self.skipTest(
                "No occurrences in the test window — adjust generate_days_ahead"
            )

        # Pre-create a row at the FIRST occurrence — realign should keep it
        kept_event = Event.objects.create(
            organization=self.event.organization,
            event_repeater=repeater,
            name="Already aligned",
            scheduled_at=new_occurrences[0],
            state="upcoming",
            discord_announcement_channel_id="ch_1",
        )
        sync_future_events(repeater, realign_schedule=True)
        # The kept row should still be there
        self.assertTrue(Event.objects.filter(pk=kept_event.pk).exists())

    def test_realign_false_default_no_regeneration(self):
        # If sync_future_events is called without realign_schedule (default False),
        # generate_events_for_repeater should NOT be invoked — rows stay as-is.
        repeater = self._make_repeater()
        with patch("events.services.generate_events_for_repeater") as mock_gen:
            sync_future_events(repeater)
            mock_gen.assert_not_called()

    def test_realign_true_calls_generate_events_for_repeater(self):
        repeater = self._make_repeater()
        with patch("events.services.generate_events_for_repeater") as mock_gen:
            mock_gen.return_value = []
            sync_future_events(repeater, realign_schedule=True)
            mock_gen.assert_called_once_with(repeater)


class RealignSignupRecordsTest(_DiscordTaskTestCase):
    """Realignment never deletes an occurrence that carries signup history."""

    def setUp(self) -> None:
        super().setUp()
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Records Realign Repeater",
            frequency="weekly",
            day_of_week=1,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=timezone.now().date() - timedelta(days=1),
            generate_days_ahead=14,
            is_active=True,
        )

    def _stale(self, day: int) -> Event:
        return Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name="Stale",
            scheduled_at=datetime(2099, 1, day, 20, 0, tzinfo=dt_tz.utc),
            state=EventState.UPCOMING,
        )

    def _record(
        self, event: Event, *, link_signup: bool, delete_signup: bool
    ) -> SignupLedgerEntry:
        user = self.make_user()
        signup = EventSignup.objects.create(
            event=event, user=user, status=SignupStatus.APPROVED
        )
        entry = record_signup_change(
            event=event,
            subject=user,
            actor=SignupActor.system(),
            action=SignupAction.SIGNED_UP,
            signup=signup if link_signup else None,
        )
        if delete_signup:
            signup.delete()
        return entry

    def test_realign_retains_records_only_and_live_signup_history(self) -> None:
        live = self._stale(5)
        self._record(live, link_signup=True, delete_signup=False)
        deleted_signup = self._stale(6)
        self._record(deleted_signup, link_signup=True, delete_signup=True)
        event_only = self._stale(7)
        self._record(event_only, link_signup=False, delete_signup=True)
        empty = self._stale(8)
        protected = (live, deleted_signup, event_only)
        with capture_logs() as logs:
            sync_future_events(self.repeater, realign_schedule=True)
        for event in protected:
            with self.subTest(event=event.pk):
                fetched = Event.objects.nocache().get(pk=event.pk)
                self.assertEqual(fetched.scheduled_at, event.scheduled_at)
                self.assertFalse(fetched.is_off_schedule)
                self.assertEqual(fetched.state, EventState.UPCOMING)
                self.assertEqual(fetched.event_repeater_id, self.repeater.pk)
        self.assertFalse(Event.objects.filter(pk=empty.pk).exists())
        self.assertTrue(
            Event.objects.filter(event_repeater=self.repeater)
            .exclude(pk__in=[e.pk for e in protected])
            .exists()
        )
        skipped = [e for e in logs if e["event"] == "realign_skipped_signup_records"]
        self.assertEqual(
            sorted(
                (
                    e["system"],
                    e["subsystem"],
                    e["event_id"],
                    e["repeater_id"],
                    e["log_level"],
                )
                for e in skipped
            ),
            sorted(
                ("events", "services", event.pk, self.repeater.pk, "info")
                for event in protected
            ),
        )
        for entry in skipped:
            self.assertEqual(
                set(entry),
                {
                    "event",
                    "system",
                    "subsystem",
                    "event_id",
                    "repeater_id",
                    "log_level",
                },
            )

    def test_realign_protected_occurrence_still_gets_config_cascade(self) -> None:
        protected = self._stale(5)
        self._record(protected, link_signup=False, delete_signup=True)
        self.repeater.name = "Renamed Records Series"
        self.repeater.save(update_fields=["name"])
        sync_future_events(self.repeater, realign_schedule=True)
        fetched = Event.objects.nocache().get(pk=protected.pk)
        self.assertEqual(fetched.name, "Renamed Records Series")
        self.assertEqual(fetched.scheduled_at, protected.scheduled_at)
        self.assertEqual(fetched.tournament_date, protected.scheduled_at)
        self.assertFalse(fetched.is_off_schedule)

    @patch("events.services.delete_discord_scheduled_event")
    def test_realign_rechecks_locked_candidate(self, delete_task: MagicMock) -> None:
        for field, value in (
            ("state", EventState.SIGNUPS_OPEN),
            ("is_off_schedule", True),
            ("event_repeater", None),
        ):
            with self.subTest(field=field):
                event = self._stale(9)
                DiscordEvent.objects.create(
                    event=event, guild_id="61", scheduled_event_id="62"
                )

                def change_then_lock(target: Event, f: str = field) -> Event:
                    Event.objects.filter(pk=target.pk).update(**{f: value})
                    return lock_event(target)

                with (
                    patch("events.services.lock_event", side_effect=change_then_lock),
                    self.captureOnCommitCallbacks(execute=True),
                ):
                    sync_future_events(self.repeater, realign_schedule=True)
                self.assertTrue(Event.objects.nocache().filter(pk=event.pk).exists())
                delete_task.delay.assert_not_called()
                Event.objects.filter(pk=event.pk).delete()

    @patch("events.services.delete_discord_scheduled_event")
    def test_empty_stale_teardown_dispatches_after_commit(
        self, delete_task: MagicMock
    ) -> None:
        empty = self._stale(5)
        DiscordEvent.objects.create(event=empty, guild_id="71", scheduled_event_id="72")
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                sync_future_events(self.repeater, realign_schedule=True)
                self.assertFalse(Event.objects.filter(pk=empty.pk).exists())
                delete_task.delay.assert_not_called()
        delete_task.delay.assert_called_once_with("71", "72")
