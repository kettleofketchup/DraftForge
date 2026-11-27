"""Deleting an event series (EventRepeater) must clean up its future events and
their live Discord scheduled events, so the every-60s sync_discord_events task
can't resurrect them as "ghost" events.

Regression for: deleted series kept generating ghost Discord events because
EventRepeaterViewSet was a plain ModelViewSet (hard delete, Event.event_repeater
SET_NULL) with no teardown, and nothing ever DELETEs the live Discord event.
"""

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import site as admin_site
from django.http import HttpRequest
from django.test import RequestFactory
from django.utils import timezone as tz
from rest_framework.test import APIClient

from discordbot.models import DiscordEvent, DiscordMessageLog
from events.admin import EventAdmin, EventRepeaterAdmin
from events.capacity import lock_event
from events.constants import EventState, RepeatFrequency, SignupAction, SignupStatus
from events.ledger import SignupActor, record_signup_change
from events.models import Event, EventRepeater, EventSignup, SignupLedgerEntry
from events.services import teardown_event_repeater
from events.tests.base import EventTestCase
from tournament.models import Tournament


class SeriesDeleteCleanupTest(EventTestCase):
    def setUp(self) -> None:
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

    @patch("events.services.delete_discord_scheduled_event")
    def test_delete_series_removes_future_events_and_discord(
        self, mock_delete_task: MagicMock
    ) -> None:
        self.client.force_authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
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

    @patch("events.services.delete_discord_scheduled_event")
    def test_delete_single_event_deletes_live_discord_event(
        self, mock_delete_task: MagicMock
    ) -> None:
        self.client.force_authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.delete(f"/api/events/{self.future_event.pk}/")
        self.assertEqual(resp.status_code, 204, resp.content)
        mock_delete_task.delay.assert_called_once_with(
            "734185035623825559", "1529289108529352788"
        )
        self.assertFalse(DiscordEvent.objects.filter(pk=self.discord_event.pk).exists())


class AdminDeleteCleanupTest(SeriesDeleteCleanupTest):
    """Django admin deletes tear down the same Discord and tournament state."""

    def setUp(self) -> None:
        super().setUp()
        self.tournament = Tournament.objects.create(
            name="Sunday Turbo Cup", date_played=tz.now()
        )
        self.future_event.tournament = self.tournament
        self.future_event.save(update_fields=["tournament"])
        self.message_log = DiscordMessageLog.objects.create(
            channel_id="1",
            embed_data={},
            success=True,
            source="event_announcement",
            source_id=self.future_event.pk,
        )

    def _request(self) -> HttpRequest:
        request = RequestFactory().post("/admin/")
        request.user = self.admin
        return request

    def _assert_torn_down(self, mock_delete_task: MagicMock) -> None:
        mock_delete_task.delay.assert_called_once_with(
            "734185035623825559", "1529289108529352788"
        )
        self.assertFalse(Event.objects.filter(pk=self.future_event.pk).exists())
        self.assertFalse(DiscordEvent.objects.filter(pk=self.discord_event.pk).exists())
        self.assertFalse(Tournament.objects.filter(pk=self.tournament.pk).exists())
        self.assertFalse(
            DiscordMessageLog.objects.filter(pk=self.message_log.pk).exists()
        )

    @patch("events.services.delete_discord_scheduled_event")
    def test_admin_event_delete_tears_down(self, mock_delete_task: MagicMock) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            EventAdmin(Event, admin_site).delete_model(
                self._request(), self.future_event
            )
        self._assert_torn_down(mock_delete_task)

    @patch("events.services.delete_discord_scheduled_event")
    def test_admin_event_bulk_delete_tears_down(
        self, mock_delete_task: MagicMock
    ) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            EventAdmin(Event, admin_site).delete_queryset(
                self._request(), Event.objects.filter(pk=self.future_event.pk)
            )
        self._assert_torn_down(mock_delete_task)

    @patch("events.services.delete_discord_scheduled_event")
    def test_admin_series_delete_tears_down(self, mock_delete_task: MagicMock) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            EventRepeaterAdmin(EventRepeater, admin_site).delete_model(
                self._request(), self.repeater
            )
        self._assert_torn_down(mock_delete_task)
        self.past_event.refresh_from_db()
        self.assertIsNone(self.past_event.event_repeater_id)

    @patch("events.services.delete_discord_scheduled_event")
    def test_admin_series_bulk_delete_tears_down(
        self, mock_delete_task: MagicMock
    ) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            EventRepeaterAdmin(EventRepeater, admin_site).delete_queryset(
                self._request(), EventRepeater.objects.filter(pk=self.repeater.pk)
            )
        self._assert_torn_down(mock_delete_task)
        self.assertFalse(EventRepeater.objects.filter(pk=self.repeater.pk).exists())


