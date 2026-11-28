"""Exercise the internal queue protocol and actual Discord request shape."""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import redis
import requests
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from app.redis_client import get_redis_client
from app.redis_keys import namespaced_key
from discordbot.internal_client.live_messages import claim_edit, finish_edit
from discordbot.live_messages import CLAIM_SCAN_LIMIT, track_message
from discordbot.live_renderers import render_live_message
from discordbot.live_worker import (
    BATCH_SIZE,
    apply_edit,
    cooldown_remaining,
    pause_live_edits,
)
from discordbot.payloads import live_component_digest
from discordbot.schemas import LiveEditClaim, LiveEditFinish
from discordbot.tasks import refresh_live_messages
from discordbot.tests.ledger_bridge import ledger_bridge
from events.tests.base import EventTestCase

TOKEN = str(uuid4())
COMPONENTS = [{"type": 10, "content": "Signed up: 12"}]
CLAIM = {
    "id": 1,
    "token": TOKEN,
    "channel_id": "102",
    "message_id": "100",
    "payload": {"flags": 32768, "components": COMPONENTS},
}
TRANSPORT = "app.internal_client.transport.post"
HTTP = "discordbot.utils.requests.request"
ACQUIRE = "discordbot.utils._acquire_rate_limit_token"


def response(status: int, body: object = None) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    return result


@override_settings(TEST=False, DISCORD_BOT_TOKEN="test-bot-token")
class LiveWorkerTests(SimpleTestCase):
    def setUp(self) -> None:
        client = self.enterContext(patch("discordbot.live_worker.get_redis_client"))
        client.return_value.pttl.return_value = -2

    @patch(ACQUIRE)
    @patch(HTTP)
    @patch(TRANSPORT)
    def test_edits_only_the_existing_message_then_acknowledges(
        self, queue: MagicMock, http: MagicMock, rate_limit: MagicMock
    ) -> None:
        queue.side_effect = [response(200, CLAIM), response(204), response(204)]
        http.return_value = response(200, {"id": "100", "channel_id": "102"})

        self.assertEqual(refresh_live_messages(), 1)
        rate_limit.assert_called_once()
        http.assert_called_once_with(
            "PATCH",
            "https://discord.com/api/v10/channels/102/messages/100",
            headers={
                "Authorization": "Bot test-bot-token",
                "Content-Type": "application/json",
            },
            timeout=10,
            json={"components": COMPONENTS, "allowed_mentions": {"parse": []}},
        )
        self.assertEqual(
            queue.call_args_list[1].args,
            (
                "/discord/live-messages/1/finish/",
                {
                    "token": TOKEN,
                    "outcome": "edited",
                    "error_code": None,
                    "retry_after": None,
                },
            ),
        )

    @patch(ACQUIRE)
    @patch(HTTP, return_value=response(200, {"id": "100", "channel_id": "102"}))
    @patch(TRANSPORT)
    def test_backlog_is_drained_in_bounded_batches(
        self, queue: MagicMock, http: MagicMock, rate_limit: MagicMock
    ) -> None:
        queue.side_effect = [response(200, CLAIM), response(204)] * BATCH_SIZE
        self.assertEqual(refresh_live_messages(), BATCH_SIZE)
        self.assertEqual(http.call_count, BATCH_SIZE)

    @override_settings(TEST=True, TEST_DISCORD_USER_ID="1001")
    @patch(HTTP)
    @patch(TRANSPORT)
    def test_scan_continuations_share_the_worker_batch_budget(
        self, queue: MagicMock, http: MagicMock
    ) -> None:
        queue.return_value = response(204)
        queue.return_value.headers["X-Live-Edit-Scan"] = "limit-reached"
        self.assertEqual(refresh_live_messages(), 0)
        self.assertEqual(queue.call_count, BATCH_SIZE)
        for attempt in queue.call_args_list:
            self.assertEqual(
                attempt.args,
                ("/discord/live-messages/claim/", {"discord_user_id": "1001"}),
            )
        http.assert_not_called()

    @patch(ACQUIRE)
    @patch(HTTP)
    def test_outcome_depends_on_discord_evidence(
        self, http: MagicMock, rate_limit: MagicMock
    ) -> None:
        claim = LiveEditClaim.model_validate(CLAIM)
        cases = [
            (404, {"code": 10008}, "missing", 10008),
            (404, {"code": 10003}, "missing", 10003),
            (403, {"code": 50013}, "blocked", 50013),
            (403, {"code": 50005}, "blocked", 50005),
            (400, {"code": 50035}, "blocked", 50035),
            (404, {}, "retry", None),
            (502, None, "retry", None),
            (200, [], "retry", None),
            (200, {"id": "101", "channel_id": "102"}, "retry", None),
            (200, {"id": "100", "channel_id": "103"}, "retry", None),
        ]
        for status, body, expected, code in cases:
            with self.subTest(status=status, body=body):
                http.return_value = response(status, body)
                result = apply_edit(claim)
                self.assertEqual((result.outcome, result.error_code), (expected, code))
        http.side_effect = requests.Timeout()
        self.assertEqual(apply_edit(claim).outcome, "retry")

    @patch(ACQUIRE)
    @patch(HTTP)
    @patch(TRANSPORT)
    def test_rate_limit_waits_for_later_beat_without_sleeping(
        self, queue: MagicMock, http: MagicMock, rate_limit: MagicMock
    ) -> None:
        for body, header, wait in [
            ({"retry_after": 5.75}, None, 5.75),
            ({}, "20.5", 20.5),
        ]:
            with self.subTest(body=body, header=header):
                http.reset_mock()
                queue.side_effect = [response(200, CLAIM), response(204)]
                http.return_value = response(429, body)
                if header:
                    http.return_value.headers["Retry-After"] = header
                self.assertEqual(refresh_live_messages(), 1)
                self.assertEqual(queue.call_args.args[1]["outcome"], "retry")
                self.assertEqual(queue.call_args.args[1]["retry_after"], wait)
                self.assertEqual(http.call_count, 1)

    @patch(ACQUIRE)
    @patch(HTTP, return_value=response(401))
    @patch(TRANSPORT)
    def test_auth_rejected_halts_batch_and_retains_dirty_message(
        self, queue: MagicMock, http: MagicMock, rate_limit: MagicMock
    ) -> None:
        queue.side_effect = [response(200, CLAIM), response(204)]
        refresh_live_messages()
        self.assertEqual(http.call_count, 1)
        self.assertEqual(queue.call_args.args[1]["outcome"], "retry")
        self.assertGreater(queue.call_args.args[1]["retry_after"], 0)

    @patch(ACQUIRE)
    @patch(HTTP, return_value=response(200, {"id": "100", "channel_id": "102"}))
    @patch(TRANSPORT)
    def test_lost_ack_yields_without_second_discord_request(
        self, queue: MagicMock, http: MagicMock, rate_limit: MagicMock
    ) -> None:
        queue.side_effect = [response(200, CLAIM), None]
        self.assertEqual(refresh_live_messages(), 0)
        self.assertEqual(http.call_count, 1)

    @patch(HTTP)
    @patch(TRANSPORT)
    def test_malformed_claim_never_reaches_discord(
        self, queue: MagicMock, http: MagicMock
    ) -> None:
        queue.return_value = response(200, {**CLAIM, "message_id": "../elsewhere"})
        self.assertEqual(refresh_live_messages(), 0)
        http.assert_not_called()

    @override_settings(TEST=True, TEST_DISCORD_USER_ID="1001")
    @patch(TRANSPORT, return_value=response(204))
    def test_worker_can_only_claim_its_test_recipient(self, queue: MagicMock) -> None:
        self.assertEqual(refresh_live_messages(), 0)
        queue.assert_called_once_with(
            "/discord/live-messages/claim/", {"discord_user_id": "1001"}
        )

    @override_settings(TEST=True, TEST_DISCORD_USER_ID="")
    @patch(TRANSPORT)
    def test_worker_missing_test_recipient_never_claims(self, queue: MagicMock) -> None:
        self.assertEqual(refresh_live_messages(), 0)
        queue.assert_not_called()

    @override_settings(DISCORD_BOT_TOKEN="")
    @patch(TRANSPORT)
    def test_tokenless_worker_leaves_all_work_unclaimed(self, queue: MagicMock) -> None:
        self.assertEqual(refresh_live_messages(), 0)
        queue.assert_not_called()


