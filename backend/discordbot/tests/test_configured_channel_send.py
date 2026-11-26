import json
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, TestCase, override_settings
from structlog.testing import capture_logs

from app import internal_client
from discordbot import utils
from discordbot.delivery_types import (
    ClaimResult,
    FailureCategory,
    SendOutcome,
    SendResult,
)
from discordbot.models import DiscordMessageLog
from events.tests._internal_client_orm import DiscordTestMixin

CHANNEL = "100000000000000001"
GUILD = "200000000000000001"
MESSAGE = "100000000000000002"
THREAD = "100000000000000003"


def response(
    status: int, data: object = None, *, body: bytes | None = None
) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = body if body is not None else json.dumps(data).encode()
    return result


class ConfiguredTransportAmbiguityTest(SimpleTestCase):
    def test_transport_exception_with_response_keeps_pending_lease(self) -> None:
        for error in (
            requests.Timeout(response=response(201, {"id": MESSAGE})),
            requests.ConnectionError(response=response(500, {})),
            utils.DiscordRateLimitTimeout(response=response(429, {})),
        ):
            with (
                self.subTest(error=type(error)),
                patch(
                    "discordbot.utils.requests.request",
                    side_effect=[
                        response(200, {"id": CHANNEL, "guild_id": GUILD, "type": 0}),
                        error,
                    ],
                ),
                patch("discordbot.utils._acquire_rate_limit_token"),
                patch(
                    "app.internal_client.claim_discord_message_log_result",
                    return_value=ClaimResult("claimed", 7),
                ),
                patch("app.internal_client.finalize_discord_message_log") as finalize,
            ):
                result = utils.send_to_configured_channel(
                    CHANNEL,
                    GUILD,
                    {},
                    title="Synthetic Event",
                    source="synthetic",
                    source_id=1,
                )
                self.assertEqual(result.outcome, SendOutcome.UNCERTAIN)
                self.assertFalse(result.fallback_safe)
                self.assertFalse(result.finalized)
                self.assertEqual(result.failure.status, error.response.status_code)
                finalize.assert_not_called()


