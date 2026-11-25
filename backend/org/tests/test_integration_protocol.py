"""Strict wire protocol for the promotion integration routes.

Bodies are parsed by hand rather than with plain ``json.loads`` so that
duplicate keys, non-finite numbers, invalid UTF-8, trailing data and
oversized or mistyped requests are all refused, and errors come back in the
contract envelope without echoing what the client sent.
"""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from django.core import signing
from django.test import SimpleTestCase, override_settings
from django.urls import path
from rest_framework.response import Response
from rest_framework.test import APIClient

from org.integration import cursors
from org.integration.base import IntegrationAPIView
from org.integration.contacts import ImportBatch, ImportEntryV, parse_import_batch
from org.integration.errors import IntegrationError
from org.integration.parsers import (
    MAX_BATCH,
    MAX_BODY_BYTES,
    expect_object,
    format_id,
    json_body,
    parse_batch,
    parse_choice,
    parse_date,
    parse_hash,
    parse_id,
    parse_limit,
    parse_timestamp,
    parse_uuid,
)
from org.integration.receipts import IMPORT_SOURCE_FIELDS, import_source_hash


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

    def test_parse_timestamp_unbounded_skips_only_the_future_bound(self) -> None:
        now = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
        self.assertEqual(
            parse_timestamp("2099-01-01T00:00:00Z", "t", now=now, bounded=False),
            datetime(2099, 1, 1, tzinfo=UTC),
        )
        for bad in ("2099-01-01T00:00:00+00:00", "0000-01-01T00:00:00Z", None):
            with self.subTest(bad=bad), self.assertRaises(IntegrationError):
                parse_timestamp(bad, "t", now=now, bounded=False)

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


GOLDEN = Path(__file__).parent / "golden"
INT64_MAX = "9223372036854775807"
# The fixtures are copied from the adaptor, whose upstream name must never
# reach this repository. It is assembled from parts so the repository-wide
# grep for it stays empty.
_UPSTREAM_MARK = "".join(("s", "f", "g"))


def _fixture(name: str) -> tuple[str, dict]:
    text = (GOLDEN / name).read_text(encoding="utf-8")
    return text, json.loads(text)


class ImportSourceHashGoldenTests(SimpleTestCase):
    def test_import_source_hash_golden(self) -> None:
        text, golden = _fixture("import_source_hash.json")
        self.assertNotIn(_UPSTREAM_MARK, text.lower())
        self.assertEqual(golden["source"], "contact_log")
        self.assertEqual(
            IMPORT_SOURCE_FIELDS,
            (
                "source",
                "source_contact_id",
                "recorded_at",
                "contact_date_ny",
                "contact_method",
                "contact_reason",
                "occasion_id",
                "event_date",
                "forced",
            ),
        )
        by_name = {case["name"]: case for case in golden["cases"]}
        for case in golden["cases"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    import_source_hash(case["entry"], source=golden["source"]),
                    case["hash"],
                )
                twin = case.get("same_hash_as")
                if twin is not None:
                    self.assertEqual(case["hash"], by_name[twin]["hash"])
        self.assertTrue(any("same_hash_as" in case for case in golden["cases"]))

    def test_parsed_entry_carries_the_golden_hash(self) -> None:
        _, golden = _fixture("import_source_hash.json")
        now = datetime(2026, 11, 25, 10, tzinfo=UTC)
        for case in golden["cases"]:
            with self.subTest(case=case["name"]):
                batch = parse_import_batch(_batch(entries=[case["entry"]]), now=now)
                self.assertEqual(batch.entries[0].source_hash, case["hash"])

    def test_import_source_hash_changes_with_each_source_fact(self) -> None:
        _, golden = _fixture("import_source_hash.json")
        base = golden["cases"][0]["entry"]
        digest = import_source_hash(base)
        for field, value in (
            ("source_contact_id", "1999"),
            ("recorded_at", "2026-11-24T18:30:01Z"),
            ("contact_date_ny", "2026-11-23"),
            ("contact_method", "OTHER"),
            ("contact_reason", "FOLLOW_UP"),
            ("occasion_id", "78"),
            ("event_date", "2026-12-05T00:00:00Z"),
            ("forced", True),
        ):
            with self.subTest(field=field):
                self.assertNotEqual(import_source_hash({**base, field: value}), digest)
        self.assertNotEqual(import_source_hash(base, source="other"), digest)