@override_settings(TEST=False, DISCORD_BOT_TOKEN="test-bot-token")
class LiveQueueScanTests(EventTestCase):
    def test_edit_behind_a_full_page_of_unchanged_dms_runs_in_the_same_batch(
        self,
    ) -> None:
        renderer = "event_signup_reminder"
        current = render_live_message(renderer, self.event.pk)
        assert current is not None
        digest = live_component_digest(current["components"])
        for index in range(CLAIM_SCAN_LIMIT):
            track_message(
                renderer=renderer,
                subject_id=self.event.pk,
                channel_id="102",
                message_id=str(1000 + index),
                initial_digest=digest,
            )
        other_event = self.make_event()
        previous = render_live_message(renderer, other_event.pk)
        assert previous is not None
        changed = track_message(
            renderer=renderer,
            subject_id=other_event.pk,
            channel_id="102",
            message_id="2000",
            initial_digest=live_component_digest(previous["components"]),
        )
        other_event.name = "Moved to Saturday"
        other_event.save(update_fields=["name"])
        with (
            ledger_bridge(),
            patch("discordbot.live_worker.cooldown_remaining", return_value=0),
            patch(ACQUIRE),
            patch(
                HTTP, return_value=response(200, {"id": "2000", "channel_id": "102"})
            ) as http,
        ):
            self.assertEqual(refresh_live_messages(), 1)
        http.assert_called_once()
        self.assertEqual(
            http.call_args.args,
            ("PATCH", "https://discord.com/api/v10/channels/102/messages/2000"),
        )
        changed.refresh_from_db()
        sent = http.call_args.kwargs["json"]["components"]
        self.assertIn("Moved to Saturday", str(sent))
        self.assertEqual(changed.applied_hash, live_component_digest(sent))
        self.assertIsNone(changed.next_attempt_at)