class ConfiguredChannelSendTest(DiscordTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.channel_type: int = 0
        self.lookup: requests.Response | Exception | None = None
        self.created: requests.Response | Exception = response(201, {"id": MESSAGE})
        self.http: MagicMock = self.enterContext(
            patch("discordbot.utils.requests.request", side_effect=self.request)
        )
        self.enterContext(patch("discordbot.utils._acquire_rate_limit_token"))
        self.sleep: MagicMock = self.enterContext(patch("discordbot.utils._time.sleep"))

    def request(self, method: str, url: str, **kwargs: object) -> requests.Response:
        if method == "GET" and url == f"{utils.DISCORD_API_BASE}/channels/{CHANNEL}":
            result = (
                self.lookup
                if self.lookup is not None
                else response(
                    200, {"id": CHANNEL, "guild_id": GUILD, "type": self.channel_type}
                )
            )
        elif method == "POST" and url in (
            f"{utils.DISCORD_API_BASE}/channels/{CHANNEL}/messages",
            f"{utils.DISCORD_API_BASE}/channels/{CHANNEL}/threads",
        ):
            result = self.created
        else:
            raise AssertionError(f"Unexpected mocked request: {method} {url}")
        if isinstance(result, Exception):
            raise result
        return result

    def send(self, **kwargs: object) -> SendResult:
        return utils.send_to_configured_channel(
            CHANNEL,
            GUILD,
            {"title": "Synthetic Event"},
            title="Synthetic Event",
            source="synthetic",
            source_id=1,
            **kwargs,
        )

    def posts(self) -> list:
        return [call for call in self.http.call_args_list if call.args[0] == "POST"]

    def test_text_channel_with_title_posts_to_messages(self) -> None:
        result = self.send(
            components=[{"type": 1}],
            content="Synthetic",
            allowed_mentions={"parse": []},
        )
        self.assertEqual(result.outcome, SendOutcome.DELIVERED)
        self.assertIsNone(result.receipt.thread_id)
        self.assertTrue(result.finalized)
        self.assertFalse(result.fallback_safe)
        self.assertEqual(
            self.posts()[0].args[1],
            f"{utils.DISCORD_API_BASE}/channels/{CHANNEL}/messages",
        )
        self.assertEqual(
            self.posts()[0].kwargs["json"],
            {
                "embeds": [{"title": "Synthetic Event"}],
                "components": [{"type": 1}],
                "content": "Synthetic",
                "allowed_mentions": {"parse": []},
            },
        )
        row = DiscordMessageLog.objects.get(pk=result.message_log_id)
        self.assertTrue(row.success)
        self.assertEqual(row.discord_message_id, MESSAGE)
        self.assertEqual(result.to_legacy(), {"id": MESSAGE, "_message_log_id": row.pk})

    def test_announcement_channel_posts_to_messages(self) -> None:
        self.channel_type = 5
        result = self.send()
        self.assertEqual(result.outcome, SendOutcome.DELIVERED)
        self.assertTrue(self.posts()[0].args[1].endswith("/messages"))

    def test_forum_channel_posts_thread(self) -> None:
        self.channel_type = 15
        self.created = response(201, {"id": THREAD, "message": {"id": MESSAGE}})
        result = self.send()
        self.assertEqual(result.receipt.thread_id, THREAD)
        self.assertEqual(result.receipt.message_id, MESSAGE)
        self.assertTrue(self.posts()[0].args[1].endswith("/threads"))
        self.assertEqual(self.posts()[0].kwargs["json"]["name"], "Synthetic Event")

    def test_lookup_failure_makes_no_post_and_no_lease(self) -> None:
        for lookup in (
            response(403, {"code": 50013}),
            requests.Timeout(),
            response(200, {"id": CHANNEL, "guild_id": GUILD, "type": 2}),
        ):
            with self.subTest(lookup=type(lookup)):
                self.lookup = lookup
                result = self.send()
                self.assertEqual(result.outcome, SendOutcome.FAILED)
                self.assertFalse(result.finalized)
                self.assertTrue(result.fallback_safe)
                self.assertEqual(result.failure.phase, "channel_lookup")
                self.assertEqual(self.posts(), [])
                self.assertFalse(DiscordMessageLog.objects.exists())

    def test_rejected_create_unconfirmed_failure_finalization_forbids_fallback(
        self,
    ) -> None:
        self.created = response(403, {"code": 50013})
        for finalized in (None, response(410), response(200, {})):
            with self.subTest(
                status=None if finalized is None else finalized.status_code
            ):
                DiscordMessageLog.objects.all().delete()
                with patch(
                    "app.internal_client.finalize_discord_message_log",
                    return_value=finalized,
                ):
                    result = self.send()
                self.assertEqual(result.outcome, SendOutcome.FAILED)
                confirmed = finalized is not None and finalized.ok
                self.assertEqual(result.finalized, confirmed)
                self.assertEqual(result.fallback_safe, confirmed)

    def test_signup_single_shot_429_preserves_known_rejection(self) -> None:
        for body in (
            b"<html>private</html>",
            b"[]",
            b'"private"',
            b"null",
            b'{"code": 50013, "retry_after": 600, "message": "private"}',
        ):
            with self.subTest(body=body):
                self.created = response(429, body=body)
                self.http.reset_mock()
                result = self.send(create_max_retries=1)
                self.assertEqual(result.outcome, SendOutcome.FAILED)
                self.assertEqual(result.failure.category, FailureCategory.RATE_LIMITED)
                self.assertEqual(result.failure.status, 429)
                self.assertTrue(result.fallback_safe)
                self.assertEqual(len(self.posts()), 1)
                self.sleep.assert_not_called()
                row = DiscordMessageLog.objects.get(pk=result.message_log_id)
                self.assertEqual(row.response_data, result.failure.safe_json())
                self.assertNotIn("private", str(row.response_data))

    def test_held_lease_is_in_flight_without_post(self) -> None:
        internal_client.claim_discord_message_log(
            source="synthetic", source_id=1, channel_id=CHANNEL, embed_data={}
        )
        result = self.send()
        self.assertEqual(result.outcome, SendOutcome.IN_FLIGHT)
        self.assertFalse(result.fallback_safe)
        self.assertEqual(self.posts(), [])

    def test_claim_unavailable_is_unavailable_without_post(self) -> None:
        with patch(
            "app.internal_client.claim_discord_message_log_result",
            return_value=ClaimResult("unavailable"),
        ):
            result = self.send()
        self.assertEqual(result.outcome, SendOutcome.UNAVAILABLE)
        self.assertFalse(result.fallback_safe)
        self.assertEqual(self.posts(), [])

    def test_403_is_failed_with_safe_evidence(self) -> None:
        self.created = response(403, {"code": 50013, "message": "private"})
        with capture_logs() as logs:
            result = self.send()
        self.assertEqual(result.outcome, SendOutcome.FAILED)
        self.assertEqual(result.failure.status, 403)
        self.assertEqual(result.failure.code, 50013)
        self.assertTrue(result.finalized)
        row = DiscordMessageLog.objects.get(pk=result.message_log_id)
        self.assertFalse(row.success)
        self.assertEqual(row.response_data, result.failure.safe_json())
        self.assertNotIn("private", str(logs))
        self.assertNotIn("private", str(row.response_data))

    def test_post_timeout_is_uncertain(self) -> None:
        for error in (
            requests.Timeout(),
            requests.ConnectionError(),
            utils.DiscordRateLimitTimeout(),
        ):
            with self.subTest(error=type(error)):
                DiscordMessageLog.objects.all().delete()
                self.created = error
                result = self.send()
                self.assertEqual(result.outcome, SendOutcome.UNCERTAIN)
                self.assertFalse(result.fallback_safe)
                self.assertIsNone(
                    DiscordMessageLog.objects.get(pk=result.message_log_id).success
                )

    def test_malformed_2xx_is_uncertain(self) -> None:
        for created in (
            response(201, {}),
            response(201, body=b"<html>private</html>"),
            response(200, []),
        ):
            with self.subTest(body=created.content):
                DiscordMessageLog.objects.all().delete()
                self.created = created
                result = self.send()
                self.assertEqual(result.outcome, SendOutcome.UNCERTAIN)
                self.assertFalse(result.fallback_safe)
                self.assertEqual(result.failure.status, created.status_code)
                self.assertIsNone(
                    DiscordMessageLog.objects.get(pk=result.message_log_id).success
                )

    def test_finalize_410_after_delivery_is_delivered_unfinalized(self) -> None:
        with patch(
            "app.internal_client.finalize_discord_message_log",
            return_value=response(410),
        ):
            result = self.send()
        self.assertEqual(result.outcome, SendOutcome.DELIVERED)
        self.assertFalse(result.finalized)
        self.assertEqual(result.receipt.message_id, MESSAGE)

    def test_deferred_success_leaves_lease_pending(self) -> None:
        result = self.send(defer_success_finalization=True)
        self.assertEqual(result.outcome, SendOutcome.DELIVERED)
        self.assertFalse(result.finalized)
        self.assertIsNone(
            DiscordMessageLog.objects.get(pk=result.message_log_id).success
        )

    def test_legacy_wrapper_maps_non_delivered_to_none(self) -> None:
        for outcome in SendOutcome:
            if outcome != SendOutcome.DELIVERED:
                self.assertIsNone(SendResult(outcome).to_legacy())
        self.created = response(403, {})
        self.assertIsNone(
            utils.sync_send_configured_channel(
                CHANNEL, GUILD, {}, title="Synthetic Event"
            )
        )

    def test_anonymous_create_rejection_has_no_confirmed_lease(self) -> None:
        self.created = response(403, {"code": 50013})
        result = utils.send_to_configured_channel(
            CHANNEL, GUILD, {}, title="Synthetic Event"
        )
        self.assertEqual(result.outcome, SendOutcome.FAILED)
        self.assertFalse(result.finalized)
        self.assertFalse(result.fallback_safe)

    def test_before_post_false_makes_no_post(self) -> None:
        seen: list[int] = []

        def before_post(log_id: int) -> bool:
            self.assertIsNone(DiscordMessageLog.objects.get(pk=log_id).success)
            seen.append(log_id)
            return False

        result = self.send(before_post=before_post)
        self.assertEqual(result.outcome, SendOutcome.UNAVAILABLE)
        self.assertEqual(seen, [result.message_log_id])
        self.assertFalse(
            DiscordMessageLog.objects.get(pk=result.message_log_id).success
        )
        self.assertEqual(self.posts(), [])
        self.assertFalse(result.fallback_safe)

    def test_v2_with_expected_guild_uses_resolver_for_text_channel(self) -> None:
        payload = {
            "flags": 32768,
            "components": [{"type": 17}],
            "allowed_mentions": {"parse": []},
        }
        result = utils.sync_send_v2_message(
            CHANNEL,
            payload,
            forum_thread_name="Synthetic Event",
            expected_guild_id=GUILD,
        )
        self.assertEqual(result["id"], MESSAGE)
        self.assertEqual(self.posts()[0].kwargs["json"], payload)
        self.assertTrue(self.posts()[0].args[1].endswith("/messages"))

    @override_settings(TEST_DISCORD_USER_ID="100000000000000004")
    def test_dm_and_reply_sends_unchanged(self) -> None:
        self.http.side_effect = [
            response(200, {"id": CHANNEL}),
            response(201, {"id": MESSAGE}),
        ]
        self.assertEqual(
            utils.sync_send_dm(
                "100000000000000004", embed={"title": "Synthetic Event"}
            )["id"],
            MESSAGE,
        )
        self.assertFalse(
            any(call.args[0] == "GET" for call in self.http.call_args_list)
        )
        self.http.reset_mock()
        self.http.side_effect = [response(201, {"id": MESSAGE})]
        utils.sync_send_embed_with_components(
            CHANNEL, {}, message_reference={"message_id": MESSAGE}
        )
        self.assertEqual(len(self.http.call_args_list), 1)
        self.assertEqual(
            self.http.call_args.kwargs["json"]["message_reference"],
            {"message_id": MESSAGE},
        )
