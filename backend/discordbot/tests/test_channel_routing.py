import json
from unittest.mock import patch

import requests
from django.test import SimpleTestCase

from discordbot.channel_routing import (
    build_create_request,
    normalize_receipt,
    resolve_guild_channel,
)
from discordbot.delivery_types import (
    ChannelKind,
    DeliveryFailure,
    DeliveryReceipt,
    FailureCategory,
    FailurePhase,
    ResolvedChannel,
)
from discordbot.utils import DISCORD_API_BASE, DiscordAuthError

CHANNEL = "100000000000000001"
GUILD = "200000000000000001"
MESSAGE = "100000000000000002"
THREAD = "100000000000000003"


def _response(status: int, data: object) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(data).encode()
    return response


class ChannelRoutingTest(SimpleTestCase):
    def setUp(self) -> None:
        self.request = patch(
            "discordbot.channel_routing.utils._rate_limited_request"
        ).start()
        self.addCleanup(patch.stopall)
        patch("discordbot.channel_routing.utils._get_headers", return_value={}).start()

    def resolve(self, channel_type: object) -> ResolvedChannel | DeliveryFailure:
        self.request.return_value = _response(
            200, {"id": CHANNEL, "guild_id": GUILD, "type": channel_type}
        )
        return resolve_guild_channel(CHANNEL, GUILD)

    def test_type_0_and_5_route_to_messages(self) -> None:
        payload = {
            "embeds": [{"title": "Synthetic Event"}],
            "components": [],
            "content": "Synthetic content",
            "allowed_mentions": {"parse": []},
        }
        for channel_type, kind in (
            (0, ChannelKind.TEXT),
            (5, ChannelKind.ANNOUNCEMENT),
        ):
            with self.subTest(channel_type=channel_type):
                channel = self.resolve(channel_type)
                self.assertEqual(channel, ResolvedChannel(CHANNEL, GUILD, kind))
                url, body = build_create_request(channel, payload, "Synthetic Event")
                self.assertEqual(url, f"{DISCORD_API_BASE}/channels/{CHANNEL}/messages")
                self.assertEqual(body, payload)

    def test_type_15_routes_to_threads_with_truncated_title(self) -> None:
        channel = self.resolve(15)
        payload = {"components": [], "allowed_mentions": {"parse": []}}
        url, body = build_create_request(channel, payload, "x" * 150)
        self.assertEqual(url, f"{DISCORD_API_BASE}/channels/{CHANNEL}/threads")
        self.assertEqual(body, {"name": "x" * 100, "message": payload})

    def test_forum_requires_nonblank_title(self) -> None:
        channel = ResolvedChannel(CHANNEL, GUILD, ChannelKind.FORUM)
        for title in (None, "", "   "):
            with self.subTest(title=title), self.assertRaises(ValueError):
                build_create_request(channel, {}, title)

    def test_unknown_type_is_unsupported(self) -> None:
        for channel_type in (2, 4, None, True, False, "0", 0.0, [], {}):
            with self.subTest(channel_type=channel_type):
                failure = self.resolve(channel_type)
                self.assertEqual(failure.category, FailureCategory.UNSUPPORTED_CHANNEL)
        self.request.return_value = _response(200, {"id": CHANNEL, "guild_id": GUILD})
        self.assertEqual(
            resolve_guild_channel(CHANNEL, GUILD).category,
            FailureCategory.UNSUPPORTED_CHANNEL,
        )

    def test_guild_mismatch_rejected(self) -> None:
        self.request.return_value = _response(
            200, {"id": CHANNEL, "guild_id": MESSAGE, "type": 0}
        )
        self.assertEqual(
            resolve_guild_channel(CHANNEL, GUILD).category,
            FailureCategory.CHANNEL_MISMATCH,
        )

    def test_id_mismatch_rejected(self) -> None:
        self.request.return_value = _response(
            200, {"id": MESSAGE, "guild_id": GUILD, "type": 0}
        )
        self.assertEqual(
            resolve_guild_channel(CHANNEL, GUILD).category,
            FailureCategory.CHANNEL_MISMATCH,
        )

    def test_blank_expected_guild_makes_no_request(self) -> None:
        self.assertEqual(
            resolve_guild_channel(CHANNEL, "").category,
            FailureCategory.CHANNEL_MISMATCH,
        )
        self.request.assert_not_called()

    def test_invalid_identifiers_make_no_request(self) -> None:
        for invalid in ("", " ", "../messages", "0", "-1", "１２３"):
            with self.subTest(invalid=invalid):
                self.assertEqual(
                    resolve_guild_channel(invalid, GUILD).category,
                    FailureCategory.CHANNEL_MISMATCH,
                )
                self.assertEqual(
                    resolve_guild_channel(CHANNEL, invalid).category,
                    FailureCategory.CHANNEL_MISMATCH,
                )
        self.request.assert_not_called()

    def test_lookup_403_reports_channel_lookup_phase(self) -> None:
        self.request.return_value = _response(
            403, {"code": 50013, "message": "Synthetic rejection"}
        )
        self.assertEqual(
            resolve_guild_channel(CHANNEL, GUILD),
            DeliveryFailure(
                FailurePhase.CHANNEL_LOOKUP, FailureCategory.HTTP_ERROR, 403, 50013
            ),
        )

    def test_lookup_timeout_is_transport(self) -> None:
        self.request.side_effect = requests.Timeout()
        self.assertEqual(
            resolve_guild_channel(CHANNEL, GUILD),
            DeliveryFailure(FailurePhase.CHANNEL_LOOKUP, FailureCategory.TRANSPORT),
        )

    def test_lookup_auth_error_preserves_response(self) -> None:
        self.request.side_effect = DiscordAuthError(response=_response(401, {}))
        self.assertEqual(
            resolve_guild_channel(CHANNEL, GUILD),
            DeliveryFailure(FailurePhase.CHANNEL_LOOKUP, FailureCategory.AUTH, 401),
        )

    def test_malformed_lookup_is_rejected(self) -> None:
        for data in ([], None, "invalid"):
            with self.subTest(data=data):
                self.request.return_value = _response(200, data)
                self.assertEqual(
                    resolve_guild_channel(CHANNEL, GUILD).category,
                    FailureCategory.MALFORMED_RESPONSE,
                )
        response = _response(200, {})
        response._content = b"<html>"
        self.request.return_value = response
        self.assertEqual(
            resolve_guild_channel(CHANNEL, GUILD),
            DeliveryFailure(
                FailurePhase.CHANNEL_LOOKUP, FailureCategory.MALFORMED_RESPONSE, 200
            ),
        )

    def test_forum_receipt_without_message_is_uncertain(self) -> None:
        self.assertIsNone(
            normalize_receipt(
                ResolvedChannel(CHANNEL, GUILD, ChannelKind.FORUM), {"id": THREAD}
            )
        )

    def test_text_receipt_has_no_thread_id(self) -> None:
        for kind in (ChannelKind.TEXT, ChannelKind.ANNOUNCEMENT):
            receipt = normalize_receipt(
                ResolvedChannel(CHANNEL, GUILD, kind), {"id": MESSAGE}
            )
            self.assertEqual(receipt, DeliveryReceipt(CHANNEL, MESSAGE, None, kind))
            self.assertEqual(receipt.storage_channel_type(), "text")

    def test_forum_receipt_ids(self) -> None:
        receipt = normalize_receipt(
            ResolvedChannel(CHANNEL, GUILD, ChannelKind.FORUM),
            {"id": THREAD, "message": {"id": MESSAGE}},
        )
        self.assertEqual(
            receipt, DeliveryReceipt(CHANNEL, MESSAGE, THREAD, ChannelKind.FORUM)
        )
        self.assertEqual(receipt.storage_channel_type(), "forum")

    def test_invalid_receipts_are_not_delivery_proof(self) -> None:
        for kind in ChannelKind:
            channel = ResolvedChannel(CHANNEL, GUILD, kind)
            for data in (
                None,
                [],
                {},
                {"id": True},
                {"id": 123},
                {"id": ""},
                {"id": "invalid"},
            ):
                with self.subTest(kind=kind, data=data):
                    self.assertIsNone(normalize_receipt(channel, data))
        forum = ResolvedChannel(CHANNEL, GUILD, ChannelKind.FORUM)
        for message in (None, [], {}, {"id": ""}, {"id": True}):
            with self.subTest(message=message):
                self.assertIsNone(
                    normalize_receipt(forum, {"id": THREAD, "message": message})
                )

    def test_receipt_json_roundtrip(self) -> None:
        for kind in ChannelKind:
            receipt = DeliveryReceipt(
                CHANNEL, MESSAGE, THREAD if kind == ChannelKind.FORUM else None, kind
            )
            self.assertEqual(DeliveryReceipt.from_json(receipt.to_json()), receipt)
            self.assertEqual(receipt.to_json()["kind"], kind.value)

    def test_receipt_json_rejects_invalid_ids_and_inconsistent_thread(self) -> None:
        valid = DeliveryReceipt(CHANNEL, MESSAGE, None, ChannelKind.TEXT).to_json()
        for update in (
            {"parent_channel_id": ""},
            {"message_id": True},
            {"message_id": None},
            {"kind": "unknown"},
            {"thread_id": THREAD},
            {"kind": "forum"},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                DeliveryReceipt.from_json(valid | update)
        with self.assertRaises(ValueError):
            DeliveryReceipt.from_json({})
