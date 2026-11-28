"""HTTP-interactions mode handler: discordbot.views.handle_message_component."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from discordbot import dm_ledger
from discordbot.dm_ledger import DMClaim, DMFinal
from discordbot.internal_client.leadership_actions import SAVE_FAILED
from discordbot.models import DiscordDM, DMKind, DMStatus
from discordbot.schemas import ClickResult
from discordbot.tasks import complete_review_click
from discordbot.views import handle_message_component

ENQUEUE = "discordbot.tasks.complete_review_click.apply_async"


def _payload(custom_id: str, *, guild_id: str | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "data": {"custom_id": custom_id},
        "message": {"id": "9001", "channel_id": "8001"},
    }
    if guild_id is None:
        payload["user"] = {"id": "1001", "username": "u"}
    else:
        payload["guild_id"] = guild_id
        payload["member"] = {"user": {"id": "1001", "username": "u"}}
    return payload


class HTTPModeDMClickTests(TestCase):
    def setUp(self) -> None:
        now = timezone.now()
        claim = dm_ledger.claim(
            DMClaim(
                kind=DMKind.SIGNUP_REMINDER,
                idempotency_key="k-views",
                claim_token="tok",
                discord_user_id="1001",
                has_components=True,
            ),
            now=now,
        )
        dm_ledger.finalize(
            claim.id,
            DMFinal(
                status=DMStatus.SENT,
                discord_channel_id="8001",
                discord_message_id="9001",
            ),
            claim_token="tok",
            now=now,
        )
        self.row_id = claim.id

    def _clicks(self) -> int:
        return DiscordDM.objects.get(pk=self.row_id).click_count

    def test_http_mode_dm_click_records(self) -> None:
        response = handle_message_component(_payload("event_signup:5", guild_id=None))
        self.assertEqual(json.loads(response.content), {"type": 6})
        self.assertEqual(self._clicks(), 1)

    def test_http_mode_guild_click_no_record(self) -> None:
        handle_message_component(_payload("event_signup:5", guild_id="77"))
        self.assertEqual(self._clicks(), 0)

    def test_http_mode_lr_click_not_recorded(self) -> None:
        with patch(ENQUEUE):
            handle_message_component(_payload("lr:1:2:3", guild_id=None))
        self.assertEqual(self._clicks(), 0)


def _lr_payload(custom_id: str = "lr:7:8:4") -> dict[str, Any]:
    payload = _payload(custom_id, guild_id=None)
    payload.update(
        {
            "application_id": "9",
            "token": "private-token",
            "id": "4001",
            "channel_id": "8001",
        }
    )
    return payload


class HTTPModeReviewClickTests(SimpleTestCase):
    def test_http_lr_returns_type6_and_enqueues(self) -> None:
        with patch(ENQUEUE) as enqueue:
            response = handle_message_component(_lr_payload())
        self.assertEqual(json.loads(response.content), {"type": 6})
        kwargs = enqueue.call_args.kwargs
        self.assertEqual(
            kwargs["args"],
            [
                {
                    "application_id": "9",
                    "interaction_token": "private-token",
                    "click": {
                        "discord_user_id": "1001",
                        "discord_message_id": "9001",
                        "discord_channel_id": "8001",
                        "interaction_id": "4001",
                        "snapshot_id": 7,
                        "trait_id": 8,
                        "score": 4,
                    },
                }
            ],
        )
        self.assertIn("redacted", kwargs["argsrepr"])
        self.assertNotIn("private-token", kwargs["argsrepr"])
        self.assertGreaterEqual(kwargs["expires"], 10 * 60)
        self.assertLess(kwargs["expires"], 15 * 60)

    def test_http_lr_broker_down_type4_ephemeral(self) -> None:
        with patch(ENQUEUE, side_effect=OSError("broker down")):
            response = handle_message_component(_lr_payload())
        self.assertEqual(
            json.loads(response.content),
            {"type": 4, "data": {"flags": 64, "content": SAVE_FAILED}},
        )

    def test_http_lr_bad_id_type4_stale(self) -> None:
        with patch(ENQUEUE) as enqueue:
            response = handle_message_component(_lr_payload("lr:7:8:9"))
        body = json.loads(response.content)
        self.assertEqual(body["type"], 4)
        self.assertEqual(body["data"]["flags"], 64)
        enqueue.assert_not_called()


TASK_PAYLOAD: dict[str, Any] = {
    "application_id": "9",
    "interaction_token": "private-token",
    "click": {
        "discord_user_id": "1001",
        "discord_message_id": "9001",
        "discord_channel_id": "8001",
        "interaction_id": "4001",
        "snapshot_id": 7,
        "trait_id": 8,
        "score": 4,
    },
}
WEBHOOK = "https://discord.com/api/v10/webhooks/9/private-token"


class CompleteReviewClickTaskTests(SimpleTestCase):
    def _run(
        self, result: ClickResult | None, payload: dict[str, Any] = TASK_PAYLOAD
    ) -> tuple[MagicMock, MagicMock, MagicMock]:
        with (
            patch("discordbot.tasks.review_click", return_value=result) as click,
            patch("discordbot.tasks.requests.patch") as patch_req,
            patch("discordbot.tasks.requests.post") as post_req,
        ):
            complete_review_click.run(payload)
        return click, patch_req, post_req

    def test_complete_review_click_patches_and_followups(self) -> None:
        message = {"flags": 1 << 15, "components": [{"type": 10, "content": "x"}]}
        click, patch_req, post_req = self._run(
            ClickResult(message=message, ephemeral="Closed.")
        )
        self.assertEqual(click.call_args.args[0].model_dump(), TASK_PAYLOAD["click"])
        self.assertEqual(patch_req.call_args.args[0], f"{WEBHOOK}/messages/@original")
        self.assertEqual(
            patch_req.call_args.kwargs["json"],
            {**message, "allowed_mentions": {"parse": []}},
        )
        self.assertEqual(post_req.call_args.args[0], WEBHOOK)
        self.assertEqual(
            post_req.call_args.kwargs["json"],
            {"content": "Closed.", "flags": 64, "allowed_mentions": {"parse": []}},
        )

    def test_backend_unreachable_sends_fallback(self) -> None:
        _, patch_req, post_req = self._run(None)
        patch_req.assert_not_called()
        self.assertEqual(post_req.call_args.kwargs["json"]["content"], SAVE_FAILED)

    def test_rerender_only(self) -> None:
        _, patch_req, post_req = self._run(
            ClickResult(message={"flags": 1 << 15, "components": []})
        )
        patch_req.assert_called_once()
        post_req.assert_not_called()

    def test_bad_token_does_nothing(self) -> None:
        for token in ("", "a/b"):
            with self.subTest(token=token):
                click, patch_req, post_req = self._run(
                    ClickResult(ephemeral="x"),
                    {**TASK_PAYLOAD, "interaction_token": token},
                )
                click.assert_not_called()
                patch_req.assert_not_called()
                post_req.assert_not_called()

    def test_patch_failure_still_sends_followup(self) -> None:
        with (
            patch(
                "discordbot.tasks.review_click",
                return_value=ClickResult(
                    message={"flags": 1 << 15, "components": []}, ephemeral="x"
                ),
            ),
            patch(
                "discordbot.tasks.requests.patch",
                side_effect=requests.ConnectionError("down"),
            ),
            patch("discordbot.tasks.requests.post") as post_req,
        ):
            complete_review_click.run(TASK_PAYLOAD)
        post_req.assert_called_once()
