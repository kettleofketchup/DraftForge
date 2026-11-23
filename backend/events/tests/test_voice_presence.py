from datetime import datetime, timedelta
from unittest import mock

from django.utils import timezone as tz
from structlog.testing import capture_logs

from app.redis_client import set_client_for_tests
from app.redis_keys import namespaced_key
from events.constants import EventState
from events.models import Event, ReadyCheck
from events.ready_check_constants import ReadyCheckPhase
from events.tests.base import EventTestCase
from events.tests.test_signup_post_lock import BrokenRedis, FakeRedis
from events.voice_presence import (
    FEED_HEARTBEAT_TTL_SECONDS,
    WatchedChannel,
    touch_feed_heartbeat,
    voice_feed_age_seconds,
    watched_channels,
    watched_events,
)

GUILD = "200000000000000532"
CHANNEL = "100000000000000532"


class WatchedEventsTests(EventTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.org.discord_server_id = GUILD
        cls.org.save()

    def setUp(self) -> None:
        self.now = tz.now().replace(microsecond=0)

    def _event(
        self,
        *,
        offset: timedelta,
        state: str = EventState.ROLL_CALL,
        channel: str = CHANNEL,
        **overrides: object,
    ) -> Event:
        return self.make_event(
            scheduled_at=self.now + offset,
            state=state,
            event_voice_channel_id=channel,
            **overrides,
        )

    def _watched_ids(self) -> set[int]:
        return set(watched_events(self.now).values_list("pk", flat=True))

    def test_roll_call_within_window_watched(self) -> None:
        event = self._event(offset=timedelta(hours=5))
        self.assertIn(event.pk, self._watched_ids())

    def test_beyond_lookahead_not_watched(self) -> None:
        event = self._event(offset=timedelta(hours=7))
        self.assertNotIn(event.pk, self._watched_ids())

    def test_older_than_lookbehind_not_watched(self) -> None:
        event = self._event(offset=-timedelta(hours=25), state=EventState.SIGNUPS_OPEN)
        self.assertNotIn(event.pk, self._watched_ids())

    def test_in_progress_watched_within_24h(self) -> None:
        recent = self._event(offset=-timedelta(hours=23), state=EventState.IN_PROGRESS)
        old = self._event(offset=-timedelta(hours=25), state=EventState.IN_PROGRESS)
        watched = self._watched_ids()
        self.assertIn(recent.pk, watched)
        self.assertNotIn(old.pk, watched)

    def test_other_state_not_watched(self) -> None:
        event = self._event(offset=timedelta(hours=1), state=EventState.UPCOMING)
        self.assertNotIn(event.pk, self._watched_ids())

    def test_live_check_watched_far_ahead(self) -> None:
        event = self._event(offset=timedelta(hours=8))
        check = ReadyCheck.objects.create(event=event, phase=ReadyCheckPhase.OPEN)
        self.assertIn(event.pk, self._watched_ids())
        check.phase = ReadyCheckPhase.CLOSED
        check.save()
        self.assertNotIn(event.pk, self._watched_ids())

    def test_no_channel_or_no_guild_excluded(self) -> None:
        no_channel = self._event(offset=timedelta(hours=1), channel="")
        self.assertNotIn(no_channel.pk, self._watched_ids())
        self.org.discord_server_id = ""
        self.org.save()
        with_channel = self._event(offset=timedelta(hours=1))
        self.assertNotIn(with_channel.pk, self._watched_ids())

    def test_shared_channel_grouped(self) -> None:
        first = self._event(offset=timedelta(hours=1))
        second = self._event(offset=timedelta(hours=9))
        ReadyCheck.objects.create(event=second, phase=ReadyCheckPhase.OPEN)
        other = self._event(offset=timedelta(hours=2), channel="100000000000000999")
        self.assertEqual(
            list(watched_events(self.now).values_list("pk", flat=True)).count(
                second.pk
            ),
            1,
        )
        self.assertEqual(
            watched_channels(self.now),
            [
                WatchedChannel(
                    guild_id=GUILD,
                    channel_id=CHANNEL,
                    event_ids=tuple(sorted((first.pk, second.pk))),
                ),
                WatchedChannel(
                    guild_id=GUILD,
                    channel_id="100000000000000999",
                    event_ids=(other.pk,),
                ),
            ],
        )

    def test_watching_ignores_toggle(self) -> None:
        event = self._event(offset=timedelta(hours=1), voice_presence_confirms=False)
        self.assertIn(event.pk, self._watched_ids())

    def test_defaults_now(self) -> None:
        event = self._event(offset=timedelta(hours=1))
        self.assertIn(event.pk, set(watched_events().values_list("pk", flat=True)))


class FeedHeartbeatTests(EventTestCase):
    def setUp(self) -> None:
        self.redis = FakeRedis()
        set_client_for_tests(self.redis)
        self.addCleanup(set_client_for_tests, None)

    def test_heartbeat_sets_channel_and_guild_keys_with_ttl(self) -> None:
        touch_feed_heartbeat("G", ["C"])
        for key in (namespaced_key("voice_feed:G"), namespaced_key("voice_feed:G:C")):
            self.assertIn(key, self.redis.data)
            self.assertEqual(self.redis.ttls[key], FEED_HEARTBEAT_TTL_SECONDS)
        self.assertEqual(FEED_HEARTBEAT_TTL_SECONDS, 3600)

    def test_heartbeat_empty_channels_writes_nothing(self) -> None:
        touch_feed_heartbeat("G", [])
        self.assertEqual(self.redis.data, {})

    def test_age_reads_channel_key_when_given(self) -> None:
        fixed = datetime(2026, 11, 23, 12, 0, 0, tzinfo=tz.get_current_timezone())
        self.redis.set(namespaced_key("voice_feed:G"), str(fixed.timestamp() - 5))
        self.redis.set(namespaced_key("voice_feed:G:C"), str(fixed.timestamp() - 40))
        with mock.patch(
            "events.voice_presence.time.time", return_value=fixed.timestamp()
        ):
            self.assertEqual(voice_feed_age_seconds("G", "C"), 40.0)
            self.assertEqual(voice_feed_age_seconds("G"), 5.0)

    def test_age_none_when_missing(self) -> None:
        self.assertIsNone(voice_feed_age_seconds("G"))
        self.assertIsNone(voice_feed_age_seconds("G", "C"))

    def test_heartbeat_round_trip(self) -> None:
        touch_feed_heartbeat("G", ["C"])
        age = voice_feed_age_seconds("G", "C")
        assert age is not None
        self.assertLess(age, 5)

    def test_broken_redis_fails_open(self) -> None:
        set_client_for_tests(BrokenRedis())
        with capture_logs() as logs:
            touch_feed_heartbeat("G", ["C"])
            self.assertIsNone(voice_feed_age_seconds("G", "C"))
        warnings = [
            entry
            for entry in logs
            if entry["event"] == "voice_feed_heartbeat_unavailable"
        ]
        self.assertTrue(warnings)
        self.assertTrue(all(entry["log_level"] == "warning" for entry in warnings))
