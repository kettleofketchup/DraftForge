from datetime import UTC, datetime, time
from enum import Enum
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import requests
from django.db import OperationalError
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pydantic import BaseModel
from rest_framework.response import Response
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.internal_client import (
    OpsNoticeTransientError,
    emit_ops_notice,
    resolve_ops_notice,
)
from events.models import Event, EventRepeater
from events.tests.base import EventTestCase
from opsnotices.models import OpsNotice
from opsnotices.registry import isolated_registry
from opsnotices.services import NoticeEmitError
from opsnotices.tests.types import register_test_types
from org.models import Organization

TOKEN = "test-internal-token"
HEADERS: dict[str, str] = {"HTTP_X_INTERNAL_TOKEN": TOKEN}


def _alert(member_id: int = 1, reason: str = "late") -> dict[str, Any]:
    return {"member_id": member_id, "reason": reason}


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class InternalEndpointTests(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enterContext(isolated_registry())
        register_test_types()
        self.client = APIClient()
        self.emit_url = reverse("internal_ops_notice_emit")
        self.resolve_url = reverse("internal_ops_notice_resolve")

    def _body(self, **overrides: Any) -> dict[str, Any]:
        return {
            "key": "test.alert",
            "payload": _alert(),
            "organization_id": self.org.id,
            **overrides,
        }

    def _post(self, url: str, data: Any) -> Response:
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, data, format="json", **HEADERS)

    def test_urls_mounted(self) -> None:
        self.assertEqual(self.emit_url, "/api/internal/ops-notices/")
        self.assertEqual(self.resolve_url, "/api/internal/ops-notices/resolve/")

    def test_requires_internal_token(self) -> None:
        for url in (self.emit_url, self.resolve_url):
            with self.subTest(url=url):
                resp = self.client.post(url, self._body(), format="json")
                self.assertEqual(resp.status_code, 403)
        self.assertEqual(OpsNotice.objects.count(), 0)

    def test_create_201_repeat_200_replay_200(self) -> None:
        emit_id = str(uuid4())
        first = self._post(self.emit_url, self._body(emit_id=emit_id))
        self.assertEqual(first.status_code, 201)
        notice_id = first.json()["id"]
        self.assertEqual(
            first.json(), {"id": notice_id, "created": True, "occurrences": 1}
        )

        replay = self._post(self.emit_url, self._body(emit_id=emit_id))
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(
            replay.json(), {"id": notice_id, "created": False, "occurrences": 1}
        )

        repeat = self._post(self.emit_url, self._body(emit_id=str(uuid4())))
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(
            repeat.json(), {"id": notice_id, "created": False, "occurrences": 2}
        )

        # Replay only matches the latest emit on a row: a retry that lands after
        # another emit counts again.
        late_retry = self._post(self.emit_url, self._body(emit_id=emit_id))
        self.assertEqual(
            late_retry.json(), {"id": notice_id, "created": False, "occurrences": 3}
        )

    def test_emit_with_event_and_users(self) -> None:
        resp = self._post(
            self.emit_url,
            self._body(
                event_id=self.event.id,
                subject_user_id=self.user.id,
                actor_id=self.admin.id,
                severity="critical",
            ),
        )
        self.assertEqual(resp.status_code, 201)
        notice = OpsNotice.objects.get(pk=resp.json()["id"])
        self.assertEqual(notice.event_id, self.event.id)
        self.assertEqual(notice.event_name, self.event.name)
        self.assertEqual(notice.subject_user_id, self.user.id)
        self.assertEqual(notice.actor_id, self.admin.id)
        self.assertEqual(notice.severity, "critical")

    def test_existing_event_repeater_wins_over_body(self) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency="weekly",
            time_of_day=time(19, 0),
            starts_at=timezone.now().date(),
        )
        Event.objects.filter(pk=self.event.pk).update(event_repeater=repeater)
        resp = self._post(
            self.emit_url,
            self._body(event_id=self.event.id, event_repeater_id=repeater.id + 1000),
        )
        self.assertEqual(resp.status_code, 201)
        notice = OpsNotice.objects.get(pk=resp.json()["id"])
        self.assertEqual(notice.event_repeater_id, repeater.id)

    def test_rejections_return_400_with_code(self) -> None:
        cases: list[tuple[dict[str, Any], str]] = [
            (self._body(key="test.missing"), "unknown_notice_type"),
            (self._body(payload={"member_id": "x"}), "invalid_payload"),
            (self._body(severity="loud"), "invalid_severity"),
        ]
        for body, code in cases:
            with self.subTest(code=code), capture_logs() as logs:
                resp = self._post(self.emit_url, body)
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(resp.json()["code"], code)
                self.assertIn("error", resp.json())
                rejected = [
                    e for e in logs if e["event"] == "ops_notice_internal_rejected"
                ]
                self.assertEqual(len(rejected), 1)
                self.assertEqual(rejected[0]["code"], code)
                self.assertEqual(rejected[0]["subsystem"], "api")
        self.assertEqual(OpsNotice.objects.count(), 0)

    def test_transient_failures_return_503_with_code(self) -> None:
        cases: list[tuple[str, BaseException]] = [
            ("database_error", OperationalError("database is locked")),
            ("event_conflict", NoticeEmitError("event_conflict", "test.alert")),
        ]
        for code, error in cases:
            with (
                self.subTest(code=code),
                patch("opsnotices.services._write", side_effect=error),
                capture_logs() as logs,
            ):
                resp = self._post(self.emit_url, self._body(emit_id=str(uuid4())))
                self.assertEqual(resp.status_code, 503)
                self.assertEqual(resp.json()["code"], code)
                rejected = [
                    e for e in logs if e["event"] == "ops_notice_internal_rejected"
                ]
                self.assertEqual(rejected[0]["log_level"], "error")
        self.assertEqual(OpsNotice.objects.count(), 0)

    def test_event_of_other_org_rejected(self) -> None:
        other = Organization.objects.create(name="Other Org", owner=self.admin)
        resp = self._post(
            self.emit_url, self._body(organization_id=other.id, event_id=self.event.id)
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "event_org_mismatch")

    def test_unknown_org_404(self) -> None:
        resp = self._post(self.emit_url, self._body(organization_id=999_999))
        self.assertEqual(resp.status_code, 404)
        resolve = self._post(
            self.resolve_url,
            {
                "key": "test.alert",
                "dedupe_key": "member:1",
                "organization_id": 999_999,
                "reason": "fixed",
            },
        )
        self.assertEqual(resolve.status_code, 404)
        self.assertEqual(OpsNotice.objects.count(), 0)

    def test_unknown_event_keeps_snapshot(self) -> None:
        resp = self._post(
            self.emit_url,
            self._body(event_id=987_654, event_name="Gone Event", event_repeater_id=42),
        )
        self.assertEqual(resp.status_code, 201)
        notice = OpsNotice.objects.get(pk=resp.json()["id"])
        self.assertIsNone(notice.event_id)
        self.assertEqual(notice.event_key, 987_654)
        self.assertEqual(notice.event_name, "Gone Event")
        self.assertEqual(notice.event_repeater_id, 42)

    def test_unknown_actor_nulled_and_warned(self) -> None:
        with capture_logs() as logs:
            resp = self._post(
                self.emit_url, self._body(actor_id=999_999, subject_user_id=999_998)
            )
        self.assertEqual(resp.status_code, 201)
        notice = OpsNotice.objects.get(pk=resp.json()["id"])
        self.assertIsNone(notice.actor_id)
        self.assertIsNone(notice.subject_user_id)
        missing = [e for e in logs if e["event"] == "ops_notice_internal_user_missing"]
        self.assertEqual(
            sorted((e["field"], e["user_id"]) for e in missing),
            [("actor_id", 999_999), ("subject_user_id", 999_998)],
        )
        self.assertTrue(all(e["log_level"] == "warning" for e in missing))

    def test_resolve_200_true_and_false(self) -> None:
        created = self._post(self.emit_url, self._body())
        notice_id = created.json()["id"]
        body = {
            "key": "test.alert",
            "dedupe_key": "member:1",
            "organization_id": self.org.id,
            "reason": "fixed",
        }
        resp = self._post(self.resolve_url, body)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"id": notice_id, "resolved": True})
        notice = OpsNotice.objects.get(pk=notice_id)
        self.assertEqual(notice.state, OpsNotice.State.RESOLVED)
        self.assertEqual(notice.close_note, "fixed")

        again = self._post(self.resolve_url, body)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json(), {"id": None, "resolved": False})

    def test_resolve_scoped_by_event(self) -> None:
        created = self._post(self.emit_url, self._body(event_id=self.event.id))
        body = {
            "key": "test.alert",
            "dedupe_key": "member:1",
            "organization_id": self.org.id,
            "reason": "fixed",
        }
        self.assertFalse(self._post(self.resolve_url, body).json()["resolved"])
        resp = self._post(self.resolve_url, {**body, "event_id": self.event.id})
        self.assertEqual(resp.json(), {"id": created.json()["id"], "resolved": True})

    def test_resolve_empty_dedupe_400_invalid_request(self) -> None:
        base = {
            "key": "test.alert",
            "dedupe_key": "member:1",
            "organization_id": self.org.id,
            "reason": "fixed",
        }
        for override in ({"dedupe_key": ""}, {"reason": ""}, {"reason": "x" * 201}):
            with self.subTest(override=override):
                resp = self._post(self.resolve_url, {**base, **override})
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(
                    resp.json(), {"error": "invalid request", "code": "invalid_request"}
                )

    def test_malformed_bodies_return_400_invalid_request(self) -> None:
        emit_cases: list[tuple[str, Any]] = [
            ("payload list", self._body(payload=[1, 2])),
            ("payload string", self._body(payload="oops")),
            ("org id string", self._body(organization_id="abc")),
            ("emit id not uuid", self._body(emit_id="nope")),
            ("missing key", {"payload": _alert(), "organization_id": self.org.id}),
            ("extra field", self._body(surprise=True)),
            ("body is a list", [self._body()]),
            ("org id bool", self._body(organization_id=True)),
            ("event id zero", self._body(event_id=0)),
        ]
        resolve_cases: list[tuple[str, Any]] = [
            ("resolve missing reason", {"key": "test.alert", "dedupe_key": "a"}),
            (
                "resolve extra field",
                {
                    "key": "test.alert",
                    "dedupe_key": "a",
                    "organization_id": self.org.id,
                    "reason": "x",
                    "payload": {},
                },
            ),
            ("resolve body string", "nope"),
        ]
        cases = [(self.emit_url, *c) for c in emit_cases] + [
            (self.resolve_url, *c) for c in resolve_cases
        ]
        for url, label, body in cases:
            with self.subTest(label):
                resp = self._post(url, body)
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(
                    resp.json(), {"error": "invalid request", "code": "invalid_request"}
                )
        self.assertEqual(OpsNotice.objects.count(), 0)

    def test_invalid_json_returns_400_invalid_request(self) -> None:
        resp = self.client.post(
            self.emit_url, "{not json", content_type="application/json", **HEADERS
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "invalid_request")


