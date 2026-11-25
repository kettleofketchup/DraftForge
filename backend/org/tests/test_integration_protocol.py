"""Strict wire protocol for the promotion integration routes.

Bodies are parsed by hand rather than with plain ``json.loads`` so that
duplicate keys, non-finite numbers, invalid UTF-8, trailing data and
oversized or mistyped requests are all refused, and errors come back in the
contract envelope without echoing what the client sent.
"""

from datetime import UTC, datetime, timedelta

from django.core import signing
from django.test import SimpleTestCase, override_settings
from django.urls import path
from rest_framework.response import Response
from rest_framework.test import APIClient

from org.integration import cursors
from org.integration.base import IntegrationAPIView
from org.integration.errors import IntegrationError
from org.integration.parsers import (
    MAX_BATCH,
    MAX_BODY_BYTES,
    expect_object,
    format_id,
    json_body,
    parse_batch,
    parse_choice,
    parse_hash,
    parse_id,
    parse_limit,
    parse_timestamp,
    parse_uuid,
)


class _Echo(IntegrationAPIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request) -> Response:
        return Response({"keys": sorted(json_body(request))})


class _Boom(IntegrationAPIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request) -> Response:
        raise RuntimeError("SELECT secret FROM tokens WHERE dfk_abc")

    def post(self, request) -> Response:
        raise IntegrationError("mapping_changed", 409)


urlpatterns = [path("echo/", _Echo.as_view()), path("boom/", _Boom.as_view())]


