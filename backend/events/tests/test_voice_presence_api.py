from datetime import timedelta

from django.test import override_settings
from django.utils import timezone as tz

from app.models import CustomUser
from app.redis_client import set_client_for_tests
from app.redis_keys import namespaced_key
from events.constants import (
    ActorRole,
    SignupAction,
    SignupStatus,
    VoicePresenceSource,
)
from events.models import Event, EventSignup, EventVoicePresence, SignupLedgerEntry
from events.ready_check_constants import ReadyCheckConfirmVia, ReadyCheckEntryState
from events.tests.test_ready_check_api import ReadyCheckApiTestCase
from events.tests.test_signup_post_lock import FakeRedis

GUILD = "200000000000000532"
CHANNEL = "100000000000000532"


@override_settings(READY_CHECK_AUTOMATIC_LIVE=True)
class VoicePresenceApiTests(ReadyCheckApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org.discord_server_id = GUILD
        self.org.save()
        self.redis = FakeRedis()
        set_client_for_tests(self.redis)
        self.addCleanup(set_client_for_tests, None)

    def _voice_event(self, **overrides: object) -> Event:
        fields: dict[str, object] = {
            "scheduled_at": tz.now() + timedelta(hours=1),
            "event_voice_channel_id": CHANNEL,
        }
        fields.update(overrides)
        return self._event(**fields)

    def _path(self, event: Event) -> str:
        return f"/api/events/{event.pk}/voice-presence/"

    def _body(
        self, user: CustomUser, *, present: bool = True, reason: str = "on stage"
    ) -> dict[str, object]:
        return {"user_id": user.pk, "present": present, "reason": reason}

    def _voice_rows(self, event: Event) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                event=event, action=SignupAction.VOICE_PRESENCE_SET
            ).order_by("pk")
        )

    def test_allowed_roles_succeed_on_get_and_post(self) -> None:
        for role, get_user in self._allowed_roles().items():
            with self.subTest(role=role):
                event = self._voice_event()
                target = self._signup(event)
                actor = get_user(event)
                resp = self._request(actor, "get", self._path(event))
                self.assertEqual(resp.status_code, 200, resp.content)
                resp = self._post(actor, self._path(event), self._body(target.user))
                self.assertEqual(resp.status_code, 200, resp.content)

    def test_denied_roles_get_403_on_get_and_post(self) -> None:
        for role, get_user in self._denied_roles().items():
            with self.subTest(role=role):
                event = self._voice_event()
                target = self._signup(event)
                actor = get_user(event)
                before = self._ledger_count(event)
                resp = self._request(actor, "get", self._path(event))
                self.assertEqual(resp.status_code, 403, resp.content)
                resp = self._post(actor, self._path(event), self._body(target.user))
                self.assertEqual(resp.status_code, 403, resp.content)
                self.assertEqual(self._ledger_count(event), before)
                self.assertFalse(
                    EventVoicePresence.objects.filter(event=event).exists()
                )

    def test_anonymous_refused_on_get_and_post(self) -> None:
        event = self._voice_event()
        target = self._signup(event)
        before = self._ledger_count(event)
        resp = self._request(None, "get", self._path(event))
        self.assertIn(resp.status_code, (401, 403), resp.content)
        resp = self._post(None, self._path(event), self._body(target.user))
        self.assertIn(resp.status_code, (401, 403), resp.content)
        self.assertEqual(self._ledger_count(event), before)
        self.assertFalse(EventVoicePresence.objects.filter(event=event).exists())

    def test_missing_or_blank_reason_400(self) -> None:
        event = self._voice_event()
        target = self._signup(event)
        bodies: dict[str, dict[str, object]] = {
            "missing": {"user_id": target.user_id, "present": True},
            "blank": self._body(target.user, reason="   "),
            "too_long": self._body(target.user, reason="x" * 501),
            "no_present": {"user_id": target.user_id, "reason": "here"},
        }
        for case, body in bodies.items():
            with self.subTest(case=case):
                resp = self._post(self.admin, self._path(event), body)
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertEqual(resp.json()["code"], "invalid")
                self.assertIn("error", resp.json())
        self.assertEqual(self._voice_rows(event), [])

    def test_reason_is_stripped(self) -> None:
        event = self._voice_event()
        target = self._signup(event)
        resp = self._post(
            self.admin, self._path(event), self._body(target.user, reason="  here  ")
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        (entry,) = self._voice_rows(event)
        self.assertEqual(entry.reason, "here")

    def test_no_signup_400_not_signed_up(self) -> None:
        event = self._voice_event()
        outsider = self.make_user()
        resp = self._post(self.admin, self._path(event), self._body(outsider))
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "not_signed_up")
        self.assertIn("error", resp.json())
        self.assertFalse(EventVoicePresence.objects.filter(event=event).exists())
        self.assertEqual(self._voice_rows(event), [])

    def test_unknown_user_404(self) -> None:
        event = self._voice_event()
        missing = CustomUser.objects.order_by("-pk").first()
        assert missing is not None
        body = {"user_id": missing.pk + 1000, "present": True, "reason": "here"}
        resp = self._post(self.admin, self._path(event), body)
        self.assertEqual(resp.status_code, 404, resp.content)
        self.assertEqual(self._voice_rows(event), [])

    def test_unknown_event_404(self) -> None:
        resp = self._request(self.admin, "get", "/api/events/999999/voice-presence/")
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_override_response_and_ledger(self) -> None:
        event = self._voice_event()
        target = self._signup(event)
        resp = self._post(
            self.helper,
            self._path(event),
            self._body(target.user, reason="seen on stream"),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        (entry,) = self._voice_rows(event)
        self.assertEqual(data["ledger_entry_id"], entry.pk)
        self.assertIsNone(data["confirm"])
        self.assertEqual(entry.reason, "seen on stream")
        self.assertEqual(entry.actor_user, self.helper)
        self.assertEqual(entry.actor_role, ActorRole.STAFF)
        self.assertEqual(entry.subject_user, target.user)
        presence = data["presence"]
        self.assertEqual(presence["user_id"], target.user_id)
        self.assertTrue(presence["present"])
        self.assertEqual(presence["source"], VoicePresenceSource.MANUAL)
        for key in (
            "first_joined_at",
            "last_joined_at",
            "last_left_at",
            "last_seen_at",
        ):
            self.assertIn(key, presence)

    def test_override_confirm_has_caused_by(self) -> None:
        event = self._voice_event(voice_presence_confirms=True)
        target = self._signup(event)
        check = self._open(event)
        resp = self._post(self.admin, self._path(event), self._body(target.user))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["confirm"], "confirmed")
        entry = self._entry(check, target)
        self.assertEqual(entry.state, ReadyCheckEntryState.CONFIRMED)
        self.assertEqual(entry.confirmed_via, ReadyCheckConfirmVia.VOICE)
        confirmed = SignupLedgerEntry.objects.get(
            event=event, action=SignupAction.CONFIRMED, subject_user=target.user
        )
        self.assertEqual(confirmed.caused_by_id, resp.json()["ledger_entry_id"])

    def test_override_absent_does_not_unconfirm(self) -> None:
        event = self._voice_event(voice_presence_confirms=True)
        target = self._signup(event)
        check = self._open(event)
        self._post(self.admin, self._path(event), self._body(target.user))
        resp = self._post(
            self.admin, self._path(event), self._body(target.user, present=False)
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(resp.json()["confirm"])
        self.assertFalse(resp.json()["presence"]["present"])
        self.assertEqual(
            self._entry(check, target).state, ReadyCheckEntryState.CONFIRMED
        )
        signup = EventSignup.objects.nocache().get(pk=target.pk)
        self.assertEqual(signup.status, SignupStatus.CONFIRMED)
        self.assertFalse(
            SignupLedgerEntry.objects.filter(
                event=event, action=SignupAction.UNCONFIRMED
            ).exists()
        )

    def test_get_returns_feed_age_and_rows(self) -> None:
        event = self._voice_event()
        target = self._signup(event)
        self._post(self.admin, self._path(event), self._body(target.user))
        stamp = str(tz.now().timestamp() - 30)
        self.redis.set(namespaced_key(f"voice_feed:{GUILD}"), stamp)
        self.redis.set(namespaced_key(f"voice_feed:{GUILD}:{CHANNEL}"), stamp)
        resp = self._request(self.admin, "get", self._path(event))
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["voice_channel_id"], CHANNEL)
        self.assertEqual(data["feed"]["guild_id"], GUILD)
        self.assertIsInstance(data["feed"]["age_seconds"], float)
        self.assertIsInstance(data["feed"]["channel_age_seconds"], float)
        self.assertGreaterEqual(data["feed"]["age_seconds"], 29.0)
        (row,) = data["presences"]
        self.assertEqual(
            set(row),
            {
                "user_id",
                "present",
                "source",
                "first_joined_at",
                "last_joined_at",
                "last_left_at",
                "last_seen_at",
            },
        )
        self.assertEqual(row["user_id"], target.user_id)
        self.assertEqual(row["source"], VoicePresenceSource.MANUAL)

    def test_get_without_feed_or_guild(self) -> None:
        self.org.discord_server_id = ""
        self.org.save()
        event = self._voice_event(event_voice_channel_id="")
        resp = self._request(self.admin, "get", self._path(event))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            resp.json(),
            {
                "feed": {
                    "guild_id": None,
                    "age_seconds": None,
                    "channel_age_seconds": None,
                },
                "voice_channel_id": "",
                "presences": [],
            },
        )