@override_settings(TEST=False, DISCORD_BOT_TOKEN="test-bot-token")
class LiveWorkerCooldownTests(SimpleTestCase):
    def setUp(self) -> None:
        # Run against CI's Redis. Keep the worker key isolated from parallel tests.
        self.enterContext(
            override_settings(REDIS_KEY_NAMESPACE=f"test-live-{uuid4()}:")
        )
        client = get_redis_client()
        try:
            client.ping()
        except redis.RedisError:
            self.skipTest("Redis unavailable for shared cooldown integration")
        self.addCleanup(client.delete, namespaced_key("discord:live_edits:pause"))

    @patch(ACQUIRE)
    @patch(HTTP)
    @patch(TRANSPORT)
    def test_global_rate_limit_survives_batch_and_suppresses_other_claims_and_edits(
        self, queue: MagicMock, http: MagicMock, rate_limit: MagicMock
    ) -> None:
        queue.side_effect = [response(200, CLAIM), response(204)]
        http.return_value = response(429, {"global": True, "retry_after": 180.5})
        self.assertEqual(refresh_live_messages(), 1)
        self.assertGreater(cooldown_remaining(), 179)

        pause_live_edits(1)  # A shorter concurrent pause must not release the block.
        self.assertGreater(cooldown_remaining(), 179)
        self.assertEqual(refresh_live_messages(), 0)
        # A worker which leased just before the global response must also defer.
        result = apply_edit(LiveEditClaim.model_validate(CLAIM))
        self.assertEqual(result.outcome, "retry")
        self.assertGreater(result.retry_after, 179)
        self.assertEqual(http.call_count, 1)
        self.assertEqual(queue.call_count, 2)
        with override_settings(REDIS_KEY_NAMESPACE=f"test-other-{uuid4()}:"):
            self.assertEqual(cooldown_remaining(), 0)


@override_settings(INTERNAL_SERVICE_TOKEN="test-token")
class LiveEditApiTests(SimpleTestCase):
    def setUp(self) -> None:
        self.api = APIClient()
        self.api.credentials(HTTP_X_INTERNAL_TOKEN="test-token")

    @patch("discordbot.internal_live_views.live_messages.claim_live_edit")
    @patch("discordbot.internal_live_views.live_messages.finish_live_edit")
    def test_routes_require_internal_auth(
        self, finish: MagicMock, claim: MagicMock
    ) -> None:
        for name, args in (
            ("internal_live_edit_claim", []),
            ("internal_live_edit_finish", [1]),
        ):
            url = reverse(name, args=args)
            for token in ("", "wrong"):
                self.assertIn(
                    APIClient()
                    .post(url, {}, format="json", HTTP_X_INTERNAL_TOKEN=token)
                    .status_code,
                    (401, 403),
                )
        finish.assert_not_called()
        claim.assert_not_called()

    @patch("discordbot.internal_live_views.live_messages.claim_live_edit")
    @patch("discordbot.internal_live_views.live_messages.finish_live_edit")
    def test_queue_client_and_auth_views_agree_on_claim_finish_and_empty(
        self, finish: MagicMock, claim: MagicMock
    ) -> None:
        def post(path: str, body: dict) -> requests.Response:
            return self.api.post(f"/api/internal{path}", body, format="json")

        claim.side_effect = [CLAIM, None]
        finish.side_effect = [True, False]
        with patch(TRANSPORT, side_effect=post):
            work = claim_edit()
            assert isinstance(work, LiveEditClaim)
            self.assertEqual((work.channel_id, work.message_id), ("102", "100"))
            result = LiveEditFinish(token=work.token, outcome="edited")
            self.assertTrue(finish_edit(work.id, result))
            self.assertFalse(finish_edit(work.id, result))
            self.assertIsNone(claim_edit())
        finish.assert_called_with(1, TOKEN, "edited", error_code=None, retry_after=None)

    @patch("discordbot.internal_live_views.live_messages.claim_live_edit")
    def test_requested_recipient_is_validated_and_forwarded(
        self, claim: MagicMock
    ) -> None:
        claim.return_value = None
        url = reverse("internal_live_edit_claim")
        self.assertEqual(
            self.api.post(url, {"discord_user_id": ""}, format="json").status_code, 400
        )
        claim.assert_not_called()
        self.assertEqual(
            self.api.post(url, {"discord_user_id": "1001"}, format="json").status_code,
            204,
        )
        claim.assert_called_once_with(discord_user_id="1001")

    @patch("discordbot.internal_live_views.live_messages.finish_live_edit")
    def test_invalid_finish_rejected_before_service(self, finish: MagicMock) -> None:
        for body in (
            {"outcome": "edited"},
            {"token": TOKEN, "outcome": "sent"},
            {"token": TOKEN, "outcome": "retry", "retry_after": -1},
        ):
            result = self.api.post(
                reverse("internal_live_edit_finish", args=[1]), body, format="json"
            )
            self.assertEqual(result.status_code, 400)
        finish.assert_not_called()
