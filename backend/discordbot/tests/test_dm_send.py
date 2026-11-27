import json
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings

from discordbot import dm
from discordbot.dm import V2_FLAG, DMRequest, _parse_discord_error, send_dm
from discordbot.dm_ledger import ClaimResult
from discordbot.models import DMKind, DMStatus, DMSubject
from discordbot.schemas import DMClaimBody, DMFinalizeBody
from discordbot.utils import DiscordAuthError, DiscordRateLimitTimeout

CHANNEL_URL_SUFFIX = "/users/@me/channels"
LEDGER_ID = 41
CHANNEL_ID = "900"
MESSAGE_ID = "901"


def _response(
    status: int, body: Any = None, *, raw: str | None = None
) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp.url = "https://discord.com/api/v10/x"
    if raw is not None:
        resp._content = raw.encode()
        resp.headers["Content-Type"] = "text/html"
    else:
        resp._content = json.dumps(body if body is not None else {}).encode()
        resp.headers["Content-Type"] = "application/json"
    return resp


def _http_error(
    status: int, body: Any = None, *, raw: str | None = None
) -> requests.HTTPError:
    resp = _response(status, body, raw=raw)
    return requests.HTTPError(f"{status} error", response=resp)


def _discord(
    *,
    channel: Callable[[], requests.Response] | None = None,
    post: Callable[[], requests.Response] | None = None,
) -> Callable[..., requests.Response]:
    def fake(method: str, url: str, **kwargs: object) -> requests.Response:
        if url.endswith(CHANNEL_URL_SUFFIX):
            return channel() if channel else _response(200, {"id": CHANNEL_ID})
        return post() if post else _response(200, {"id": MESSAGE_ID})

    return fake


def _raises(exc: BaseException) -> Callable[[], requests.Response]:
    def fn() -> requests.Response:
        raise exc

    return fn


def _granted(dm_id: int = LEDGER_ID, *, granted: bool = True) -> ClaimResult:
    return ClaimResult(
        id=dm_id,
        granted=granted,
        status=DMStatus.PENDING,
        attempts=1,
        created=True,
    )


def _req(**overrides: Any) -> DMRequest:
    base: dict[str, Any] = dict(
        kind=DMKind.TEST_NOTIFICATION,
        idempotency_key="test_notification:1:abc",
        discord_user_id="222",
        subject=(DMSubject.EVENT, 5),
        content="hello",
    )
    base.update(overrides)
    return DMRequest(**base)


