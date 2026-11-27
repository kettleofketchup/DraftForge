from typing import Any, get_args

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APIClient

from discordbot.dm_ledger import ErrorClass
from discordbot.models import DiscordDM, DMKind, DMStatus, DMSubject
from discordbot.schemas import (
    DMErrorClassValue,
    DMKindValue,
    DMStatusValue,
    DMSubjectValue,
)

INTERNAL_TOKEN = "test-token"
CHANNEL_ID = "777000111"
MESSAGE_ID = "888000222"


def _claim_body(key: str = "k1", token: str = "tok-a", **extra: Any) -> dict[str, Any]:
    return {
        "kind": DMKind.SIGNUP_REMINDER.value,
        "idempotency_key": key,
        "claim_token": token,
        "discord_user_id": "1001",
        "context": {"discord_event_id": 5},
        "has_components": True,
        **extra,
    }


class LedgerSchemaParityTests(SimpleTestCase):
    def test_literals_match_model_enums(self) -> None:
        self.assertEqual(set(get_args(DMKindValue)), set(DMKind.values))
        self.assertEqual(set(get_args(DMStatusValue)), set(DMStatus.values))
        self.assertEqual(set(get_args(DMSubjectValue)), set(DMSubject.values))
        self.assertEqual(set(get_args(DMErrorClassValue)), set(get_args(ErrorClass)))