def _response(status_code: int, body: Any = None) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.text = ""
    resp.json.return_value = body
    return resp


POST_TARGET = "app.internal_client.transport.requests.post"


class InternalClientTests(SimpleTestCase):
    def test_emit_ops_notice_returns_id_on_2xx(self) -> None:
        emit_id = uuid4()
        with patch(
            POST_TARGET,
            return_value=_response(201, {"id": 7, "created": True, "occurrences": 1}),
        ) as post:
            result = emit_ops_notice(
                "test.alert",
                {"member_id": 1, "reason": "late"},
                organization_id=3,
                event_id=5,
                event_repeater_id=9,
                emit_id=emit_id,
            )
        self.assertEqual(result, 7)
        url = post.call_args.args[0]
        self.assertTrue(url.endswith("/ops-notices/"))
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["key"], "test.alert")
        self.assertEqual(body["payload"], {"member_id": 1, "reason": "late"})
        self.assertEqual(body["organization_id"], 3)
        self.assertEqual(body["event_id"], 5)
        self.assertEqual(body["event_repeater_id"], 9)
        self.assertEqual(body["emit_id"], str(emit_id))
        self.assertNotIn("actor_id", body)

    def test_emit_ops_notice_none_on_400(self) -> None:
        with patch(POST_TARGET, return_value=_response(400, {"code": "x"})):
            self.assertIsNone(emit_ops_notice("test.alert", {}, organization_id=1))
        with patch(POST_TARGET, return_value=_response(404, {})):
            self.assertIsNone(emit_ops_notice("test.alert", {}, organization_id=1))

    def test_emit_ops_notice_raises_transient_on_5xx(self) -> None:
        with patch(POST_TARGET, return_value=_response(503)):
            with self.assertRaises(OpsNoticeTransientError):
                emit_ops_notice("test.alert", {}, organization_id=1)

    def test_emit_ops_notice_raises_transient_on_503_database_error(self) -> None:
        with patch(
            POST_TARGET, return_value=_response(503, {"code": "database_error"})
        ):
            with self.assertRaises(OpsNoticeTransientError):
                emit_ops_notice("test.alert", {}, organization_id=1)

    def test_emit_ops_notice_sends_json_native_payload(self) -> None:
        class Colour(Enum):
            RED = "red"

        class Payload(BaseModel):
            at: datetime
            ref: UUID
            colour: Colour

        at = datetime(2026, 11, 17, 18, 0, tzinfo=UTC)
        ref = uuid4()
        expected = {"at": "2026-11-17T18:00:00Z", "ref": str(ref), "colour": "red"}
        payloads: list[Any] = [
            Payload(at=at, ref=ref, colour=Colour.RED),
            {"at": at, "ref": ref, "colour": Colour.RED},
        ]
        for payload in payloads:
            with (
                self.subTest(type=type(payload).__name__),
                patch(POST_TARGET, return_value=_response(201, {"id": 1})) as post,
            ):
                self.assertEqual(
                    emit_ops_notice("test.alert", payload, organization_id=1), 1
                )
                self.assertEqual(post.call_args.kwargs["json"]["payload"], expected)

    def test_invalid_json_logged_with_internal_api_tags(self) -> None:
        resp = _response(200)
        resp.json.side_effect = ValueError("bad")
        with patch(POST_TARGET, return_value=resp), capture_logs() as logs:
            self.assertIsNone(emit_ops_notice("test.alert", {}, organization_id=1))
        invalid = [e for e in logs if e["event"] == "ops_notice_invalid_json"]
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0]["tags"], ["internal_api", "outbound"])
        self.assertEqual(invalid[0]["system"], "internal_client")

    def test_emit_ops_notice_raises_transient_on_connection_error(self) -> None:
        with patch(POST_TARGET, side_effect=requests.ConnectionError("down")):
            with self.assertRaises(OpsNoticeTransientError):
                emit_ops_notice("test.alert", {}, organization_id=1)

    def test_resolve_ops_notice_returns_resolved_on_2xx(self) -> None:
        with patch(
            POST_TARGET, return_value=_response(200, {"id": 4, "resolved": True})
        ) as post:
            self.assertTrue(
                resolve_ops_notice(
                    "test.alert", "member:1", organization_id=3, reason="fixed"
                )
            )
        self.assertTrue(post.call_args.args[0].endswith("/ops-notices/resolve/"))
        self.assertEqual(
            post.call_args.kwargs["json"],
            {
                "key": "test.alert",
                "dedupe_key": "member:1",
                "organization_id": 3,
                "reason": "fixed",
            },
        )
        with patch(
            POST_TARGET, return_value=_response(200, {"id": None, "resolved": False})
        ):
            self.assertFalse(
                resolve_ops_notice(
                    "test.alert", "member:1", organization_id=3, reason="fixed"
                )
            )

    def test_resolve_ops_notice_false_on_400(self) -> None:
        with patch(POST_TARGET, return_value=_response(400, {})):
            self.assertFalse(
                resolve_ops_notice("test.alert", "", organization_id=1, reason="x")
            )

    def test_resolve_ops_notice_raises_transient_on_5xx(self) -> None:
        with patch(POST_TARGET, return_value=_response(500)):
            with self.assertRaises(OpsNoticeTransientError):
                resolve_ops_notice("test.alert", "a", organization_id=1, reason="x")

    def test_resolve_ops_notice_raises_transient_on_connection_error(self) -> None:
        with patch(POST_TARGET, side_effect=requests.Timeout("slow")):
            with self.assertRaises(OpsNoticeTransientError):
                resolve_ops_notice("test.alert", "a", organization_id=1, reason="x")