@override_settings(TEST=False)
@patch("discordbot.dm.log")
@patch("discordbot.dm._rate_limited_request", side_effect=_discord())
@patch("discordbot.dm.finalize_dm", return_value=True)
@patch("discordbot.dm.mark_dm_sending", return_value=True)
@patch("discordbot.dm.claim_dm", return_value=_granted())
class SendDMTests(SimpleTestCase):
    def _final(self, finalize: MagicMock) -> DMFinalizeBody:
        finalize.assert_called_once()
        self.assertEqual(finalize.call_args.args[0], LEDGER_ID)
        body = finalize.call_args.args[1]
        self.assertIsInstance(body, DMFinalizeBody)
        return body

    def _claim(self, claim: MagicMock) -> DMClaimBody:
        claim.assert_called_once()
        body = claim.call_args.args[0]
        self.assertIsInstance(body, DMClaimBody)
        return body

    def _posts(self, request: MagicMock) -> list[Any]:
        return [
            c
            for c in request.call_args_list
            if not c.args[1].endswith(CHANNEL_URL_SUFFIX)
        ]

    @override_settings(TEST=True, TEST_DISCORD_USER_ID="111")
    def test_test_mode_skip_records_and_no_discord_call(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        hook = MagicMock()
        outcome = send_dm(_req(), on_claimed=hook)
        self.assertEqual(self._claim(claim).initial_status, DMStatus.SKIPPED_TEST_MODE)
        request.assert_not_called()
        mark.assert_not_called()
        finalize.assert_not_called()
        self.assertEqual(outcome.status, DMStatus.SKIPPED_TEST_MODE)
        self.assertEqual(outcome.ledger_id, LEDGER_ID)
        hook.assert_called_once_with(LEDGER_ID, DMStatus.SKIPPED_TEST_MODE)
        self.assertIn(
            "dm_skipped_test_mode", [c.args[0] for c in log.info.call_args_list]
        )

    def test_skip_status_disabled_records_without_send(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        hook = MagicMock()
        outcome = send_dm(
            _req(
                content=None,
                components=[{"type": 10, "content": "x"}],
                flags=V2_FLAG,
                skip_status=DMStatus.SKIPPED_DISABLED,
            ),
            on_claimed=hook,
        )
        body = self._claim(claim)
        self.assertEqual(body.initial_status, DMStatus.SKIPPED_DISABLED)
        self.assertEqual(body.discord_user_id, "222")
        request.assert_not_called()
        mark.assert_not_called()
        finalize.assert_not_called()
        self.assertEqual(outcome.status, DMStatus.SKIPPED_DISABLED)
        hook.assert_called_once_with(LEDGER_ID, DMStatus.SKIPPED_DISABLED)

    def test_skip_status_must_be_a_skip(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        with self.assertRaises(ValueError):
            send_dm(_req(skip_status=DMStatus.SENT))
        claim.assert_not_called()

    @override_settings(TEST=True, TEST_DISCORD_USER_ID="222", DISCORD_BOT_TOKEN="")
    def test_test_mode_target_user_skips_without_bot_token(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        outcome = send_dm(_req())
        self.assertEqual(self._claim(claim).initial_status, DMStatus.SKIPPED_TEST_MODE)
        self.assertEqual(outcome.status, DMStatus.SKIPPED_TEST_MODE)
        self.assertFalse(outcome.auth_rejected)
        request.assert_not_called()

    @override_settings(TEST=True, TEST_DISCORD_USER_ID="222", DISCORD_BOT_TOKEN="tok")
    def test_test_mode_target_user_sends(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        outcome = send_dm(_req())
        self.assertIsNone(self._claim(claim).initial_status)
        self.assertEqual(outcome.status, DMStatus.SENT)
        self.assertEqual(len(self._posts(request)), 1)

    @override_settings(TEST=True, TEST_DISCORD_USER_ID="")
    def test_test_mode_empty_target_skips_all(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        outcome = send_dm(_req())
        self.assertEqual(self._claim(claim).initial_status, DMStatus.SKIPPED_TEST_MODE)
        self.assertEqual(outcome.status, DMStatus.SKIPPED_TEST_MODE)
        request.assert_not_called()

    def test_has_components_derived_from_payload(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        send_dm(_req(components=[{"type": 1, "components": []}]))
        self.assertTrue(claim.call_args.args[0].has_components)
        claim.reset_mock()
        send_dm(_req(components=[]))
        self.assertFalse(claim.call_args.args[0].has_components)
        claim.reset_mock()
        send_dm(_req())
        self.assertFalse(claim.call_args.args[0].has_components)

    def test_claim_body_carries_request_fields(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        send_dm(
            _req(
                recipient_user_id=3,
                organization_id=4,
                tournament_log_id=9,
                context={"a": 1},
            )
        )
        body = self._claim(claim)
        self.assertEqual(body.kind, "test_notification")
        self.assertEqual(body.idempotency_key, "test_notification:1:abc")
        self.assertEqual(body.discord_user_id, "222")
        self.assertEqual((body.subject_type, body.subject_id), ("event", 5))
        self.assertEqual(
            (body.recipient_user_id, body.organization_id, body.tournament_log_id),
            (3, 4, 9),
        )
        self.assertEqual(body.context, {"a": 1})
        self.assertTrue(body.claim_token.startswith("local:"))
        self.assertEqual(mark.call_args.kwargs["claim_token"], body.claim_token)
        self.assertEqual(finalize.call_args.args[1].claim_token, body.claim_token)

    def test_no_discord_id_records_skip_and_runs_hook(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        hook = MagicMock()
        outcome = send_dm(_req(discord_user_id=None), on_claimed=hook)
        body = self._claim(claim)
        self.assertEqual(body.initial_status, DMStatus.SKIPPED_NO_DISCORD)
        self.assertEqual(body.discord_user_id, "")
        self.assertEqual(outcome.status, DMStatus.SKIPPED_NO_DISCORD)
        hook.assert_called_once_with(LEDGER_ID, DMStatus.SKIPPED_NO_DISCORD)
        request.assert_not_called()
        finalize.assert_not_called()

    def test_skip_claim_unreachable_is_ledger_unavailable(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        claim.return_value = None
        hook = MagicMock()
        outcome = send_dm(_req(discord_user_id=None), on_claimed=hook)
        self.assertEqual(outcome.status, "ledger_unavailable")
        hook.assert_not_called()

    def test_skip_hook_raises_is_logged_and_skip_returned(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        outcome = send_dm(
            _req(discord_user_id=None),
            on_claimed=MagicMock(side_effect=RuntimeError("x")),
        )
        self.assertEqual(outcome.status, DMStatus.SKIPPED_NO_DISCORD)
        self.assertIn(
            "dm_on_claimed_failed", [c.args[0] for c in log.error.call_args_list]
        )

    def test_ledger_unavailable_fails_closed(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        claim.return_value = None
        hook = MagicMock()
        outcome = send_dm(_req(), on_claimed=hook)
        request.assert_not_called()
        hook.assert_not_called()
        finalize.assert_not_called()
        self.assertEqual(outcome.status, "ledger_unavailable")
        self.assertIsNone(outcome.ledger_id)
        self.assertIn(
            "dm_ledger_unavailable", [c.args[0] for c in log.error.call_args_list]
        )

    def test_duplicate_returns_duplicate_no_hook(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        claim.return_value = _granted(granted=False)
        hook = MagicMock()
        outcome = send_dm(_req(), on_claimed=hook)
        self.assertEqual(outcome.status, "duplicate")
        self.assertEqual(outcome.ledger_id, LEDGER_ID)
        hook.assert_not_called()
        request.assert_not_called()
        finalize.assert_not_called()
        self.assertIn(
            "dm_duplicate_suppressed", [c.args[0] for c in log.info.call_args_list]
        )

    def test_hook_runs_after_claim_before_post(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        order: list[str] = []
        claim.side_effect = lambda body: order.append("claim") or _granted()
        request.side_effect = lambda m, url, **kw: order.append(
            url.rsplit("/", 1)[-1]
        ) or _discord()(m, url, **kw)
        send_dm(_req(), on_claimed=lambda dm_id, status: order.append(f"hook:{status}"))
        self.assertEqual(order, ["claim", "hook:pending", "channels", "messages"])

    def test_hook_raises_finalizes_before_send_failed(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        outcome = send_dm(
            _req(), on_claimed=MagicMock(side_effect=RuntimeError("boom"))
        )
        body = self._final(finalize)
        self.assertEqual(body.status, "failed")
        self.assertEqual(body.error_class, "before_send_failed")
        self.assertEqual(outcome.status, DMStatus.FAILED)
        request.assert_not_called()
        mark.assert_not_called()

    def test_channel_open_failure_stores_code(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        request.side_effect = _discord(
            channel=lambda: _response(400, {"code": 50007, "message": "Cannot send"})
        )
        outcome = send_dm(_req())
        body = self._final(finalize)
        self.assertEqual(body.status, "failed")
        self.assertEqual(body.error_code, 50007)
        self.assertEqual(body.http_status, 400)
        self.assertEqual(body.error_class, "permanent")
        self.assertEqual(outcome.error_code, 50007)
        mark.assert_not_called()

    def test_channel_open_other_failure_pre_send(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        request.side_effect = _discord(channel=_raises(requests.ReadTimeout("slow")))
        send_dm(_req())
        body = self._final(finalize)
        self.assertEqual((body.status, body.error_class), ("failed", "pre_send"))
        mark.assert_not_called()

    def test_channel_open_missing_id_pre_send(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        request.side_effect = _discord(channel=lambda: _response(200, {}))
        send_dm(_req())
        body = self._final(finalize)
        self.assertEqual((body.status, body.error_class), ("failed", "pre_send"))

    def test_http_error_50007_permanent(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        request.side_effect = _discord(
            post=lambda: _response(
                403, {"code": 50007, "message": "Cannot send messages to this user"}
            )
        )
        outcome = send_dm(_req())
        body = self._final(finalize)
        self.assertEqual(
            (body.status, body.error_class, body.error_code),
            ("failed", "permanent", 50007),
        )
        self.assertEqual(body.http_status, 403)
        self.assertIn("Cannot send messages", body.error)
        self.assertEqual(outcome.status, DMStatus.FAILED)
        self.assertIn("dm_failed", [c.args[0] for c in log.warning.call_args_list])

    def test_other_4xx_retryable_pre_send(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        request.side_effect = _discord(
            post=lambda: _response(400, {"code": 50035, "message": "Invalid Form Body"})
        )
        send_dm(_req())
        body = self._final(finalize)
        self.assertEqual(
            (body.status, body.error_class, body.error_code),
            ("failed", "pre_send", 50035),
        )

    def test_rate_limit_timeout_retryable(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        request.side_effect = _discord(
            post=_raises(DiscordRateLimitTimeout("no token"))
        )
        send_dm(_req())
        body = self._final(finalize)
        self.assertEqual(
            (body.status, body.error_class), ("failed", "rate_limit_timeout")
        )

    def test_429_after_retries_rate_limit_timeout(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        request.side_effect = _discord(
            post=lambda: _response(429, {"retry_after": 1.0, "message": "rate"})
        )
        send_dm(_req())
        body = self._final(finalize)
        self.assertEqual(
            (body.status, body.error_class, body.http_status),
            ("failed", "rate_limit_timeout", 429),
        )

    def test_connect_timeout_failed_pre_send(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        request.side_effect = _discord(post=_raises(requests.ConnectTimeout("connect")))
        send_dm(_req())
        body = self._final(finalize)
        self.assertEqual((body.status, body.error_class), ("failed", "pre_send"))

    def test_read_timeout_unknown(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        request.side_effect = _discord(post=_raises(requests.ReadTimeout("read")))
        outcome = send_dm(_req())
        body = self._final(finalize)
        self.assertEqual((body.status, body.error_class), ("unknown", None))
        self.assertEqual(outcome.status, DMStatus.UNKNOWN)

    def test_connection_error_unknown(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        request.side_effect = _discord(post=_raises(requests.ConnectionError("reset")))
        send_dm(_req())
        self.assertEqual(self._final(finalize).status, "unknown")

    def test_5xx_unknown(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        request.side_effect = _discord(post=lambda: _response(503, {"message": "busy"}))
        send_dm(_req())
        body = self._final(finalize)
        self.assertEqual((body.status, body.http_status), ("unknown", 503))

    def test_401_failed_and_flagged(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        resp = _response(401, {"code": 0, "message": "401: Unauthorized"})
        request.side_effect = _discord(
            post=_raises(DiscordAuthError("401", response=resp))
        )
        self.assertTrue(send_dm(_req()).auth_rejected)
        body = self._final(finalize)
        self.assertEqual(
            (body.status, body.error_class, body.http_status),
            ("failed", "pre_send", 401),
        )

    def test_401_on_channel_open_failed_and_flagged(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        resp = _response(401, {"message": "401: Unauthorized"})
        request.side_effect = _discord(
            channel=_raises(DiscordAuthError("401", response=resp))
        )
        self.assertTrue(send_dm(_req()).auth_rejected)
        self.assertEqual(self._final(finalize).status, "failed")

    def test_html_502_body_parses(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        self.assertEqual(
            _parse_discord_error(_http_error(502, raw="<html>Bad gateway</html>"))[:2],
            (502, None),
        )
        request.side_effect = _discord(
            post=lambda: _response(502, raw="<html>Bad gateway</html>")
        )
        send_dm(_req())
        body = self._final(finalize)
        self.assertEqual(
            (body.status, body.http_status, body.error_code), ("unknown", 502, None)
        )
        self.assertNotIn("<html>", body.error)

    def test_responseless_exception_parses(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        status, code, message = _parse_discord_error(RuntimeError("plain"))
        self.assertEqual((status, code), (None, None))
        self.assertEqual(message, "plain")
        status, code, _ = _parse_discord_error(requests.HTTPError("no response"))
        self.assertEqual((status, code), (None, None))
        self.assertLessEqual(
            len(_parse_discord_error(RuntimeError("x" * 1000))[2]), 300
        )

    def test_json_non_dict_body_parses(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        self.assertEqual(
            _parse_discord_error(_http_error(400, [1, 2]))[:2], (400, None)
        )
        self.assertEqual(
            _parse_discord_error(_http_error(400, {"code": "x"}))[:2], (400, None)
        )

    def test_v2_payload_accepted(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        components = [{"type": 10, "content": "hi"}]
        outcome = send_dm(_req(content=None, components=components, flags=V2_FLAG))
        self.assertEqual(outcome.status, DMStatus.SENT)
        payload = self._posts(request)[0].kwargs["json"]
        self.assertEqual(payload["flags"], 32768)
        self.assertEqual(payload["components"], components)
        self.assertNotIn("content", payload)
        self.assertNotIn("embeds", payload)

    def test_v2_with_content_rejected(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        send_dm(
            _req(content="hi", components=[{"type": 10, "content": "x"}], flags=V2_FLAG)
        )
        body = self._final(finalize)
        self.assertEqual((body.status, body.error_class), ("failed", "permanent"))
        self.assertEqual(self._posts(request), [])
        mark.assert_not_called()

    def test_v2_with_embed_rejected(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        send_dm(
            _req(
                content=None,
                embed={"title": "t"},
                components=[{"type": 10}],
                flags=V2_FLAG,
            )
        )
        self.assertEqual(self._final(finalize).error_class, "permanent")
        self.assertEqual(self._posts(request), [])

    def test_empty_payload_rejected(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        send_dm(_req(content=None))
        body = self._final(finalize)
        self.assertEqual(
            (body.status, body.error_class, body.error),
            ("failed", "permanent", "empty_payload"),
        )
        self.assertEqual(self._posts(request), [])

    def test_mark_sending_false_no_post(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        for result in (False, None):
            with self.subTest(result=result):
                mark.return_value = result
                finalize.reset_mock()
                request.reset_mock()
                outcome = send_dm(_req())
                body = self._final(finalize)
                self.assertEqual(
                    (body.status, body.error_class), ("failed", "pre_send")
                )
                self.assertEqual(self._posts(request), [])
                self.assertEqual(outcome.status, DMStatus.FAILED)

    def test_success_stores_ids_and_nonce(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        outcome = send_dm(_req(embed={"title": "t"}, components=[{"type": 1}]))
        post = self._posts(request)[0]
        self.assertEqual(post.args[0], "POST")
        self.assertTrue(post.args[1].endswith(f"/channels/{CHANNEL_ID}/messages"))
        payload = post.kwargs["json"]
        self.assertEqual(payload["nonce"], f"dm{LEDGER_ID}")
        self.assertIs(payload["enforce_nonce"], True)
        self.assertEqual(payload["content"], "hello")
        self.assertEqual(payload["embeds"], [{"title": "t"}])
        self.assertNotIn("flags", payload)
        mark.assert_called_once()
        self.assertEqual(mark.call_args.args[0], LEDGER_ID)
        body = self._final(finalize)
        self.assertEqual(
            (
                body.status,
                body.discord_channel_id,
                body.discord_message_id,
                body.http_status,
            ),
            ("sent", CHANNEL_ID, MESSAGE_ID, 200),
        )
        self.assertEqual(
            (
                outcome.status,
                outcome.ledger_id,
                outcome.message_id,
                outcome.channel_id,
                outcome.error_code,
            ),
            (DMStatus.SENT, LEDGER_ID, MESSAGE_ID, CHANNEL_ID, None),
        )
        self.assertIn("dm_sent", [c.args[0] for c in log.info.call_args_list])

    def test_finalize_failure_logged(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        finalize.return_value = False
        outcome = send_dm(_req())
        self.assertEqual(outcome.status, DMStatus.SENT)
        self.assertIn(
            "dm_ledger_finalize_failed", [c.args[0] for c in log.error.call_args_list]
        )

    def test_every_exception_path_finalizes(
        self,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
        request: MagicMock,
        log: MagicMock,
    ) -> None:
        post_cases: list[tuple[BaseException, str]] = [
            (requests.ConnectTimeout("c"), "failed"),
            (requests.ReadTimeout("r"), "unknown"),
            (requests.ConnectionError("e"), "unknown"),
            (requests.RequestException("x"), "unknown"),
            (DiscordRateLimitTimeout("t"), "failed"),
            (_http_error(500, {"message": "x"}), "unknown"),
            (_http_error(400, {"code": 50007}), "failed"),
            (ValueError("bad json"), "unknown"),
            (RuntimeError("anything"), "unknown"),
        ]
        for exc, expected in post_cases:
            with self.subTest(stage="post", exc=type(exc).__name__):
                finalize.reset_mock()
                request.side_effect = _discord(post=_raises(exc))
                send_dm(_req())
                finalize.assert_called_once()
                self.assertEqual(finalize.call_args.args[1].status, expected)
        for exc in (
            requests.ConnectTimeout("c"),
            requests.ConnectionError("e"),
            DiscordRateLimitTimeout("t"),
            RuntimeError("anything"),
        ):
            with self.subTest(stage="channel", exc=type(exc).__name__):
                finalize.reset_mock()
                request.side_effect = _discord(channel=_raises(exc))
                send_dm(_req())
                finalize.assert_called_once()
                self.assertEqual(finalize.call_args.args[1].status, "failed")
        request.side_effect = _discord()
        with self.subTest(stage="mark raises"):
            finalize.reset_mock()
            mark.side_effect = RuntimeError("mark")
            send_dm(_req())
            finalize.assert_called_once()
            self.assertEqual(
                (
                    finalize.call_args.args[1].status,
                    finalize.call_args.args[1].error_class,
                ),
                ("failed", "pre_send"),
            )
        mark.side_effect = None
        with self.subTest(stage="interrupt after mark"):
            finalize.reset_mock()
            request.side_effect = _discord(post=_raises(KeyboardInterrupt()))
            with self.assertRaises(KeyboardInterrupt):
                send_dm(_req())
            finalize.assert_called_once()
            self.assertEqual(finalize.call_args.args[1].status, "unknown")
        with self.subTest(stage="interrupt before mark"):
            finalize.reset_mock()
            request.side_effect = _discord(channel=_raises(KeyboardInterrupt()))
            with self.assertRaises(KeyboardInterrupt):
                send_dm(_req())
            finalize.assert_called_once()
            self.assertEqual(
                (
                    finalize.call_args.args[1].status,
                    finalize.call_args.args[1].error_class,
                ),
                ("failed", "pre_send"),
            )


@override_settings(TEST=False)
@patch("discordbot.internal_client.dm_ledger.time.sleep")
@patch("discordbot.dm._rate_limited_request", side_effect=_discord())
class SendDMLedgerTransportTests(SimpleTestCase):
    def test_claim_timeout_then_retry_sends_once(
        self, request: MagicMock, sleep: MagicMock
    ) -> None:
        created = MagicMock(spec=requests.Response)
        created.status_code = 201
        created.json.return_value = {
            "id": LEDGER_ID,
            "status": "pending",
            "attempts": 1,
        }
        no_content = MagicMock(spec=requests.Response)
        no_content.status_code = 204
        finalized = MagicMock(spec=requests.Response)
        finalized.status_code = 200
        finalized.json.return_value = {"id": LEDGER_ID, "status": "sent"}
        with patch(
            "app.internal_client.transport.post",
            side_effect=[None, created, no_content, finalized],
        ) as post:
            outcome = send_dm(_req())
        self.assertEqual(outcome.status, DMStatus.SENT)
        paths = [c.args[0] for c in post.call_args_list]
        self.assertEqual(
            paths,
            [
                "/discord/dms/claim/",
                "/discord/dms/claim/",
                f"/discord/dms/{LEDGER_ID}/sending/",
                f"/discord/dms/{LEDGER_ID}/finalize/",
            ],
        )
        tokens = {c.args[1]["claim_token"] for c in post.call_args_list}
        self.assertEqual(len(tokens), 1)
        posts = [
            c
            for c in request.call_args_list
            if not c.args[1].endswith(CHANNEL_URL_SUFFIX)
        ]
        self.assertEqual(len(posts), 1)


class ClaimTokenTests(SimpleTestCase):
    def test_uses_celery_task_id(self) -> None:
        task = MagicMock()
        task.request.id = "task-abc"
        with patch("discordbot.dm.current_task", task):
            token = dm._claim_token()
        self.assertTrue(token.startswith("task-abc:"))
        self.assertEqual(len(token.split(":")[1]), 8)

    def test_local_without_task(self) -> None:
        with patch("discordbot.dm.current_task", None):
            self.assertTrue(dm._claim_token().startswith("local:"))

    def test_tokens_unique(self) -> None:
        self.assertNotEqual(dm._claim_token(), dm._claim_token())