class SeriesPreservationTest(EventTestCase):
    """Series deletion cancels registered occurrences instead of deleting them."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        for target in (
            "events.services.notify_signup_changed",
            "events.discord.dispatch.notify_signup_changed",
        ):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly Night",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day="18:00",
            starts_at=tz.now().date(),
            created_by=self.admin,
        )

    def _occurrence(self, state: str = EventState.UPCOMING, **extra: Any) -> Event:
        return self.make_event(event_repeater=self.repeater, state=state, **extra)

    def _signup(self, event: Event, status: str = SignupStatus.APPROVED) -> EventSignup:
        return EventSignup.objects.create(
            event=event, user=self.make_user(), status=status
        )

    def _record(self, event: Event, *, keep_signup: bool) -> SignupLedgerEntry:
        signup = self._signup(event)
        entry = record_signup_change(
            event=event,
            subject=signup.user,
            actor=SignupActor.system(),
            action=SignupAction.SIGNED_UP,
            signup=signup if keep_signup else None,
        )
        signup.delete()
        return entry

    def _delete_series(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(f"/api/events/repeaters/{self.repeater.pk}/")
        self.assertEqual(response.status_code, 204, response.content)

    def _cancel_entries(self, event: Event) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                event_id=event.pk, action=SignupAction.EVENT_CANCELLED
            )
        )

    @patch("events.services.delete_discord_scheduled_event")
    def test_registered_occurrences_are_cancelled_and_kept(
        self, delete_task: MagicMock
    ) -> None:
        registered = {
            state: self._occurrence(state)
            for state in (
                EventState.UPCOMING,
                EventState.SIGNUPS_OPEN,
                EventState.ROLL_CALL,
            )
        }
        registered["off_schedule"] = self._occurrence(is_off_schedule=True)
        registered["past"] = self._occurrence(scheduled_at=tz.now() - timedelta(days=3))
        signups = {key: self._signup(event) for key, event in registered.items()}
        removed_only = self._occurrence()
        removed = self._signup(removed_only, SignupStatus.CANCELLED)
        deleted_signup_history = self._occurrence()
        orphan_entry = self._record(deleted_signup_history, keep_signup=True)
        event_only = self._occurrence()
        event_entry = self._record(event_only, keep_signup=False)
        empty = self._occurrence()
        empty_tournament = Tournament.objects.create(
            name="Empty Cup", date_played=tz.now()
        )
        empty.tournament = empty_tournament
        empty.save(update_fields=["tournament"])
        DiscordEvent.objects.create(event=empty, guild_id="11", scheduled_event_id="22")
        inactive = {
            state: self._occurrence(state)
            for state in (
                EventState.IN_PROGRESS,
                EventState.COMPLETED,
                EventState.CANCELLED,
            )
        }

        self._delete_series()

        self.assertFalse(EventRepeater.objects.filter(pk=self.repeater.pk).exists())
        for key, event in registered.items():
            with self.subTest(occurrence=key):
                fetched = Event.objects.nocache().get(pk=event.pk)
                self.assertEqual(fetched.state, EventState.CANCELLED)
                self.assertIsNone(fetched.event_repeater_id)
                signup = EventSignup.objects.nocache().get(pk=signups[key].pk)
                self.assertEqual(signup.status, SignupStatus.APPROVED)
                (entry,) = self._cancel_entries(event)
                self.assertEqual(entry.actor_user_id, self.admin.pk)
        for event in (removed_only, deleted_signup_history, event_only):
            with self.subTest(event=event.pk):
                fetched = Event.objects.nocache().get(pk=event.pk)
                self.assertEqual(fetched.state, EventState.CANCELLED)
                self.assertIsNone(fetched.event_repeater_id)
                self.assertEqual(self._cancel_entries(event), [])
        self.assertEqual(
            EventSignup.objects.nocache().get(pk=removed.pk).status,
            SignupStatus.CANCELLED,
        )
        self.assertTrue(SignupLedgerEntry.objects.filter(pk=orphan_entry.pk).exists())
        self.assertTrue(SignupLedgerEntry.objects.filter(pk=event_entry.pk).exists())
        self.assertFalse(Event.objects.filter(pk=empty.pk).exists())
        self.assertFalse(Tournament.objects.filter(pk=empty_tournament.pk).exists())
        self.assertFalse(DiscordEvent.objects.filter(event_id=empty.pk).exists())
        delete_task.delay.assert_called_once_with("11", "22")
        for state, event in inactive.items():
            with self.subTest(inactive=state):
                fetched = Event.objects.nocache().get(pk=event.pk)
                self.assertEqual(fetched.state, state)
                self.assertIsNone(fetched.event_repeater_id)

    @patch("events.services.delete_discord_scheduled_event")
    def test_retained_occurrence_scheduled_event_removed_after_commit(
        self, delete_task: MagicMock
    ) -> None:
        event = self._occurrence()
        self._signup(event)
        discord = DiscordEvent.objects.create(
            event=event, guild_id="31", scheduled_event_id="32"
        )
        self._delete_series()
        discord.refresh_from_db()
        self.assertIsNone(discord.scheduled_event_id)
        delete_task.delay.assert_called_once_with("31", "32")

    @patch("events.services.delete_discord_scheduled_event")
    def test_series_rollback_discards_all_discord_dispatches(
        self, delete_task: MagicMock
    ) -> None:
        empty = self._occurrence()
        empty_discord = DiscordEvent.objects.create(
            event=empty, guild_id="41", scheduled_event_id="42"
        )
        registered = self._occurrence()
        signup = self._signup(registered)
        DiscordEvent.objects.create(
            event=registered, guild_id="51", scheduled_event_id="52"
        )
        with (
            patch(
                "events.services.standing.on_event_closed",
                side_effect=RuntimeError("standing failure"),
            ),
            self.captureOnCommitCallbacks(execute=True),
            self.assertRaises(RuntimeError),
        ):
            teardown_event_repeater(self.repeater, actor=self.admin)
        delete_task.delay.assert_not_called()
        self.assertTrue(EventRepeater.objects.filter(pk=self.repeater.pk).exists())
        self.assertTrue(Event.objects.nocache().filter(pk=empty.pk).exists())
        empty_discord.refresh_from_db()
        self.assertEqual(empty_discord.scheduled_event_id, "42")
        fetched = Event.objects.nocache().get(pk=registered.pk)
        self.assertEqual(
            (fetched.state, fetched.event_repeater_id),
            (EventState.UPCOMING, self.repeater.pk),
        )
        self.assertEqual(
            EventSignup.objects.nocache().get(pk=signup.pk).status,
            SignupStatus.APPROVED,
        )
        self.assertEqual(self._cancel_entries(registered), [])

    def test_occurrence_that_progressed_under_lock_is_kept(self) -> None:
        event = self._occurrence()

        def progress_then_lock(target: Event) -> Event:
            Event.objects.filter(pk=target.pk).update(state=EventState.IN_PROGRESS)
            return lock_event(target)

        with patch("events.services.lock_event", side_effect=progress_then_lock):
            teardown_event_repeater(self.repeater, actor=self.admin)
        fetched = Event.objects.nocache().get(pk=event.pk)
        self.assertEqual(fetched.state, EventState.IN_PROGRESS)
        self.assertIsNone(fetched.event_repeater_id)
