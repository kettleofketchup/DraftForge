from datetime import timedelta
from typing import Any

from django.test import override_settings
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.redis_keys import namespaced_key
from events.models import Event, ReadyCheck
from events.ready_check_constants import ReadyCheckEntryState
from events.tests.test_voice_presence import (
    CHANNEL,
    GUILD,
    OTHER_CHANNEL,
    VoiceSnapshotTestCase,
)
from events.voice_presence import SNAPSHOT_GRACE

INTERNAL_TOKEN = "test-token"
WATCHED = "internal_discord_voice_watched_channels"
STATE = "internal_discord_voice_state"
SNAPSHOT = "internal_discord_voice_snapshot"


@override_settings(INTERNAL_SERVICE_TOKEN=INTERNAL_TOKEN)
class InternalVoiceViewsTests(VoiceSnapshotTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.api = APIClient()
        self.api.credentials(HTTP_X_INTERNAL_TOKEN=INTERNAL_TOKEN)

    def _post(self, name: str, body: dict[str, Any]) -> Response:
        with self.captureOnCommitCallbacks(execute=True):
            return self.api.post(reverse(name), body, format="json")

    def _state_body(
        self, user_discord_id: str, before: str | None, after: str | None
    ) -> dict[str, Any]:
        return {
            "guild_id": GUILD,
            "discord_user_id": user_discord_id,
            "before_channel_id": before,
            "after_channel_id": after,
        }

    def _snap_body(self, channels: dict[str, list[str]]) -> dict[str, Any]:
        return {
            "guild_id": GUILD,
            "channels": [
                {"channel_id": channel, "member_ids": members}
                for channel, members in channels.items()
            ],
            "missing_channel_ids": [],
        }

    def _checked(self, *, flag: bool) -> tuple[Event, ReadyCheck]:
        event = self._event(voice_presence_confirms=flag)
        self._member(event)
        return event, self._open(event).check

    def test_routes_reject_missing_and_wrong_token(self) -> None:
        anon = APIClient()
        wrong = APIClient()
        wrong.credentials(HTTP_X_INTERNAL_TOKEN="wrong")
        for client in (anon, wrong):
            responses = [
                client.get(reverse(WATCHED)),
                client.post(reverse(STATE), {}, format="json"),
                client.post(reverse(SNAPSHOT), {}, format="json"),
            ]
            for response in responses:
                self.assertIn(response.status_code, (401, 403))

    def test_watched_channels_lists_watched(self) -> None:
        event = self._event()
        response = self.api.get(reverse(WATCHED))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "channels": [
                    {"guild_id": GUILD, "channel_id": CHANNEL, "event_ids": [event.pk]}
                ],
                "ttl_seconds": 60,
                "available": True,
            },
        )

    def test_state_join_returns_counts(self) -> None:
        event = self._event()
        user = self._member(event)
        response = self._post(
            STATE, self._state_body(str(user.discordId), None, CHANNEL)
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIs(data["success"], True)
        self.assertEqual(data["joined"], 1)
        self.assertEqual(data["events"], 1)
        self.assertTrue(self._row(event, user).present)

    def test_state_unwatched_returns_not_watched(self) -> None:
        user = self._linked()
        response = self._post(
            STATE, self._state_body(str(user.discordId), None, OTHER_CHANNEL)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "not_watched")

    def test_state_same_channel_noop(self) -> None:
        event = self._event()
        user = self._member(event)
        response = self._post(
            STATE, self._state_body(str(user.discordId), CHANNEL, CHANNEL)
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIs(data["success"], True)
        self.assertEqual(data["detail"], "")
        self.assertEqual(data["joined"], 0)

    def test_bad_id_returns_400(self) -> None:
        for bad in ("abc", "1" * 21, "", "١٢٣"):
            response = self._post(STATE, self._state_body(bad, None, CHANNEL))
            self.assertEqual(response.status_code, 400, bad)
            self.assertEqual(response.json()["error"], "invalid_request")
        response = self._post(STATE, self._state_body("123", None, "abc"))
        self.assertEqual(response.status_code, 400)
        response = self._post(SNAPSHOT, self._snap_body({CHANNEL: ["abc"]}))
        self.assertEqual(response.status_code, 400)

    def test_snapshot_caps_return_400(self) -> None:
        channels = {str(10**17 + n): [] for n in range(101)}
        self.assertEqual(
            self._post(SNAPSHOT, self._snap_body(channels)).status_code, 400
        )
        members = [str(10**17 + n) for n in range(5001)]
        response = self._post(SNAPSHOT, self._snap_body({CHANNEL: members}))
        self.assertEqual(response.status_code, 400)
        at_cap = self._post(
            SNAPSHOT, self._snap_body({str(10**17 + n): [] for n in range(100)})
        )
        self.assertEqual(at_cap.status_code, 200)

    def test_snapshot_duplicate_member_ids_deduped(self) -> None:
        event = self._event()
        user = self._member(event)
        discord_id = str(user.discordId)
        response = self._post(
            SNAPSHOT, self._snap_body({CHANNEL: [discord_id, discord_id]})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["joined"], 1)
        self.assertTrue(self._row(event, user).present)

    def test_snapshot_applies_and_sets_heartbeat(self) -> None:
        event = self._event()
        user = self._member(event)
        response = self._post(
            SNAPSHOT, self._snap_body({CHANNEL: [str(user.discordId)]})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["success"], True)
        self.assertIn(namespaced_key(f"voice_feed:{GUILD}:{CHANNEL}"), self.redis.data)
        self.assertIn(namespaced_key(f"voice_feed:{GUILD}"), self.redis.data)

    def test_state_unlinked_user_returns_user_not_linked(self) -> None:
        self._event()
        response = self._post(
            STATE, self._state_body("999999999999999999", None, CHANNEL)
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["detail"], "user_not_linked")
        self.assertEqual(data["unknown_users"], 1)

    def test_snapshot_clears_stale_returns_left(self) -> None:
        event = self._event()
        user = self._member(event)
        self._feed_row(
            event, user, present=True, age=SNAPSHOT_GRACE + timedelta(seconds=5)
        )
        response = self._post(SNAPSHOT, self._snap_body({CHANNEL: []}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["left"], 1)
        self.assertFalse(self._row(event, user).present)

    def test_state_join_confirm_flag_on_off(self) -> None:
        _, on_check = self._checked(flag=True)
        on_user = on_check.entries.get().user
        response = self._post(
            STATE, self._state_body(str(on_user.discordId), None, CHANNEL)
        )
        self.assertEqual(response.json()["confirmed"], 1)
        self.assertEqual(
            on_check.entries.get(user=on_user).state, ReadyCheckEntryState.CONFIRMED
        )

        off_event = self._event(channel=OTHER_CHANNEL, voice_presence_confirms=False)
        off_user = self._member(off_event)
        off_check = self._open(off_event).check
        response = self._post(
            STATE, self._state_body(str(off_user.discordId), None, OTHER_CHANNEL)
        )
        data = response.json()
        self.assertEqual(data["joined"], 1)
        self.assertEqual(data["confirmed"], 0)
        self.assertEqual(
            off_check.entries.get(user=off_user).state, ReadyCheckEntryState.PENDING
        )

    def test_state_linked_without_signup_returns_not_signed_up(self) -> None:
        self._event()
        user = self._linked()
        response = self._post(
            STATE, self._state_body(str(user.discordId), None, CHANNEL)
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["not_signed_up"], 1)
        self.assertEqual(data["joined"], 0)

    def test_snapshot_log_has_counts_not_members(self) -> None:
        event = self._event()
        user = self._member(event)
        with capture_logs() as logs:
            self._post(SNAPSHOT, self._snap_body({CHANNEL: [str(user.discordId)]}))
        (entry,) = [
            log for log in logs if log["event"] == "internal_voice_snapshot_processed"
        ]
        self.assertEqual(entry["system"], "discord")
        self.assertEqual(entry["subsystem"], "dispatch")
        self.assertEqual(entry["joined"], 1)
        self.assertEqual(entry["channels"], 1)
        self.assertNotIn("member_ids", entry)
        self.assertNotIn("channel_ids", entry)
