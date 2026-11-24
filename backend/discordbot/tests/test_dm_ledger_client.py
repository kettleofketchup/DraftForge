from typing import Any
from unittest.mock import MagicMock, call, patch

import requests
from django.test import SimpleTestCase

from discordbot.internal_client import dm_ledger as client
from discordbot.models import DMStatus
from discordbot.schemas import DMClaimBody, DMFinalizeBody

TRANSPORT_POST = "app.internal_client.transport.post"
REQUESTS_POST = "app.internal_client.transport.requests.post"
SLEEP = "discordbot.internal_client.dm_ledger.time.sleep"


def _resp(status_code: int, payload: Any = None) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.text = ""
    resp.json.return_value = payload
    return resp


def _claim_body() -> DMClaimBody:
    return DMClaimBody(
        kind="signup_reminder",
        idempotency_key="signup_reminder:k",
        claim_token="task-1:abcd1234",
        discord_user_id="1001",
        context={"discord_event_id": 5},
        has_components=True,
    )


def _tokens(mock_post: MagicMock) -> list[str]:
    return [c.args[1]["claim_token"] for c in mock_post.call_args_list]


@patch(SLEEP)
class DMLedgerClientTests(SimpleTestCase):
    def test_claim_retries_lost_response_with_same_token(
        self, sleep: MagicMock
    ) -> None:
        granted = _resp(200, {"id": 7, "status": "pending", "attempts": 1})
        with patch(TRANSPORT_POST, side_effect=[None, granted]) as post:
            result = client.claim_dm(_claim_body())
        assert result is not None
        self.assertTrue(result.granted)
        self.assertEqual(result.id, 7)
        self.assertFalse(result.created)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(_tokens(post), ["task-1:abcd1234"] * 2)
        self.assertEqual(post.call_args_list[0], post.call_args_list[1])
        sleep.assert_called_once_with(client._RETRY_DELAYS[0])

    def test_claim_retries_timeout_under_real_transport(self, sleep: MagicMock) -> None:
        created = _resp(201, {"id": 7, "status": "pending", "attempts": 1})
        with patch(
            REQUESTS_POST, side_effect=[requests.Timeout("read timed out"), created]
        ) as post:
            result = client.claim_dm(_claim_body())
        assert result is not None
        self.assertTrue(result.granted)
        self.assertTrue(result.created)
        self.assertEqual(post.call_count, 2)
        bodies = [c.kwargs["json"] for c in post.call_args_list]
        self.assertEqual([b["claim_token"] for b in bodies], ["task-1:abcd1234"] * 2)
        self.assertTrue(post.call_args_list[0].args[0].endswith("/discord/dms/claim/"))

    def test_claim_unreachable_returns_none(self, sleep: MagicMock) -> None:
        with patch(TRANSPORT_POST, side_effect=[None, None, None]) as post:
            self.assertIsNone(client.claim_dm(_claim_body()))
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(0.5), call(2.0)])

    def test_claim_5xx_exhausted_returns_none(self, sleep: MagicMock) -> None:
        with patch(TRANSPORT_POST, return_value=_resp(503)) as post:
            self.assertIsNone(client.claim_dm(_claim_body()))
        self.assertEqual(post.call_count, 3)

    def test_claim_409_not_granted(self, sleep: MagicMock) -> None:
        with patch(
            TRANSPORT_POST, return_value=_resp(409, {"id": 7, "status": "sent"})
        ) as post:
            result = client.claim_dm(_claim_body())
        assert result is not None
        self.assertFalse(result.granted)
        self.assertEqual(result.status, DMStatus.SENT)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_claim_400_returns_none_without_retry(self, sleep: MagicMock) -> None:
        with patch(
            TRANSPORT_POST, return_value=_resp(400, {"error": "invalid_request"})
        ) as post:
            self.assertIsNone(client.claim_dm(_claim_body()))
        self.assertEqual(post.call_count, 1)

    def test_mark_sending(self, sleep: MagicMock) -> None:
        with patch(TRANSPORT_POST, side_effect=[None, _resp(204)]) as post:
            self.assertTrue(client.mark_dm_sending(7, claim_token="tok"))
        self.assertEqual(_tokens(post), ["tok", "tok"])
        self.assertEqual(post.call_args.args[0], "/discord/dms/7/sending/")
        with patch(TRANSPORT_POST, return_value=_resp(409)):
            self.assertFalse(client.mark_dm_sending(7, claim_token="tok"))
        with patch(TRANSPORT_POST, return_value=None):
            self.assertIsNone(client.mark_dm_sending(7, claim_token="tok"))

    def test_finalize_retries_5xx(self, sleep: MagicMock) -> None:
        body = DMFinalizeBody(
            claim_token="tok",
            status="sent",
            discord_channel_id="111",
            discord_message_id="222",
        )
        ok = _resp(200, {"id": 7, "status": "sent"})
        with patch(TRANSPORT_POST, side_effect=[_resp(502), None, ok]) as post:
            self.assertTrue(client.finalize_dm(7, body))
        self.assertEqual(post.call_count, 3)
        self.assertEqual(_tokens(post), ["tok"] * 3)
        self.assertEqual(post.call_args.args[0], "/discord/dms/7/finalize/")
        with patch(TRANSPORT_POST, return_value=_resp(409)) as post:
            self.assertFalse(client.finalize_dm(7, body))
        self.assertEqual(post.call_count, 1)
        with patch(TRANSPORT_POST, return_value=_resp(500)):
            self.assertFalse(client.finalize_dm(7, body))

    def test_record_click_swallows_errors(self, sleep: MagicMock) -> None:
        with patch(TRANSPORT_POST, side_effect=RuntimeError("boom")):
            self.assertIsNone(client.record_dm_click("222", "1001"))
        with patch(TRANSPORT_POST, return_value=None) as post:
            self.assertIsNone(client.record_dm_click("222", "1001"))
        self.assertEqual(post.call_count, 1)
        self.assertIsNone(client.record_dm_click("not-an-id", "1001"))
        with patch(TRANSPORT_POST, return_value=_resp(204)) as post:
            client.record_dm_click("222", "1001")
        post.assert_called_once_with(
            "/discord/dms/click/",
            {"discord_message_id": "222", "discord_user_id": "1001"},
        )
        sleep.assert_not_called()
