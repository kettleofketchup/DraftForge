from datetime import datetime, timedelta
from itertools import count
from typing import Any
from unittest import mock

from django.db import transaction
from django.utils import timezone as tz
from structlog.testing import capture_logs

from app.models import CustomUser
from app.redis_client import set_client_for_tests
from app.redis_keys import namespaced_key
from events import voice_presence
from events.capacity import lock_event
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
    SignupLedgerEntry,
)
from events.ready_check import ConfirmResult
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
    PRESENCE_FRESH,
    SNAPSHOT_GRACE,
    PresenceOutcome,
    Transition,
    WatchedChannel,
    _reconcile_has_work,
    _reconcile_pending,
    apply_voice_snapshot,
    apply_voice_state,
    set_presence_manually,
    touch_feed_heartbeat,
    voice_feed_age_seconds,
    watched_channels,
    watched_events,
)
from org.conduct.sources import _voice_user_ids

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


class VoiceSnapshotTestCase(VoiceStateTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        set_client_for_tests(self.redis)
        self.addCleanup(set_client_for_tests, None)

    def _snap(
        self,
        channels: dict[str, list[CustomUser | str]],
        missing: tuple[str, ...] = (),
    ) -> PresenceOutcome:
        payload = {
            channel: [
                member if isinstance(member, str) else str(member.discordId)
                for member in members
            ]
            for channel, members in channels.items()
        }
        with self.captureOnCommitCallbacks(execute=True):
            return apply_voice_snapshot(
                guild_id=GUILD, channels=payload, missing_channel_ids=missing
            )

    def _feed_row(
        self, event: Event, user: CustomUser, *, present: bool, age: timedelta
    ) -> EventVoicePresence:
        at = tz.now() - age
        return EventVoicePresence.objects.create(
            event=event,
            user=user,
            guild_id=GUILD,
            channel_id=event.event_voice_channel_id,
            present=present,
            source=VoicePresenceSource.FEED,
            first_joined_at=at,
            last_joined_at=at,
            last_left_at=None if present else at,
            last_seen_at=at,
        )

    def _age(self, event: Event, user: CustomUser, age: timedelta) -> None:
        at = tz.now() - age
        row = self._row(event, user)
        EventVoicePresence.objects.filter(pk=row.pk).update(
            last_joined_at=at if row.last_joined_at else None,
            last_left_at=at if row.last_left_at else None,
            last_seen_at=at if row.last_seen_at else None,
        )


class VoiceSnapshotTests(VoiceSnapshotTestCase):
    def test_snapshot_rebinds_present_row_after_channel_change(self) -> None:
        event = self._event(voice_presence_confirms=True)
        user = self._member(event)
        check = self._open(event).check
        self._feed_row(event, user, present=True, age=timedelta(seconds=5))
        event.event_voice_channel_id = OTHER_CHANNEL
        event.save()

        outcome = self._snap({OTHER_CHANNEL: [user]})

        row = self._row(event, user)
        self.assertTrue(row.present)
        self.assertEqual(row.channel_id, OTHER_CHANNEL)
        self.assertEqual(row.guild_id, GUILD)
        self.assertEqual(outcome.joined, 1)
        self.assertEqual(
            check.entries.get(user=user).state, ReadyCheckEntryState.CONFIRMED
        )

    def test_snapshot_new_empty_channel_clears_previous_presence(self) -> None:
        event = self._event(voice_presence_confirms=True)
        user = self._member(event)
        check = self._open(event).check
        self._feed_row(event, user, present=True, age=timedelta(seconds=5))
        event.event_voice_channel_id = OTHER_CHANNEL
        event.save()

        outcome = self._snap({OTHER_CHANNEL: []})

        self.assertFalse(self._row(event, user).present)
        self.assertEqual(outcome.confirmed, 0)
        self.assertEqual(
            check.entries.get(user=user).state, ReadyCheckEntryState.PENDING
        )

    def test_snapshot_marks_members_present(self) -> None:
        event = self._event()
        user = self._member(event)
        stranger = self._linked()
        outcome = self._snap({CHANNEL: [user, user, stranger, "399999999999999999"]})
        row = self._row(event, user)
        self.assertTrue(row.present)
        self.assertEqual(row.source, VoicePresenceSource.FEED)
        self.assertIsNotNone(row.first_joined_at)
        self.assertEqual(row.channel_id, CHANNEL)
        self.assertEqual(outcome.joined, 1)
        self.assertEqual(outcome.unknown_users, 1)
        self.assertEqual(outcome.not_signed_up, 1)
        self.assertFalse(EventVoicePresence.objects.filter(user=stranger).exists())

    def test_gateway_join_rebinds_present_row_after_channel_change(self) -> None:
        event = self._event(voice_presence_confirms=True)
        user = self._member(event)
        check = self._open(event).check
        self._feed_row(event, user, present=True, age=timedelta(seconds=1))
        Event.objects.filter(pk=event.pk).update(event_voice_channel_id=OTHER_CHANNEL)
        outcome = self._state(None, OTHER_CHANNEL, user)
        row = self._row(event, user)
        self.assertEqual(row.channel_id, OTHER_CHANNEL)
        self.assertEqual(outcome.joined, 1)
        self.assertEqual(
            check.entries.get(user=user).state, ReadyCheckEntryState.CONFIRMED
        )

    def test_snapshot_clears_stale_presence(self) -> None:
        event = self._event()
        user = self._member(event)
        self._feed_row(event, user, present=True, age=timedelta(minutes=2))
        outcome = self._snap({CHANNEL: []})
        row = self._row(event, user)
        self.assertFalse(row.present)
        self.assertIsNotNone(row.last_left_at)
        self.assertEqual(outcome.left, 1)

    def test_snapshot_keeps_manual_pin(self) -> None:
        event = self._event()
        pinned_in = self._member(event)
        pinned_out = self._member(event)
        for user, present in ((pinned_in, True), (pinned_out, False)):
            EventVoicePresence.objects.create(
                event=event,
                user=user,
                channel_id=CHANNEL,
                present=present,
                source=VoicePresenceSource.MANUAL,
            )
        outcome = self._snap({CHANNEL: [pinned_out]})
        self.assertTrue(self._row(event, pinned_in).present)
        self.assertFalse(self._row(event, pinned_out).present)
        self.assertEqual(self._row(event, pinned_in).source, "manual")
        self.assertEqual((outcome.joined, outcome.left), (0, 0))

    def test_missing_or_omitted_channel_not_cleared(self) -> None:
        missing = self._event()
        omitted = self._event(channel=OTHER_CHANNEL)
        user = self._member(missing, omitted)
        self._feed_row(missing, user, present=True, age=timedelta(minutes=2))
        self._feed_row(omitted, user, present=True, age=timedelta(minutes=2))
        with capture_logs() as logs:
            outcome = self._snap({}, missing=(CHANNEL,))
        self.assertTrue(self._row(missing, user).present)
        self.assertTrue(self._row(omitted, user).present)
        self.assertEqual(outcome.left, 0)
        warnings = [
            entry
            for entry in logs
            if entry["event"] == "voice_presence_channel_missing"
        ]
        self.assertEqual(len(warnings), 2)
        self.assertTrue(all(entry["log_level"] == "warning" for entry in warnings))

    def test_snapshot_does_not_undo_recent_gateway_leave(self) -> None:
        event = self._event(voice_presence_confirms=True)
        user = self._member(event)
        check = self._open(event).check
        self._feed_row(event, user, present=True, age=timedelta(minutes=2))
        joined_at = self._row(event, user).last_joined_at
        self._state(CHANNEL, None, user)
        outcome = self._snap({CHANNEL: [user]})
        row = self._row(event, user)
        self.assertFalse(row.present)
        self.assertEqual(row.last_joined_at, joined_at)
        self.assertEqual(
            check.entries.get(user=user).state, ReadyCheckEntryState.PENDING
        )
        self.assertEqual((outcome.joined, outcome.confirmed), (0, 0))

    def test_snapshot_does_not_undo_recent_gateway_join(self) -> None:
        event = self._event()
        user = self._member(event)
        self._state(None, CHANNEL, user)
        outcome = self._snap({CHANNEL: []})
        self.assertTrue(self._row(event, user).present)
        self.assertEqual(outcome.left, 0)

    def test_snapshot_heals_when_no_recent_transition(self) -> None:
        event = self._event()
        user = self._member(event)
        self._feed_row(event, user, present=False, age=timedelta(minutes=2))
        outcome = self._snap({CHANNEL: [user]})
        row = self._row(event, user)
        self.assertTrue(row.present)
        self.assertEqual(outcome.joined, 1)
        self.assertGreater(SNAPSHOT_GRACE, timedelta(0))

    def test_snapshot_clear_after_confirm_stays_confirmed(self) -> None:
        event = self._event(voice_presence_confirms=True)
        user = self._member(event)
        check = self._open(event).check
        self._state(None, CHANNEL, user)
        self.assertEqual(
            check.entries.get(user=user).state, ReadyCheckEntryState.CONFIRMED
        )
        self._age(event, user, SNAPSHOT_GRACE + timedelta(seconds=30))
        ledger_before = list(
            SignupLedgerEntry.objects.filter(
                event=event, subject_user=user
            ).values_list("pk", flat=True)
        )
        self.assertTrue(ledger_before)
        outcome = self._snap({CHANNEL: []})
        self.assertFalse(self._row(event, user).present)
        self.assertEqual(outcome.left, 1)
        self.assertEqual(
            check.entries.get(user=user).state, ReadyCheckEntryState.CONFIRMED
        )
        self.assertEqual(
            EventSignup.objects.get(event=event, user=user).status,
            SignupStatus.CONFIRMED,
        )
        self.assertEqual(self._rows(SignupAction.UNCONFIRMED, event), [])
        self.assertEqual(
            list(
                SignupLedgerEntry.objects.filter(
                    event=event, subject_user=user
                ).values_list("pk", flat=True)
            ),
            ledger_before,
        )

    def test_steady_state_takes_no_lock(self) -> None:
        event = self._event()
        user = self._member(event)
        self._feed_row(event, user, present=True, age=timedelta(minutes=2))
        seen_before = self._row(event, user).last_seen_at
        assert seen_before is not None
        with mock.patch("events.voice_presence.lock_event", wraps=lock_event) as locked:
            outcome = self._snap({CHANNEL: [user]})
        locked.assert_not_called()
        last_seen = self._row(event, user).last_seen_at
        assert last_seen is not None
        self.assertGreater(last_seen, seen_before)
        self.assertEqual((outcome.joined, outcome.left, outcome.events), (0, 0, 1))


class VoiceSnapshotHeartbeatTests(VoiceSnapshotTestCase):
    def _keys(self) -> set[str]:
        return set(self.redis.data)

    def test_heartbeat_written_for_visible_channels_after_apply(self) -> None:
        event = self._event()
        user = self._member(event)
        seen: list[bool] = []

        def record(guild_id: str, channel_ids: list[str]) -> None:
            seen.append(
                EventVoicePresence.objects.filter(
                    event=event, user=user, present=True
                ).exists()
            )
            touch_feed_heartbeat(guild_id, channel_ids)

        with mock.patch(
            "events.voice_presence.touch_feed_heartbeat", side_effect=record
        ):
            self._snap({CHANNEL: [user]})
        self.assertEqual(seen, [True])
        self.assertEqual(
            self._keys(),
            {
                namespaced_key(f"voice_feed:{GUILD}"),
                namespaced_key(f"voice_feed:{GUILD}:{CHANNEL}"),
            },
        )

    def test_only_missing_channels_writes_no_key(self) -> None:
        self._event()
        self._snap({}, missing=(CHANNEL,))
        self.assertEqual(self.redis.data, {})

    def test_missing_channel_has_no_channel_key_but_guild_key_from_other(
        self,
    ) -> None:
        self._event()
        self._event(channel=OTHER_CHANNEL)
        self._snap({OTHER_CHANNEL: [], CHANNEL: []}, missing=(CHANNEL,))
        self.assertEqual(
            self._keys(),
            {
                namespaced_key(f"voice_feed:{GUILD}"),
                namespaced_key(f"voice_feed:{GUILD}:{OTHER_CHANNEL}"),
            },
        )

    def test_unwatched_listed_channel_gets_no_key(self) -> None:
        self._event()
        self._snap({CHANNEL: [], "100000000000000999": []})
        self.assertNotIn(
            namespaced_key(f"voice_feed:{GUILD}:100000000000000999"), self._keys()
        )

    def test_raising_block_leaves_its_channel_key_unset(self) -> None:
        bad = self._event()
        good = self._event(channel=OTHER_CHANNEL)
        user = self._member(bad, good)
        real = voice_presence._apply_presence

        def explode(event: Event, *args: Any, **kwargs: Any) -> Transition:
            if event.pk == bad.pk:
                raise RuntimeError("boom")
            return real(event, *args, **kwargs)

        with (
            mock.patch("events.voice_presence._apply_presence", side_effect=explode),
            self.assertRaises(RuntimeError),
        ):
            self._snap({CHANNEL: [user], OTHER_CHANNEL: [user]})
        self.assertTrue(self._row(good, user).present)
        self.assertFalse(
            EventVoicePresence.objects.filter(event=bad, user=user).exists()
        )
        self.assertEqual(
            self._keys(),
            {
                namespaced_key(f"voice_feed:{GUILD}"),
                namespaced_key(f"voice_feed:{GUILD}:{OTHER_CHANNEL}"),
            },
        )


class VoiceReconcileTests(VoiceSnapshotTestCase):
    def _reconcile(self, event: Event) -> int:
        with self.captureOnCommitCallbacks(execute=True), transaction.atomic():
            return _reconcile_pending(lock_event(event), tz.now())

    def test_reconcile_ignores_previous_channel_and_guild(self) -> None:
        event = self._event(voice_presence_confirms=True)
        channel_user = self._member(event)
        guild_user = self._member(event)
        check = self._open(event).check
        channel_row = self._feed_row(
            event, channel_user, present=True, age=timedelta(seconds=40)
        )
        guild_row = self._feed_row(
            event, guild_user, present=True, age=timedelta(seconds=40)
        )
        EventVoicePresence.objects.filter(pk=channel_row.pk).update(
            channel_id=OTHER_CHANNEL
        )
        EventVoicePresence.objects.filter(pk=guild_row.pk).update(
            guild_id="200000000000000999"
        )

        self.assertFalse(_reconcile_has_work(event, tz.now()))
        self.assertEqual(self._reconcile(event), 0)
        self.assertEqual(
            set(check.entries.values_list("state", flat=True)),
            {ReadyCheckEntryState.PENDING},
        )

    def test_reconcile_confirms_present_pending_member(self) -> None:
        event = self._event(voice_presence_confirms=True)
        user = self._member(event)
        check = self._open(event).check
        self._feed_row(event, user, present=True, age=timedelta(seconds=40))
        self.assertTrue(_reconcile_has_work(event, tz.now()))
        outcome = self._snap({CHANNEL: [user]})
        entry = check.entries.get(user=user)
        self.assertEqual(entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(entry.confirmed_via, ReadyCheckConfirmVia.VOICE)
        (row,) = self._rows(SignupAction.CONFIRMED, event)
        self.assertEqual(row.means, SignupMeans.DISCORD_VOICE)
        self.assertEqual(outcome.confirmed, 1)

    def test_reconcile_ignores_manual_and_stale_rows(self) -> None:
        event = self._event(voice_presence_confirms=True)
        manual = self._member(event)
        stale = self._member(event)
        check = self._open(event).check
        EventVoicePresence.objects.create(
            event=event,
            user=manual,
            channel_id=CHANNEL,
            present=True,
            source=VoicePresenceSource.MANUAL,
            last_seen_at=tz.now(),
        )
        self._feed_row(
            event, stale, present=True, age=PRESENCE_FRESH + timedelta(seconds=5)
        )
        self.assertFalse(_reconcile_has_work(event, tz.now()))
        self.assertEqual(self._reconcile(event), 0)
        for user in (manual, stale):
            self.assertEqual(
                check.entries.get(user=user).state, ReadyCheckEntryState.PENDING
            )

    def test_reconcile_requires_both_flags(self) -> None:
        cases = (("snapshot_off", False, True), ("live_off", True, False))
        for name, at_open, live in cases:
            with self.subTest(name):
                event = self._event(voice_presence_confirms=at_open)
                user = self._member(event)
                check = self._open(event).check
                Event.objects.filter(pk=event.pk).update(voice_presence_confirms=live)
                self._feed_row(event, user, present=True, age=timedelta(seconds=40))
                event.refresh_from_db()
                self.assertFalse(_reconcile_has_work(event, tz.now()))
                self.assertEqual(self._reconcile(event), 0)
                self.assertEqual(
                    check.entries.get(user=user).state,
                    ReadyCheckEntryState.PENDING,
                )


class ManualPresenceTests(VoiceStateTestCase):
    def _manual(
        self,
        event: Event,
        user: CustomUser,
        *,
        present: bool,
        reason: str = "on stage, mic broken",
    ) -> voice_presence.ManualPresenceResult:
        with self.captureOnCommitCallbacks(execute=True):
            return set_presence_manually(
                event, user, present=present, reason=reason, actor=self.staff_actor
            )

    def test_manual_requires_signup(self) -> None:
        event = self._event()
        user = self._linked()
        with self.assertRaisesMessage(ValueError, "not_signed_up"):
            self._manual(event, user, present=True)
        self.assertFalse(EventVoicePresence.objects.filter(event=event).exists())
        self.assertEqual(self._rows(SignupAction.VOICE_PRESENCE_SET, event), [])

    def test_manual_sets_present_and_source_only(self) -> None:
        event = self._event()
        user = self._member(event)
        result = self._manual(event, user, present=True)
        row = self._row(event, user)
        self.assertEqual(result.presence.pk, row.pk)
        self.assertTrue(row.present)
        self.assertEqual(row.source, VoicePresenceSource.MANUAL)
        self.assertIsNone(row.first_joined_at)
        self.assertIsNone(row.last_joined_at)
        self.assertIsNone(row.last_left_at)
        self.assertIsNone(row.last_seen_at)
        self.assertIsNone(result.confirm)

    def test_manual_keeps_feed_timestamps(self) -> None:
        event = self._event()
        user = self._member(event)
        self._state(None, CHANNEL, user)
        joined = self._row(event, user).first_joined_at
        self._manual(event, user, present=False)
        row = self._row(event, user)
        self.assertFalse(row.present)
        self.assertEqual(row.source, VoicePresenceSource.MANUAL)
        self.assertEqual(row.first_joined_at, joined)
        self.assertIsNone(row.last_left_at)

    def test_manual_ledger_row(self) -> None:
        event = self._event()
        user = self._member(event)
        result = self._manual(event, user, present=True, reason="seen on stream")
        (entry,) = self._rows(SignupAction.VOICE_PRESENCE_SET, event)
        self.assertEqual(entry.pk, result.ledger_entry_id)
        self.assertEqual(entry.reason, "seen on stream")
        self.assertEqual(entry.actor_user, self.helper)
        self.assertEqual(entry.actor_role, ActorRole.STAFF)
        self.assertEqual(entry.subject_user, user)
        self.assertEqual(entry.correlation_id, f"vp{event.pk}:{user.pk}")
        self.assertEqual(
            entry.after["extra"]["voice"],
            {"present": True, "previous": False, "source": "manual"},
        )
        self._manual(event, user, present=False)
        _first, second = self._rows(SignupAction.VOICE_PRESENCE_SET, event)
        self.assertEqual(
            second.after["extra"]["voice"],
            {"present": False, "previous": True, "source": "manual"},
        )

    def test_manual_present_confirms_with_caused_by(self) -> None:
        event = self._event(voice_presence_confirms=True)
        user = self._member(event)
        check = self._open(event).check
        result = self._manual(event, user, present=True)
        self.assertEqual(result.confirm, ConfirmResult.CONFIRMED)
        entry = check.entries.get(user=user)
        self.assertEqual(entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(entry.confirmed_via, ReadyCheckConfirmVia.VOICE)
        (confirmed,) = self._rows(SignupAction.CONFIRMED, event)
        self.assertEqual(confirmed.caused_by_id, result.ledger_entry_id)
        self.assertEqual(confirmed.actor_role, ActorRole.STAFF)

    def test_manual_present_flag_off_no_confirm(self) -> None:
        event = self._event(voice_presence_confirms=False)
        user = self._member(event)
        check = self._open(event).check
        result = self._manual(event, user, present=True)
        self.assertIsNone(result.confirm)
        self.assertEqual(
            check.entries.get(user=user).state, ReadyCheckEntryState.PENDING
        )

    def test_manual_absent_does_not_unconfirm(self) -> None:
        event = self._event(voice_presence_confirms=True)
        user = self._member(event)
        check = self._open(event).check
        self._state(None, CHANNEL, user)
        self.assertEqual(
            check.entries.get(user=user).state, ReadyCheckEntryState.CONFIRMED
        )
        result = self._manual(event, user, present=False)
        self.assertIsNone(result.confirm)
        self.assertFalse(self._row(event, user).present)
        self.assertEqual(
            check.entries.get(user=user).state, ReadyCheckEntryState.CONFIRMED
        )
        signup = EventSignup.objects.nocache().get(event=event, user=user)
        self.assertEqual(signup.status, SignupStatus.CONFIRMED)
        self.assertEqual(self._rows(SignupAction.UNCONFIRMED, event), [])

    def test_manual_pin_then_unpin_gives_no_conduct_credit(self) -> None:
        event = self._event()
        user = self._member(event)
        self._manual(event, user, present=True)
        self._manual(event, user, present=False)
        self.assertEqual(_voice_user_ids(event, {user.pk}), set())