@override_settings(ROOT_URLCONF=__name__)
class ParserTests(SimpleTestCase):
    def post(self, body: bytes, content_type: str = "application/json"):
        return APIClient().generic("POST", "/echo/", body, content_type=content_type)

    def assert_invalid(self, body: bytes, status: int = 400, code: str = "") -> None:
        resp = self.post(body)
        self.assertEqual(resp.status_code, status, resp.content)
        error = resp.json()["error"]
        self.assertEqual(set(error), {"code", "message", "request_id"})
        if code:
            self.assertEqual(error["code"], code)

    def test_accepts_plain_object(self) -> None:
        resp = self.post(b'{"b": 1, "a": {"c": [1, "x"]}}')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json(), {"keys": ["a", "b"]})

    def test_accepts_utf8_charset(self) -> None:
        resp = self.post(b'{"a":"\xc3\xa9"}', "application/json; charset=utf-8")
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_rejects_duplicate_keys_top_level_and_nested(self) -> None:
        for body in (
            b'{"a":1,"a":2}',
            b'{"a":{"b":1,"b":1}}',
            b'{"a":[{"x":1},{"y":1,"y":2}]}',
        ):
            with self.subTest(body=body):
                self.assert_invalid(body, code="invalid_request")

    def test_rejects_non_finite_numbers(self) -> None:
        for body in (b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}'):
            with self.subTest(body=body):
                self.assert_invalid(body)

    def test_rejects_invalid_utf8_and_lone_surrogates(self) -> None:
        for body in (
            b'{"a":"\xff"}',
            b'{"a":"\xed\xa0\x80"}',
            b'{"a":"\\ud800"}',
            b'{"\\udfff":1}',
            b'\xef\xbb\xbf{"a":1}',
        ):
            with self.subTest(body=body):
                self.assert_invalid(body)

    def test_rejects_trailing_values_and_non_objects(self) -> None:
        for body in (
            b'{"a":1}{"b":2}',
            b'{"a":1} x',
            b'{"a":1},',
            b"[]",
            b'"a"',
            b"1",
            b"null",
            b"",
            b"{",
            b'{"a":1,}',
        ):
            with self.subTest(body=body):
                self.assert_invalid(body)

    def test_rejects_deep_nesting_without_crashing(self) -> None:
        self.assert_invalid(b'{"a":' + b"[" * 5000 + b"]" * 5000 + b"}")

    def test_size_limit_is_413(self) -> None:
        filler = b"x" * (MAX_BODY_BYTES - len(b'{"a":""}'))
        self.assertEqual(self.post(b'{"a":"' + filler + b'"}').status_code, 200)
        self.assert_invalid(
            b'{"a":"' + filler + b'x"}', status=413, code="request_too_large"
        )

    def test_content_type_is_415(self) -> None:
        for content_type in (
            "text/plain",
            "application/x-www-form-urlencoded",
            "application/json; charset=latin-1",
        ):
            with self.subTest(content_type=content_type):
                resp = self.post(b'{"a":1}', content_type)
                self.assertEqual(resp.status_code, 415)
                self.assertEqual(resp.json()["error"]["code"], "unsupported_media_type")

    def test_error_does_not_echo_payload(self) -> None:
        resp = self.post(b'{"secret-key-name":1,"secret-key-name":2}')
        self.assertNotIn("secret-key-name", resp.content.decode())

    def test_method_not_allowed_envelope(self) -> None:
        resp = APIClient().get("/echo/")
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(resp.json()["error"]["code"], "method_not_allowed")

    def test_unexpected_exception_is_hidden_500(self) -> None:
        with self.assertLogs("org.integration.errors", level="ERROR"):
            resp = APIClient().get("/boom/")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["error"]["code"], "internal_error")
        self.assertNotIn("SELECT", resp.content.decode())
        self.assertNotIn("dfk_", resp.content.decode())

    def test_integration_error_uses_its_code_and_status(self) -> None:
        resp = APIClient().post("/boom/", {}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"]["code"], "mapping_changed")
        self.assertEqual(resp["X-Request-ID"], resp.json()["error"]["request_id"])


class FieldValidatorTests(SimpleTestCase):
    def assert_rejects(self, fn, *values) -> None:
        for value in values:
            with self.subTest(value=value), self.assertRaises(IntegrationError) as ctx:
                fn(value, "field")
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertNotIn(repr(value), ctx.exception.message)

    def test_expect_object_requires_exact_keys(self) -> None:
        self.assertEqual(
            expect_object({"a": 1, "b": None}, "x", ("a", "b")),
            {
                "a": 1,
                "b": None,
            },
        )
        for bad in ({"a": 1}, {"a": 1, "b": 2, "c": 3}, [], "x", None):
            with self.subTest(bad=bad), self.assertRaises(IntegrationError):
                expect_object(bad, "x", ("a", "b"))

    def test_parse_id_canonical_positive_int64_string(self) -> None:
        self.assertEqual(parse_id("1", "f"), 1)
        self.assertEqual(parse_id("9223372036854775807", "f"), 2**63 - 1)
        self.assert_rejects(
            parse_id,
            "0",
            "01",
            "-1",
            "+1",
            " 1",
            "1 ",
            "1e3",
            "1.0",
            "9223372036854775808",
            "١٢",
            1,
            True,
            None,
            "",
        )

    def test_parse_id_nullable(self) -> None:
        self.assertIsNone(parse_id(None, "f", nullable=True))
        with self.assertRaises(IntegrationError):
            parse_id(None, "f")

    def test_format_id_round_trips(self) -> None:
        self.assertEqual(format_id(9001), "9001")
        self.assertIsNone(format_id(None))

    def test_parse_timestamp_utc_z_micro_and_future_bound(self) -> None:
        now = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
        self.assertEqual(
            parse_timestamp("2026-11-24T11:30:00Z", "t", now=now),
            datetime(2026, 11, 24, 11, 30, tzinfo=UTC),
        )
        self.assertEqual(
            parse_timestamp("2026-11-24T11:30:00.123456Z", "t", now=now).microsecond,
            123456,
        )
        self.assertEqual(
            parse_timestamp("2026-11-24T12:05:00Z", "t", now=now),
            now + timedelta(minutes=5),
        )
        for bad in (
            "2026-11-24T12:05:00.000001Z",
            "2026-11-24T11:30:00+00:00",
            "2026-11-24T11:30:00",
            "2026-11-24T11:30:00.1234567Z",
            "2026-11-24 11:30:00Z",
            "2026-11-24t11:30:00z",
            "2026-02-30T11:30:00Z",
            "2026-11-24T24:00:00Z",
            "２026-11-24T11:30:00Z",
            1732447800,
            None,
        ):
            with self.subTest(bad=bad), self.assertRaises(IntegrationError):
                parse_timestamp(bad, "t", now=now)

    def test_parse_uuid_and_hash_lowercase_canonical(self) -> None:
        uid = "3f2b6c1e-8a4d-4f6b-9c2e-1d7a5b3e9f01"
        self.assertEqual(parse_uuid(uid, "u"), uid)
        self.assert_rejects(
            parse_uuid, uid.upper(), uid.replace("-", ""), "{" + uid + "}", None
        )
        digest = "a" * 64
        self.assertEqual(parse_hash(digest, "h"), digest)
        self.assert_rejects(parse_hash, "A" * 64, "a" * 63, "g" * 64, None)

    def test_parse_choice(self) -> None:
        self.assertEqual(parse_choice("occasion", "l", ("occasion",)), "occasion")
        for bad in ("OCCASION", "", None, 1):
            with self.subTest(bad=bad), self.assertRaises(IntegrationError):
                parse_choice(bad, "l", ("occasion",))

    def test_parse_batch_bounds(self) -> None:
        self.assertEqual(len(parse_batch([{}] * MAX_BATCH, "entries")), MAX_BATCH)
        self.assertEqual(parse_batch([], "entries", min_items=0), [])
        for bad in ([], [{}] * (MAX_BATCH + 1), {}, None):
            with self.subTest(n=bad if not isinstance(bad, list) else len(bad)):
                with self.assertRaises(IntegrationError):
                    parse_batch(bad, "entries")

    def test_parse_limit(self) -> None:
        self.assertEqual(parse_limit(None), 100)
        self.assertEqual(parse_limit("1"), 1)
        self.assertEqual(parse_limit("100"), 100)
        for bad in ("0", "101", "01", "-1", "abc", " 5", "1e2", ""):
            with self.subTest(bad=bad), self.assertRaises(IntegrationError):
                parse_limit(bad)


@override_settings(SECRET_KEY="cursor-test-secret")
class CursorTests(SimpleTestCase):
    def encode(self, **overrides) -> str:
        args = {
            "org_id": 41,
            "resource": "event_recipients:720",
            "key": ["123456789012345678", 9001],
            "fingerprint": "f" * 64,
        }
        args.update(overrides)
        return cursors.encode_cursor(**args)

    def decode(self, raw: str, **overrides):
        args = {
            "org_id": 41,
            "resource": "event_recipients:720",
            "fingerprint": "f" * 64,
        }
        args.update(overrides)
        return cursors.decode_cursor(raw, **args)

    def assert_error(self, code: str, status: int, raw: str, **overrides) -> None:
        with self.assertRaises(IntegrationError) as ctx:
            self.decode(raw, **overrides)
        self.assertEqual(
            (ctx.exception.code, ctx.exception.status_code), (code, status)
        )

    def test_round_trip(self) -> None:
        raw = self.encode()
        self.assertLessEqual(len(raw), cursors.MAX_CURSOR_BYTES)
        self.assertEqual(self.decode(raw), ["123456789012345678", 9001])

    def test_other_org_or_resource_is_invalid(self) -> None:
        raw = self.encode()
        self.assert_error("invalid_cursor", 400, raw, org_id=42)
        self.assert_error("invalid_cursor", 400, raw, resource="event_recipients:721")
        self.assert_error("invalid_cursor", 400, raw, resource="contributions")

    def test_changed_fingerprint_is_mapping_changed(self) -> None:
        self.assert_error("mapping_changed", 409, self.encode(), fingerprint="e" * 64)

    def test_tampered_or_foreign_signature_is_invalid(self) -> None:
        raw = self.encode()
        flipped = raw[:-1] + ("A" if raw[-1] != "A" else "B")
        self.assert_error("invalid_cursor", 400, flipped)
        forged = signing.dumps(
            {"v": 1, "o": 41, "r": "event_recipients:720", "k": [], "f": "f" * 64},
            salt="some.other.salt",
        )
        self.assert_error("invalid_cursor", 400, forged)
        with override_settings(SECRET_KEY="another-secret"):
            other = self.encode()
        self.assert_error("invalid_cursor", 400, other)

    def test_oversized_or_non_ascii_cursor_is_invalid(self) -> None:
        self.assert_error("invalid_cursor", 400, "a" * (cursors.MAX_CURSOR_BYTES + 1))
        self.assert_error("invalid_cursor", 400, "é")
        self.assert_error("invalid_cursor", 400, "")

    def test_encode_refuses_oversized_key(self) -> None:
        with self.assertRaises(ValueError):
            self.encode(key=["x" * 4000])