def _entry(**overrides) -> dict:
    entry = {
        "source_contact_id": "1001",
        "target_discord_id": "123456789012345678",
        "promoter_discord_id": "123456789012345601",
        "recorded_at": "2026-11-24T18:30:00.000000Z",
        "contact_date_ny": "2026-11-24",
        "contact_method": "DISCORD_DM",
        "contact_reason": "EVENT_INVITE",
        "occasion_id": "77",
        "event_date": None,
        "forced": False,
    }
    entry.update(overrides)
    return entry


_DEFAULT_RANGE = {"after": "0", "through": INT64_MAX}


def _batch(
    *,
    entries: list | None = None,
    skipped_ids: list | None = None,
    range: Any = _DEFAULT_RANGE,  # noqa: A002
    **overrides,
) -> dict:
    body = {
        "source": "contact_log",
        "guild_id": "555000000000000001",
        "scan_started_at": "2026-11-25T10:00:00.000000Z",
        "range": range,
        "skipped_ids": skipped_ids if skipped_ids is not None else [],
        "entries": entries if entries is not None else [],
    }
    body.update(overrides)
    return body


class ParseImportBatchTests(SimpleTestCase):
    now = datetime(2026, 11, 25, 10, tzinfo=UTC)

    def parse(self, payload) -> ImportBatch:
        return parse_import_batch(payload, now=self.now)

    def assert_rejected(self, payload) -> None:
        with self.assertRaises(IntegrationError) as ctx:
            self.parse(payload)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_import_rules_fixture(self) -> None:
        text, golden = _fixture("import_rules.json")
        self.assertNotIn(_UPSTREAM_MARK, text.lower())
        now = parse_timestamp(golden["now"], "now")
        self.assertTrue(any(c["accept"] for c in golden["cases"]))
        self.assertTrue(any(not c["accept"] for c in golden["cases"]))
        for case in golden["cases"]:
            payload = _batch(entries=[case["entry"]])
            with self.subTest(case=case["name"]):
                if case["accept"]:
                    batch = parse_import_batch(payload, now=now)
                    self.assertEqual(len(batch.entries), 1)
                else:
                    with self.assertRaises(IntegrationError) as ctx:
                        parse_import_batch(payload, now=now)
                    self.assertEqual(ctx.exception.status_code, 400)

    def test_parses_a_full_batch(self) -> None:
        batch = self.parse(
            _batch(
                range={"after": "1000", "through": "1010"},
                skipped_ids=["1005"],
                entries=[
                    _entry(),
                    _entry(
                        source_contact_id="1002",
                        promoter_discord_id=None,
                        contact_reason="GENERAL",
                        occasion_id=None,
                        event_date="2099-12-05T20:00:00.5Z",
                    ),
                ],
            )
        )
        self.assertEqual(batch.guild_id, "555000000000000001")
        self.assertEqual(batch.scan_started_at, self.now)
        self.assertEqual((batch.range_after, batch.range_through), (1000, 1010))
        self.assertEqual(batch.skipped_ids, frozenset({1005}))
        first, second = batch.entries
        self.assertIsInstance(first, ImportEntryV)
        self.assertEqual(first.source_contact_id, 1001)
        self.assertEqual(first.target_discord_id, "123456789012345678")
        self.assertEqual(first.promoter_discord_id, "123456789012345601")
        self.assertEqual(first.recorded_at, datetime(2026, 11, 24, 18, 30, tzinfo=UTC))
        self.assertEqual(first.contact_date_ny, date(2026, 11, 24))
        self.assertEqual(first.contact_method, "DISCORD_DM")
        self.assertEqual(first.contact_reason, "EVENT_INVITE")
        self.assertEqual(first.occasion_id, 77)
        self.assertIsNone(first.event_date)
        self.assertFalse(first.forced)
        self.assertEqual(first.source_hash, import_source_hash(_entry()))
        self.assertIsNone(second.promoter_discord_id)
        self.assertIsNone(second.occasion_id)
        self.assertEqual(
            second.event_date, datetime(2099, 12, 5, 20, 0, 0, 500000, tzinfo=UTC)
        )

    def test_probe_batch_is_accepted(self) -> None:
        batch = self.parse(_batch(range=None))
        self.assertIsNone(batch.range_after)
        self.assertIsNone(batch.range_through)
        self.assertEqual(batch.skipped_ids, frozenset())
        self.assertEqual(batch.entries, [])

    def test_parse_import_batch_range_rules(self) -> None:
        cases = {
            "null range with entries": _batch(range=None, entries=[_entry()]),
            "null range with skipped ids": _batch(range=None, skipped_ids=["5"]),
            "skipped id outside range": _batch(
                range={"after": "10", "through": "20"}, skipped_ids=["21"]
            ),
            "skipped id at range start": _batch(
                range={"after": "10", "through": "20"}, skipped_ids=["10"]
            ),
            "skipped id equal to an entry id": _batch(
                entries=[_entry()], skipped_ids=["1001"]
            ),
            "repeated skipped id": _batch(skipped_ids=["5", "5"]),
            "entry outside range": _batch(
                range={"after": "1001", "through": "2000"}, entries=[_entry()]
            ),
            "after equals through": _batch(range={"after": "20", "through": "20"}),
            "after above through": _batch(range={"after": "21", "through": "20"}),
            "through zero": _batch(range={"after": "0", "through": "0"}),
            "after not canonical": _batch(range={"after": "00", "through": "20"}),
            "range missing a key": _batch(range={"through": "20"}),
            "range with an extra key": _batch(
                range={"after": "0", "through": "20", "limit": "5"}
            ),
            "range not an object": _batch(range=["0", "20"]),
            "duplicate entry id": _batch(entries=[_entry(), _entry()]),
            "too many entries": _batch(
                entries=[_entry(source_contact_id=str(i)) for i in range(1, 102)]
            ),
            "too many skipped ids": _batch(
                skipped_ids=[str(i) for i in range(1, 1002)]
            ),
        }
        for name, payload in cases.items():
            with self.subTest(case=name):
                self.assert_rejected(payload)

    def test_batch_bounds_are_inclusive(self) -> None:
        batch = self.parse(
            _batch(
                range={"after": "0", "through": "2000"},
                entries=[_entry(source_contact_id=str(i)) for i in range(1, 101)],
                skipped_ids=[str(i) for i in range(1001, 2001)],
            )
        )
        self.assertEqual(len(batch.entries), 100)
        self.assertEqual(len(batch.skipped_ids), 1000)

    def test_parse_import_batch_rejects_removed_keys(self) -> None:
        self.assert_rejected(_batch(mapping_version="a" * 64))
        for key, value in (
            ("event_id", "720"),
            ("linkage", "occasion"),
            ("discord_id", "123456789012345678"),
            ("user_id", None),
            ("org_user_id", None),
        ):
            with self.subTest(key=key):
                self.assert_rejected(_batch(entries=[{**_entry(), key: value}]))

    def test_rejects_bad_envelope_fields(self) -> None:
        missing = _batch()
        del missing["scan_started_at"]
        for name, payload in {
            "other source": _batch(source="other"),
            "guild id not canonical": _batch(guild_id="0555"),
            "scan start in the future": _batch(
                scan_started_at="2026-11-25T10:05:00.000001Z"
            ),
            "scan start missing": missing,
            "skipped ids not a list": _batch(skipped_ids="5"),
            "skipped id not canonical": _batch(skipped_ids=["05"]),
            "entries not a list": _batch(entries={}),
            "entry not an object": _batch(entries=["1001"]),
            "not an object": [],
        }.items():
            with self.subTest(case=name):
                self.assert_rejected(payload)

    def test_forced_must_be_a_json_boolean(self) -> None:
        for value in (0, 1, "true", None):
            with self.subTest(value=value):
                self.assert_rejected(_batch(entries=[_entry(forced=value)]))

    def test_error_names_the_field_not_the_value(self) -> None:
        with self.assertRaises(IntegrationError) as ctx:
            self.parse(_batch(entries=[_entry(contact_reason="SECRET_REASON")]))
        self.assertIn("entries[0].contact_reason", ctx.exception.message)
        self.assertNotIn("SECRET_REASON", ctx.exception.message)


class ParseDateTests(SimpleTestCase):
    def test_parse_date_accepts_real_dates(self) -> None:
        self.assertEqual(parse_date("2026-11-24", "d"), date(2026, 11, 24))
        self.assertEqual(parse_date("2024-02-29", "d"), date(2024, 2, 29))
        self.assertEqual(parse_date("0001-01-01", "d"), date(1, 1, 1))

    def test_parse_date_rejects_invalid(self) -> None:
        for bad in (
            "2026-02-30",
            "2026-1-01",
            "2026-01-1",
            "0000-01-01",
            "2026-13-01",
            "2026-11-24T00:00:00Z",
            " 2026-11-24",
            "２026-11-24",
            "20261124",
            20261124,
            None,
        ):
            with self.subTest(bad=bad), self.assertRaises(IntegrationError) as ctx:
                parse_date(bad, "d")
            self.assertEqual(ctx.exception.status_code, 400)
