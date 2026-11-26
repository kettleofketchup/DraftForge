from unittest.mock import patch

import requests
from django.test import SimpleTestCase
from structlog.testing import capture_logs

from discordbot.delivery_types import DeliveryFailure, FailureCategory, FailurePhase
from discordbot.http_evidence import (
    decode_response_json,
    discord_error_code,
    failure_from_exception,
    failure_from_response,
)
from discordbot.utils import DiscordAuthError, _rate_limited_request


def _resp(
    status: int, body: bytes, content_type: str = "application/json"
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.headers["Content-Type"] = content_type
    return response


class HttpEvidenceTest(SimpleTestCase):
    def test_falsey_403_response_keeps_status_and_code(self) -> None:
        response = _resp(403, b'{"code":50013,"message":"private"}')
        self.assertFalse(response)
        self.assertEqual(
            failure_from_response(response, FailurePhase.CREATE),
            DeliveryFailure(
                FailurePhase.CREATE, FailureCategory.HTTP_ERROR, 403, 50013
            ),
        )

    def test_code_extraction_tolerates_shapes(self) -> None:
        for body in (
            b"[1]",
            b'"str"',
            b"null",
            b"<html>",
            b"",
            b'{"code":true}',
            b'{"code":"50013"}',
        ):
            with self.subTest(body=body):
                response = _resp(403, body)
                self.assertIsNone(discord_error_code(response))
                self.assertEqual(
                    failure_from_response(response, FailurePhase.CREATE).status, 403
                )
        self.assertIsNone(discord_error_code(None))

    def test_status_matrix(self) -> None:
        for status, category in (
            (401, FailureCategory.AUTH),
            (429, FailureCategory.RATE_LIMITED),
            (500, FailureCategory.HTTP_ERROR),
        ):
            with self.subTest(status=status):
                self.assertEqual(
                    failure_from_response(
                        _resp(status, b"{}"), FailurePhase.CREATE
                    ).category,
                    category,
                )

    def test_exception_without_response_is_transport(self) -> None:
        failure = failure_from_exception(requests.Timeout(), FailurePhase.CREATE)
        self.assertEqual(failure.category, FailureCategory.TRANSPORT)
        self.assertIsNone(failure.status)

    def test_json_decode_error_retains_original_response(self) -> None:
        response = _resp(201, b"<html>private</html>")
        with self.assertRaises(requests.exceptions.JSONDecodeError) as caught:
            decode_response_json(response)
        self.assertIs(caught.exception.response, response)
        self.assertEqual(
            failure_from_exception(caught.exception, FailurePhase.CREATE),
            DeliveryFailure(
                FailurePhase.CREATE, FailureCategory.MALFORMED_RESPONSE, 201
            ),
        )

    def test_auth_error_keeps_response(self) -> None:
        failure = failure_from_exception(
            DiscordAuthError("private", response=_resp(401, b"{}")), FailurePhase.CREATE
        )
        self.assertEqual(failure.status, 401)

    def test_safe_json_is_allowlisted(self) -> None:
        failure = failure_from_response(
            _resp(403, b'{"code":50013,"message":"private","errors":{}}'),
            FailurePhase.CREATE,
        )
        self.assertEqual(
            failure.safe_json(),
            {"phase": "create", "category": "http_error", "status": 403, "code": 50013},
        )
        self.assertEqual(failure.log_fields(), failure.safe_json())
        self.assertEqual(
            failure_from_response(None, FailurePhase.CREATE).safe_json(),
            {"phase": "create", "category": "transport"},
        )

    def test_429_malformed_retry_body_preserves_response(self) -> None:
        bodies = (
            b"<html>private</html>",
            b"",
            b"[]",
            b'"private"',
            b"null",
            b'{"retry_after":true}',
            b'{"retry_after":"private"}',
            b'{"retry_after":-1}',
            b'{"retry_after":NaN}',
            b'{"retry_after":Infinity}',
        )
        for body in bodies:
            for attempts in (1, 3):
                with self.subTest(body=body, attempts=attempts):
                    response = _resp(429, body)
                    with (
                        patch(
                            "discordbot.utils.requests.request", return_value=response
                        ) as request,
                        patch("discordbot.utils._acquire_rate_limit_token"),
                        patch("discordbot.utils._time.sleep") as sleep,
                        capture_logs() as logs,
                    ):
                        result = _rate_limited_request(
                            "POST", "https://discord.invalid", max_retries=attempts
                        )
                    self.assertIs(result, response)
                    self.assertEqual(
                        failure_from_response(result, FailurePhase.CREATE).status, 429
                    )
                    self.assertEqual(request.call_count, attempts)
                    self.assertEqual(sleep.call_count, attempts - 1)
                    for call in sleep.call_args_list:
                        self.assertEqual(call.args, (1.0,))
                    self.assertNotIn("private", str(logs))

    def test_429_numeric_retry_metadata_retains_bounded_retry(self) -> None:
        for delay in (0, 0.25, 2):
            with self.subTest(delay=delay):
                response = _resp(
                    429, ('{"retry_after":%s,"message":"private"}' % delay).encode()
                )
                response.headers["X-Private"] = "private"
                with (
                    patch(
                        "discordbot.utils.requests.request", return_value=response
                    ) as request,
                    patch("discordbot.utils._acquire_rate_limit_token"),
                    patch("discordbot.utils._time.sleep") as sleep,
                    capture_logs() as logs,
                ):
                    self.assertIs(
                        _rate_limited_request("POST", "https://discord.invalid"),
                        response,
                    )
                self.assertEqual(request.call_count, 3)
                self.assertEqual(sleep.call_count, 2)
                self.assertEqual(sleep.call_args.args, (delay,))
                self.assertNotIn("private", str(logs))

    def test_retry_budget_must_allow_a_request(self) -> None:
        with patch("discordbot.utils.requests.request") as request:
            with self.assertRaises(ValueError):
                _rate_limited_request("POST", "https://discord.invalid", max_retries=0)
        request.assert_not_called()
