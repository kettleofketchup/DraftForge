from datetime import datetime, timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from structlog.testing import capture_logs

from app.models import GameType, League, Organization, Tournament
from events.models import Event, EventState
from org import activity
from org.activity import (
    active_org_ids,
    enqueue_org_name_sync,
    guild_sync_lock,
    release_guild_sync_lock,
)

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test_activity",
    }
}

APPLY = "org.activity.sync_org_discord_names.apply_async"


class ActiveOrgIdsTest(TestCase):
    def setUp(self) -> None:
        self.now: datetime = timezone.now()
        self.org = Organization.objects.create(name="Active", discord_server_id="111")
        self.other = Organization.objects.create(name="Other", discord_server_id="222")
        self.league = League.objects.create(name="L", organization=self.org)

    def _tournament(self, offset: timedelta, state: str = "future") -> Tournament:
        return Tournament.objects.create(
            name="T", date_played=self.now + offset, league=self.league, state=state
        )

    def _event(self, offset: timedelta) -> Event:
        return Event.objects.create(
            name="E",
            organization=self.org,
            game_type=GameType.DOTA2,
            scheduled_at=self.now + offset,
            state=EventState.SIGNUPS_OPEN,
        )

    def _active(self) -> set[int]:
        return active_org_ids([self.org.pk, self.other.pk], now=self.now)

    def test_no_tournaments_or_events_is_inactive(self) -> None:
        self.assertEqual(self._active(), set())

    def test_in_progress_tournament_is_active_regardless_of_date(self) -> None:
        self._tournament(-timedelta(days=30), state="in_progress")
        self.assertEqual(self._active(), {self.org.pk})

    def test_tournament_within_window_is_active(self) -> None:
        self._tournament(-timedelta(days=2))
        self.assertEqual(self._active(), {self.org.pk})

    def test_upcoming_tournament_within_lookahead_is_active(self) -> None:
        self._tournament(timedelta(days=6))
        self.assertEqual(self._active(), {self.org.pk})

    def test_tournament_outside_window_is_inactive(self) -> None:
        self._tournament(-timedelta(days=4), state="past")
        self._tournament(timedelta(days=8))
        self.assertEqual(self._active(), set())

    def test_event_within_window_is_active(self) -> None:
        self._event(timedelta(days=1))
        self.assertEqual(self._active(), {self.org.pk})

    def test_event_outside_window_is_inactive(self) -> None:
        self._event(timedelta(days=10))
        self.assertEqual(self._active(), set())

    def test_only_requested_orgs_are_considered(self) -> None:
        self._tournament(timedelta(days=1))
        self.assertEqual(active_org_ids([self.other.pk], now=self.now), set())
        self.assertEqual(active_org_ids([], now=self.now), set())


@override_settings(CACHES=LOCMEM)
class GuildLockAndEnqueueTest(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_guild_sync_lock_round_trip(self) -> None:
        self.assertTrue(guild_sync_lock("111"))
        self.assertFalse(guild_sync_lock("111"))
        self.assertTrue(guild_sync_lock("222"))
        release_guild_sync_lock("111")
        self.assertTrue(guild_sync_lock("111"))

    def test_enqueue_publishes_on_commit(self) -> None:
        with mock.patch(APPLY) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                enqueue_org_name_sync(7)
        self.assertEqual(apply_async.call_args.kwargs["args"], [7])

    def test_broker_unreachable_is_swallowed_and_logged(self) -> None:
        with (
            mock.patch.object(
                activity.sync_org_discord_names.app,
                "connection_for_write",
                side_effect=OSError("down"),
            ) as conn,
            capture_logs() as logs,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                enqueue_org_name_sync(7)
        self.assertEqual(conn.call_args.kwargs["connect_timeout"], 0.5)
        transport = conn.call_args.kwargs["transport_options"]
        self.assertEqual(transport["socket_connect_timeout"], 0.5)
        self.assertEqual(transport["socket_timeout"], 0.5)
        self.assertIn("name_sync_enqueue_failed", [e["event"] for e in logs])
