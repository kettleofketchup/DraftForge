from datetime import datetime, timedelta
from itertools import count
from unittest import mock

from django.utils import timezone as tz
from structlog.testing import capture_logs

from app.models import CustomUser
from app.redis_client import set_client_for_tests
from app.redis_keys import namespaced_key
from events.constants import (
    ActorRole,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
    VoicePresenceSource,
)
from events.models import (
    Event,
    EventSignup,
    EventVoicePresence,
    ReadyCheck,
    RollCallMode,
)
from events.ready_check_constants import (
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckPhase,
)
from events.tests.base import EventTestCase
from events.tests.test_ready_check_service import ReadyCheckServiceTestCase
from events.tests.test_signup_post_lock import BrokenRedis, FakeRedis
from events.voice_presence import (
    FEED_HEARTBEAT_TTL_SECONDS,
    PresenceOutcome,
    WatchedChannel,
    apply_voice_state,
    touch_feed_heartbeat,
    voice_feed_age_seconds,
    watched_channels,
    watched_events,
)

GUILD = "200000000000000532"
CHANNEL = "100000000000000532"
OTHER_CHANNEL = "100000000000000533"
_discord_ids = count(300000000000000000)


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


class VoiceStateTestCase(ReadyCheckServiceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org.discord_server_id = GUILD
        self.org.save()

    def _event(self, *, channel: str = CHANNEL, **overrides: object) -> Event:
        fields: dict[str, object] = {
            "scheduled_at": tz.now() + timedelta(hours=1),
            "event_voice_channel_id": channel,
        }
        fields.update(overrides)
        return self.make_event(**fields)

    def _linked(self) -> CustomUser:
        user = self.make_user()
        user.discordId = str(next(_discord_ids))
        user.save()
        return user

    def _member(
        self,
        *events: Event,
        user: CustomUser | None = None,
        status: str = SignupStatus.APPROVED,
    ) -> CustomUser:
        member = user or self._linked()
        for event in events:
            self._signup(status, event=event, user=member)
        return member

    def _state(
        self,
        before: str | None,
        after: str | None,
        user: CustomUser,
        *,
        guild_id: str = GUILD,
    ) -> PresenceOutcome:
        assert user.discordId is not None
        with self.captureOnCommitCallbacks(execute=True):
            return apply_voice_state(
                guild_id=guild_id,
                discord_user_id=user.discordId,
                before_channel_id=before,
                after_channel_id=after,
            )

    def _row(self, event: Event, user: CustomUser) -> EventVoicePresence:
        return EventVoicePresence.objects.get(event=event, user=user)


class VoiceStateTests(VoiceStateTestCase):
    def test_join_creates_row_with_first_joined(self) -> None:
        event = self._event()
        user = self._member(event)
        outcome = self._state(None, CHANNEL, user)
        row = self._row(event, user)
        self.assertTrue(row.present)
        self.assertIsNotNone(row.first_joined_at)
        self.assertEqual(row.first_joined_at, row.last_joined_at)
        self.assertEqual(row.last_joined_at, row.last_seen_at)
        self.assertEqual(row.guild_id, GUILD)
        self.assertEqual(row.channel_id, CHANNEL)
        self.assertEqual(row.source, VoicePresenceSource.FEED)
        self.assertEqual(outcome.joined, 1)
        self.assertEqual(outcome.events, 1)
        self.assertEqual(outcome.detail, "")

    def test_leave_sets_last_left(self) -> None:
        event = self._event()
        user = self._member(event)
        self._state(None, CHANNEL, user)
        outcome = self._state(CHANNEL, None, user)
        row = self._row(event, user)
        self.assertFalse(row.present)
        self.assertIsNotNone(row.last_left_at)
        self.assertEqual(outcome.left, 1)

    def test_rejoin_keeps_first_joined_at(self) -> None:
        event = self._event()
        user = self._member(event)
        self._state(None, CHANNEL, user)
        self._state(CHANNEL, None, user)
        earlier = tz.now() - timedelta(minutes=10)
        EventVoicePresence.objects.filter(event=event, user=user).update(
            first_joined_at=earlier, last_joined_at=earlier
        )
        self._state(None, CHANNEL, user)
        row = self._row(event, user)
        self.assertTrue(row.present)
        self.assertEqual(row.first_joined_at, earlier)
        assert row.last_joined_at is not None
        self.assertGreater(row.last_joined_at, earlier)

    def test_move_between_watched_channels(self) -> None:
        first = self._event()
        second = self._event(channel=OTHER_CHANNEL)
        user = self._member(first, second)
        self._state(None, CHANNEL, user)
        outcome = self._state(CHANNEL, OTHER_CHANNEL, user)
        self.assertFalse(self._row(first, user).present)
        self.assertTrue(self._row(second, user).present)
        self.assertEqual((outcome.left, outcome.joined, outcome.events), (1, 1, 2))

    def test_unwatched_channel_returns_not_watched(self) -> None:
        event = self._event()
        user = self._member(event)
        outcome = self._state(None, "100000000000000999", user)
        self.assertEqual(outcome.detail, "not_watched")
        self.assertFalse(EventVoicePresence.objects.exists())

    def test_unknown_user_returns_user_not_linked(self) -> None:
        self._event()
        users_before = CustomUser.objects.count()
        outcome = apply_voice_state(
            guild_id=GUILD,
            discord_user_id="399999999999999999",
            before_channel_id=None,
            after_channel_id=CHANNEL,
        )
        self.assertEqual(outcome.detail, "user_not_linked")
        self.assertEqual(outcome.unknown_users, 1)
        self.assertFalse(EventVoicePresence.objects.exists())
        self.assertEqual(CustomUser.objects.count(), users_before)

    def test_linked_user_without_signup_no_row(self) -> None:
        self._event()
        user = self._linked()
        outcome = self._state(None, CHANNEL, user)
        self.assertEqual(outcome.not_signed_up, 1)
        self.assertEqual(outcome.joined, 0)
        self.assertFalse(EventVoicePresence.objects.exists())

    def test_guild_mismatch_ignored(self) -> None:
        event = self._event()
        user = self._member(event)
        outcome = self._state(None, CHANNEL, user, guild_id="200000000000000999")
        self.assertEqual(outcome.detail, "not_watched")
        self.assertFalse(EventVoicePresence.objects.exists())

    def test_same_channel_noop(self) -> None:
        event = self._event()
        user = self._member(event)
        outcome = self._state(CHANNEL, CHANNEL, user)
        self.assertEqual(outcome, PresenceOutcome())
        self.assertFalse(EventVoicePresence.objects.exists())

    def test_gateway_clears_manual_pin(self) -> None:
        event = self._event()
        user = self._member(event)
        EventVoicePresence.objects.create(
            event=event,
            user=user,
            channel_id=CHANNEL,
            present=True,
            source=VoicePresenceSource.MANUAL,
        )
        outcome = self._state(CHANNEL, None, user)
        row = self._row(event, user)
        self.assertFalse(row.present)
        self.assertEqual(row.source, VoicePresenceSource.FEED)
        self.assertEqual(outcome.left, 1)

    def test_gateway_join_on_manual_pin_records_feed_join(self) -> None:
        event = self._event()
        user = self._member(event)
        EventVoicePresence.objects.create(
            event=event,
            user=user,
            channel_id=CHANNEL,
            present=True,
            source=VoicePresenceSource.MANUAL,
        )
        outcome = self._state(None, CHANNEL, user)
        row = self._row(event, user)
        self.assertTrue(row.present)
        self.assertEqual(row.source, VoicePresenceSource.FEED)
        self.assertIsNotNone(row.first_joined_at)
        self.assertEqual(outcome.joined, 1)


class VoiceConfirmTests(VoiceStateTestCase):
    def _checked(
        self, *, flag: bool = True, **overrides: object
    ) -> tuple[Event, ReadyCheck, CustomUser]:
        event = self._event(voice_presence_confirms=flag, **overrides)
        user = self._member(event)
        check = self._open(event).check
        return event, check, user

    def _entry_state(self, check: ReadyCheck, user: CustomUser) -> str:
        return check.entries.get(user=user).state

    def test_join_confirms_when_flag_on(self) -> None:
        event, check, user = self._checked()
        outcome = self._state(None, CHANNEL, user)
        entry = check.entries.get(user=user)
        self.assertEqual(entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(entry.confirmed_via, ReadyCheckConfirmVia.VOICE)
        (row,) = self._rows(SignupAction.CONFIRMED, event)
        self.assertEqual(row.means, SignupMeans.DISCORD_VOICE)
        self.assertEqual(row.actor_role, ActorRole.MEMBER)
        self.assertEqual(outcome.confirmed, 1)

    def test_flag_off_no_confirm(self) -> None:
        event, check, user = self._checked(flag=False)
        outcome = self._state(None, CHANNEL, user)
        self.assertTrue(self._row(event, user).present)
        self.assertEqual(self._entry_state(check, user), ReadyCheckEntryState.PENDING)
        self.assertEqual(outcome.confirmed, 0)

    def test_flag_turned_on_after_open_no_confirm(self) -> None:
        event, check, user = self._checked(flag=False)
        Event.objects.filter(pk=event.pk).update(voice_presence_confirms=True)
        self._state(None, CHANNEL, user)
        self.assertEqual(self._entry_state(check, user), ReadyCheckEntryState.PENDING)

    def test_flag_turned_off_after_open_no_confirm(self) -> None:
        event, check, user = self._checked()
        Event.objects.filter(pk=event.pk).update(voice_presence_confirms=False)
        self._state(None, CHANNEL, user)
        self.assertEqual(self._entry_state(check, user), ReadyCheckEntryState.PENDING)

    def test_held_or_closed_no_confirm(self) -> None:
        for phase in (ReadyCheckPhase.HELD, ReadyCheckPhase.CLOSED):
            with self.subTest(phase=phase):
                event, check, user = self._checked()
                ReadyCheck.objects.filter(pk=check.pk).update(phase=phase)
                outcome = self._state(None, CHANNEL, user)
                self.assertTrue(self._row(event, user).present)
                self.assertEqual(
                    self._entry_state(check, user), ReadyCheckEntryState.PENDING
                )
                self.assertEqual(outcome.confirmed, 0)
                self._state(CHANNEL, None, user)

    def test_not_in_check_no_error(self) -> None:
        event, _check, _user = self._checked()
        late = self._member(event)
        outcome = self._state(None, CHANNEL, late)
        self.assertTrue(self._row(event, late).present)
        self.assertEqual(outcome.confirmed, 0)
        self.assertEqual(self._rows(SignupAction.CONFIRMED, event), [])

    def test_dropped_signup_gets_row_but_no_confirm(self) -> None:
        event, check, user = self._checked()
        EventSignup.objects.filter(event=event, user=user).update(
            status=SignupStatus.DROPPED
        )
        outcome = self._state(None, CHANNEL, user)
        self.assertTrue(self._row(event, user).present)
        self.assertNotEqual(
            self._entry_state(check, user), ReadyCheckEntryState.CONFIRMED
        )
        self.assertEqual(outcome.confirmed, 0)
        self.assertEqual(
            EventSignup.objects.get(event=event, user=user).status,
            SignupStatus.DROPPED,
        )

    def test_staff_verified_mode_confirms(self) -> None:
        _event, check, user = self._checked(
            roll_call_enabled=True, roll_call_mode=RollCallMode.MANUAL
        )
        self.assertEqual(check.settings_snapshot["effective_mode"], "manual")
        outcome = self._state(None, CHANNEL, user)
        self.assertEqual(self._entry_state(check, user), ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(outcome.confirmed, 1)

    def test_leave_after_confirm_stays_confirmed(self) -> None:
        event, check, user = self._checked()
        self._state(None, CHANNEL, user)
        self._state(CHANNEL, None, user)
        self.assertFalse(self._row(event, user).present)
        self.assertEqual(self._entry_state(check, user), ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(
            EventSignup.objects.get(event=event, user=user).status,
            SignupStatus.CONFIRMED,
        )
        self.assertEqual(self._rows(SignupAction.UNCONFIRMED, event), [])

    def test_shared_channel_confirms_only_event_with_flag(self) -> None:
        on = self._event(voice_presence_confirms=True)
        off = self._event(voice_presence_confirms=False)
        user = self._member(on, off)
        on_check = self._open(on).check
        off_check = self._open(off).check
        outcome = self._state(None, CHANNEL, user)
        self.assertTrue(self._row(on, user).present)
        self.assertTrue(self._row(off, user).present)
        self.assertEqual(
            self._entry_state(on_check, user), ReadyCheckEntryState.CONFIRMED
        )
        self.assertEqual(
            self._entry_state(off_check, user), ReadyCheckEntryState.PENDING
        )
        self.assertEqual(outcome.confirmed, 1)