@override_settings(INTERNAL_SERVICE_TOKEN=INTERNAL_TOKEN)
class InternalDMViewsTests(TestCase):
    def setUp(self) -> None:
        self.api = APIClient()
        self.api.credentials(HTTP_X_INTERNAL_TOKEN=INTERNAL_TOKEN)

    def _post(
        self,
        name: str,
        body: dict[str, Any],
        client: APIClient | None = None,
        **kw: int,
    ) -> Response:
        return (client or self.api).post(reverse(name, kwargs=kw), body, format="json")

    def _claim(self, **kw: Any) -> Response:
        return self._post("internal_dm_claim", _claim_body(**kw))

    def _finalize(self, dm_id: int, token: str = "tok-a", **extra: Any) -> Response:
        return self._post(
            "internal_dm_finalize",
            {"claim_token": token, "status": "sent", **extra},
            dm_id=dm_id,
        )

    def test_requires_internal_auth(self) -> None:
        wrong = APIClient()
        wrong.credentials(HTTP_X_INTERNAL_TOKEN="wrong")
        for client in (APIClient(), wrong):
            for name, kw in (
                ("internal_dm_claim", {}),
                ("internal_dm_sending", {"dm_id": 1}),
                ("internal_dm_finalize", {"dm_id": 1}),
                ("internal_dm_click", {}),
            ):
                resp = self._post(name, {}, client, **kw)
                self.assertIn(resp.status_code, (401, 403), name)
        self.assertFalse(DiscordDM.objects.exists())

    def test_claim_201_new(self) -> None:
        resp = self._claim()
        self.assertEqual(resp.status_code, 201)
        row = DiscordDM.objects.get()
        self.assertEqual(
            resp.json(), {"id": row.pk, "status": "pending", "attempts": 1}
        )
        self.assertEqual(row.context, {"discord_event_id": 5})
        self.assertTrue(row.has_components)

    def test_claim_skip_status_is_terminal(self) -> None:
        resp = self._claim(initial_status="skipped_test_mode")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["status"], "skipped_test_mode")

    def test_claim_same_token_returns_200_same_id(self) -> None:
        first = self._claim()
        second = self._claim()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(DiscordDM.objects.count(), 1)

    def test_claim_conflict_409_body_is_id_status_only(self) -> None:
        first = self._claim()
        resp = self._claim(token="tok-b")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(set(resp.json()), {"id", "status"})
        self.assertEqual(resp.json(), {"id": first.json()["id"], "status": "pending"})

    def test_claim_invalid_400(self) -> None:
        for body in (
            {},
            _claim_body(kind="nope"),
            _claim_body(claim_token=""),
            _claim_body(discord_user_id="not-a-snowflake"),
            _claim_body(subject_type="event"),
            _claim_body(initial_status="sent"),
        ):
            resp = self._post("internal_dm_claim", body)
            self.assertEqual(resp.status_code, 400, body)
            self.assertEqual(resp.json(), {"error": "invalid_request"})
        self.assertFalse(DiscordDM.objects.exists())

    def test_claim_bad_context_400(self) -> None:
        resp = self._claim(context={"content": "hello"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json(), {"error": "invalid_request"})
        self.assertFalse(DiscordDM.objects.exists())

    def test_sending_204_and_409(self) -> None:
        dm_id = self._claim().json()["id"]
        ok = self._post("internal_dm_sending", {"claim_token": "tok-a"}, dm_id=dm_id)
        self.assertEqual(ok.status_code, 204)
        self.assertIsNotNone(DiscordDM.objects.get().send_started_at)
        wrong = self._post("internal_dm_sending", {"claim_token": "tok-b"}, dm_id=dm_id)
        self.assertEqual(wrong.status_code, 409)
        missing = self._post("internal_dm_sending", {"claim_token": "tok-a"}, dm_id=999)
        self.assertEqual(missing.status_code, 409)
        bad = self._post("internal_dm_sending", {}, dm_id=dm_id)
        self.assertEqual(bad.status_code, 400)

    def test_finalize_200_409_404(self) -> None:
        dm_id = self._claim().json()["id"]
        self.assertEqual(self._finalize(dm_id, token="tok-b").status_code, 409)
        self.assertEqual(self._finalize(999).status_code, 404)
        resp = self._finalize(
            dm_id, discord_channel_id=CHANNEL_ID, discord_message_id=MESSAGE_ID
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"id": dm_id, "status": "sent"})
        row = DiscordDM.objects.get()
        self.assertEqual(row.status, DMStatus.SENT)
        self.assertEqual(row.discord_message_id, MESSAGE_ID)
        self.assertEqual(self._finalize(dm_id, status="failed").status_code, 409)
        self.assertEqual(self._finalize(dm_id, status="pending").status_code, 400)
        self.assertEqual(self._finalize(dm_id, error_class="bogus").status_code, 400)

    def test_finalize_failed_retryable_from_class(self) -> None:
        dm_id = self._claim().json()["id"]
        resp = self._finalize(
            dm_id,
            status="failed",
            error_class="pre_send",
            http_status=400,
            error_code=1,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(DiscordDM.objects.get().retryable)

    def test_finalize_repeat_same_token_200(self) -> None:
        dm_id = self._claim().json()["id"]
        first = self._finalize(dm_id, discord_message_id=MESSAGE_ID)
        repeat = self._finalize(dm_id, discord_message_id=MESSAGE_ID)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat.json(), first.json())

    def test_click_always_204(self) -> None:
        dm_id = self._claim().json()["id"]
        self._finalize(dm_id, discord_message_id=MESSAGE_ID)
        hit = self._post(
            "internal_dm_click",
            {"discord_message_id": MESSAGE_ID, "discord_user_id": "1001"},
        )
        other_user = self._post(
            "internal_dm_click",
            {"discord_message_id": MESSAGE_ID, "discord_user_id": "2002"},
        )
        unknown = self._post(
            "internal_dm_click",
            {"discord_message_id": "123456", "discord_user_id": "1001"},
        )
        for resp in (hit, other_user, unknown):
            self.assertEqual(resp.status_code, 204)
            self.assertEqual(resp.content, b"")
        self.assertEqual(DiscordDM.objects.get().click_count, 1)
        bad = self._post("internal_dm_click", {"discord_message_id": "x"})
        self.assertEqual(bad.status_code, 400)

    def test_no_response_contains_channel_or_message_id(self) -> None:
        responses = [self._claim()]
        dm_id = responses[0].json()["id"]
        responses.append(
            self._post("internal_dm_sending", {"claim_token": "tok-a"}, dm_id=dm_id)
        )
        finalize_body = {
            "discord_channel_id": CHANNEL_ID,
            "discord_message_id": MESSAGE_ID,
        }
        responses.append(self._finalize(dm_id, **finalize_body))
        responses.append(self._finalize(dm_id, **finalize_body))
        responses.append(self._finalize(dm_id, token="tok-b", **finalize_body))
        responses.append(self._claim())
        responses.append(self._claim(token="tok-b"))
        responses.append(
            self._post(
                "internal_dm_click",
                {"discord_message_id": MESSAGE_ID, "discord_user_id": "1001"},
            )
        )
        for resp in responses:
            text = resp.content.decode()
            for needle in (CHANNEL_ID, MESSAGE_ID, "channel", "message"):
                self.assertNotIn(needle, text, resp.status_code)
