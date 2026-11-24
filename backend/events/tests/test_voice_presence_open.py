from datetime import datetime, timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone as tz

from app.models import CustomUser
from events.constants import (
    ActorRole,
    EventState,
    SignupAction,
    SignupMeans,
    SignupStatus,
    VoicePresenceSource,
)
from events.ledger import SignupActor, record_signup_change
from events.models import Event, EventVoicePresence, RollCallMode
from events.ready_check import (
    ConfirmResult,
    confirm_ready,
    trusted_present_user_ids,
)
from events.ready_check_constants import (
    PRESENCE_FRESH,
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
)
from events.ready_check_signals import ready_check_opened
from events.tests.test_ready_check_service import NOTIFY, ReadyCheckServiceTestCase

VOICE_CHANNEL = "100000000000000532"


class VoicePresenceOpenTests(ReadyCheckServiceTestCase):
    def _voice_on(self, event: Event | None = None) -> Event:
        target = event or self.rc_event
        target.voice_presence_confirms = True
        target.event_voice_channel_id = VOICE_CHANNEL
        target.save()
        return target

    def _present(
        self,
        user: CustomUser,
        *,
        event: Event | None = None,
        source: str = VoicePresenceSource.FEED,
        last_seen_at: datetime | None = None,
    ) -> EventVoicePresence:
        return EventVoicePresence.objects.create(
            event=event or self.rc_event,
            user=user,
            guild_id=(event or self.rc_event).organization.discord_server_id or "",
            channel_id=VOICE_CHANNEL,
            present=True,
            source=source,
            last_seen_at=last_seen_at if last_seen_at is not None else tz.now(),
        )

    def test_presence_fresh_is_180_seconds(self) -> None:
        self.assertEqual(PRESENCE_FRESH, timedelta(seconds=180))

    def test_confirm_ready_records_caused_by(self) -> None:
        signup = self._signup(SignupStatus.APPROVED)
        check = self._open().check
        cause = record_signup_change(
            event=self.rc_event,
            subject=signup.user,
            actor=self.staff_actor,
            action=SignupAction.VOICE_PRESENCE_SET,
            signup=signup,
            reason="cause",
        )
        with self.captureOnCommitCallbacks(execute=True):
            result = confirm_ready(
                self.rc_event,
                signup.user,
                via=ReadyCheckConfirmVia.VOICE,
                actor=SignupActor.voice(signup.user),
                caused_by=cause,
            )
        self.assertEqual(result, ConfirmResult.CONFIRMED)
        (row,) = self._rows(SignupAction.CONFIRMED)
        self.assertEqual(row.caused_by_id, cause.pk)
        self.assertEqual(row.correlation_id, f"rc{check.pk}:confirm")

    def test_previous_channel_presence_does_not_confirm_at_open(self) -> None:
        self._voice_on()
        signup = self._signup(SignupStatus.APPROVED)
        row = self._present(signup.user)
        row.channel_id = "100000000000000999"
        row.save()
        check = self._open().check
        self.assertEqual(self._entry(check, signup).state, ReadyCheckEntryState.PENDING)

    def test_previous_guild_presence_does_not_confirm_at_open(self) -> None:
        self._voice_on()
        signup = self._signup(SignupStatus.APPROVED)
        row = self._present(signup.user)
        row.guild_id = "200000000000000999"
        row.save()
        check = self._open().check
        self.assertEqual(self._entry(check, signup).state, ReadyCheckEntryState.PENDING)

    def test_present_member_confirmed_at_open(self) -> None:
        self._voice_on()
        signup = self._signup(SignupStatus.APPROVED)
        self._present(signup.user)
        check = self._open().check
        entry = self._entry(check, signup)
        self.assertEqual(entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(entry.confirmed_via, "voice")
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.CONFIRMED)
        (row,) = self._rows(SignupAction.CONFIRMED)
        self.assertEqual(row.means, SignupMeans.DISCORD_VOICE)
        self.assertEqual(row.actor_role, ActorRole.MEMBER)

    def test_opened_signal_excludes_voice_confirmed(self) -> None:
        self._voice_on()
        present = self._signup(SignupStatus.APPROVED)
        absent = self._signup(SignupStatus.APPROVED)
        self._present(present.user)
        with self._listen(ready_check_opened) as opened:
            self._open()
        opened.assert_called_once()
        user_ids = opened.call_args.kwargs["change"].user_ids
        self.assertIn(absent.user_id, user_ids)
        self.assertNotIn(present.user_id, user_ids)

    def test_open_transition_extra_has_voice_confirmed(self) -> None:
        self._voice_on()
        present = self._signup(SignupStatus.APPROVED)
        self._signup(SignupStatus.APPROVED)
        self._present(present.user)
        self._open()
        (row,) = [
            r
            for r in self._rows(SignupAction.READY_CHECK_TRANSITION)
            if r.reason == "open"
        ]
        extra = row.after["extra"]
        self.assertEqual(extra["voice_confirmed"], 1)
        self.assertEqual(extra["confirmed"], 1)
        self.assertEqual(extra["pending"], 1)
        self.assertEqual(extra["asked"], 2)

    def test_stale_feed_row_not_confirmed_at_open(self) -> None:
        self._voice_on()
        signup = self._signup(SignupStatus.APPROVED)
        self._present(signup.user, last_seen_at=tz.now() - timedelta(seconds=181))
        check = self._open().check
        self.assertEqual(self._entry(check, signup).state, ReadyCheckEntryState.PENDING)

    def test_manual_row_not_confirmed_at_open(self) -> None:
        self._voice_on()
        signup = self._signup(SignupStatus.APPROVED)
        self._present(signup.user, source=VoicePresenceSource.MANUAL)
        check = self._open().check
        self.assertEqual(self._entry(check, signup).state, ReadyCheckEntryState.PENDING)
        self.assertEqual(self._rows(SignupAction.CONFIRMED), [])

    def test_flag_off_confirms_nobody(self) -> None:
        self.rc_event.event_voice_channel_id = VOICE_CHANNEL
        self.rc_event.save()
        signup = self._signup(SignupStatus.APPROVED)
        self._present(signup.user)
        check = self._open().check
        self.assertEqual(self._entry(check, signup).state, ReadyCheckEntryState.PENDING)
        self.assertEqual(self._rows(SignupAction.CONFIRMED), [])

    @override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
    def test_automatic_mode_reset_member_reconfirmed_by_voice(self) -> None:
        event = self._voice_on(
            self.make_event(
                roll_call_enabled=True, roll_call_mode=RollCallMode.AUTOMATIC
            )
        )
        signup = self._signup(SignupStatus.CONFIRMED, event=event)
        self._present(signup.user, event=event)
        check = self._open(event).check
        self.assertEqual(check.settings_snapshot["effective_mode"], "automatic")
        entry = self._entry(check, signup)
        self.assertEqual(entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(entry.confirmed_via, ReadyCheckConfirmVia.VOICE)
        signup.refresh_from_db()
        self.assertEqual(signup.status, SignupStatus.CONFIRMED)
        self.assertEqual(len(self._rows(SignupAction.UNCONFIRMED, event)), 1)
        self.assertEqual(len(self._rows(SignupAction.CONFIRMED, event)), 1)

    def test_open_signup_post_refresh_count(self) -> None:
        event = self._voice_on(self.make_event(state=EventState.ROLL_CALL))
        for _ in range(2):
            signup = self._signup(SignupStatus.APPROVED, event=event)
            self._present(signup.user, event=event)
        with mock.patch(NOTIFY) as notify:
            self._open(event)
        self.assertEqual(notify.call_count, 3)

    def test_trusted_present_user_ids_filters(self) -> None:
        self._voice_on()
        now = tz.now()
        fresh = self.make_user()
        stale = self.make_user()
        manual = self.make_user()
        absent = self.make_user()
        self._present(fresh, last_seen_at=now)
        self._present(stale, last_seen_at=now - PRESENCE_FRESH - timedelta(seconds=1))
        self._present(manual, source=VoicePresenceSource.MANUAL)
        EventVoicePresence.objects.create(
            event=self.rc_event, user=absent, present=False, last_seen_at=now
        )
        other = self.make_event()
        self._present(self.make_user(), event=other)
        self.assertEqual(trusted_present_user_ids(self.rc_event, now), {fresh.pk})
