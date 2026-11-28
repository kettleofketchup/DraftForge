import ast
import uuid
from datetime import timedelta
from typing import Any
from unittest import mock

from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from structlog.testing import capture_logs

import app.internal_client as internal_client
from app.models import CustomUser
from events.constants import ActorRole, SignupAction, SignupMeans
from events.ledger import event_snapshot, purge_expired
from events.models import SignupLedgerEntry
from events.tasks import purge_expired_signup_records
from events.tests.base import EventTestCase
from lobby.tests.test_beat_schedule import CONFIG, beat_schedule
from org.models import OrgSettings

TOKEN = "test-internal-token"
BEAT_KEY = "purge-signup-records-nightly"
TASK_NAME = "events.tasks.purge_expired_signup_records"
RESULT_KEYS = {
    "purged",
    "organizations",
    "events",
    "skipped_unknown_end",
    "per_org",
    "more",
    "resume_org_id",
}


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class InternalPurgeEndpointTest(EventTestCase):
    def setUp(self) -> None:
        self.url = reverse("internal_signup_records_purge")
        OrgSettings.objects.update_or_create(
            organization=self.org, defaults={"signup_record_retention_days": 30}
        )
        ended = timezone.now() - timedelta(days=60)
        event = self.make_event(scheduled_at=ended - timedelta(hours=2), ends_at=ended)
        SignupLedgerEntry.objects.create(
            event_id=event.pk,
            organization_id=self.org.pk,
            event_snapshot=event_snapshot(event),
            subject_user=self.user,
            subject_snapshot={"user_id": self.user.pk},
            actor_role=ActorRole.SYSTEM,
            means=SignupMeans.SYSTEM,
            action=SignupAction.SIGNED_UP,
            correlation_id=uuid.uuid4().hex,
        )

    def post(self, **headers: str) -> HttpResponse:
        return self.client.post(
            self.url, "{}", content_type="application/json", **headers
        )

    def test_no_token_rejected(self) -> None:
        self.assertIn(self.post().status_code, (401, 403))
        self.assertEqual(SignupLedgerEntry.objects.count(), 1)

    def test_bad_token_rejected(self) -> None:
        self.assertIn(self.post(HTTP_X_INTERNAL_TOKEN="wrong").status_code, (401, 403))
        self.assertEqual(SignupLedgerEntry.objects.count(), 1)

    def test_session_site_staff_without_token_forbidden(self) -> None:
        staff = CustomUser.objects.create_user(
            username="purge_site_staff", password="x", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        self.assertEqual(self.post().status_code, 403)
        self.assertEqual(SignupLedgerEntry.objects.count(), 1)

    def test_valid_token_purges_and_reports(self) -> None:
        resp = self.post(HTTP_X_INTERNAL_TOKEN=TOKEN)
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(set(body), RESULT_KEYS)
        self.assertEqual(body["purged"], 1)
        self.assertEqual(body["per_org"], {str(self.org.pk): 1})
        self.assertFalse(body["more"])
        self.assertIsNone(body["resume_org_id"])
        self.assertEqual(SignupLedgerEntry.objects.count(), 0)

    def test_resume_org_id_passed_through(self) -> None:
        with mock.patch(
            "events.views_records.purge_expired", wraps=purge_expired
        ) as spy:
            resp = self.client.post(
                self.url,
                {"resume_org_id": self.org.pk},
                content_type="application/json",
                HTTP_X_INTERNAL_TOKEN=TOKEN,
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        spy.assert_called_once_with(resume_org_id=self.org.pk)

    def test_invalid_resume_org_id_rejected(self) -> None:
        for bad in ("x", 0, True, 2**63):
            with self.subTest(bad=bad):
                resp = self.client.post(
                    self.url,
                    {"resume_org_id": bad},
                    content_type="application/json",
                    HTTP_X_INTERNAL_TOKEN=TOKEN,
                )
                self.assertEqual(resp.status_code, 400, resp.content)
                self.assertIn("resume_org_id", resp.json())
        self.assertEqual(SignupLedgerEntry.objects.count(), 1)


class PurgeClientTest(SimpleTestCase):
    def test_returns_json_body(self) -> None:
        response = mock.Mock(ok=True)
        response.json.return_value = {"purged": 0, "more": False}
        with mock.patch.object(
            internal_client.transport, "post", return_value=response
        ) as post:
            result = internal_client.purge_signup_records()
        post.assert_called_once_with("/signup-records/purge/", {})
        self.assertEqual(result, {"purged": 0, "more": False})

    def test_sends_resume_org_id(self) -> None:
        response = mock.Mock(ok=True)
        response.json.return_value = {"purged": 0, "more": False}
        with mock.patch.object(
            internal_client.transport, "post", return_value=response
        ) as post:
            internal_client.purge_signup_records(resume_org_id=7)
        post.assert_called_once_with("/signup-records/purge/", {"resume_org_id": 7})

    def test_transport_failure_returns_none(self) -> None:
        with mock.patch.object(internal_client.transport, "post", return_value=None):
            self.assertIsNone(internal_client.purge_signup_records())

    def test_not_ok_returns_none(self) -> None:
        with mock.patch.object(
            internal_client.transport, "post", return_value=mock.Mock(ok=False)
        ):
            self.assertIsNone(internal_client.purge_signup_records())

    def test_invalid_json_returns_none_and_logs(self) -> None:
        response = mock.Mock(ok=True)
        response.json.side_effect = ValueError("bad json")
        with (
            mock.patch.object(internal_client.transport, "post", return_value=response),
            mock.patch.object(internal_client.transport, "log") as log,
        ):
            self.assertIsNone(internal_client.purge_signup_records())
        self.assertEqual(
            log.error.call_args.args[0], "signup_records_purge_invalid_json"
        )


class PurgeTaskTest(SimpleTestCase):
    def run_task(self, side_effect: Any) -> tuple[mock.Mock, list[dict[str, Any]]]:
        with (
            mock.patch(
                "events.tasks.purge_signup_records", side_effect=side_effect
            ) as call,
            capture_logs() as logs,
        ):
            purge_expired_signup_records()
        return call, logs

    def events_named(self, logs: list[dict[str, Any]], name: str) -> list[dict]:
        return [line for line in logs if line["event"] == name]

    def test_loops_while_more(self) -> None:
        call, logs = self.run_task([{"more": True}, {"more": False}])
        self.assertEqual(call.call_count, 2)
        self.assertEqual(self.events_named(logs, "signup_records_purge_incomplete"), [])
        self.assertEqual(self.events_named(logs, "signup_records_purge_failed"), [])

    def test_threads_resume_org_id(self) -> None:
        call, _ = self.run_task(
            [
                {"more": True, "resume_org_id": 5},
                {"more": True, "resume_org_id": 9},
                {"more": False, "resume_org_id": None},
            ]
        )
        self.assertEqual(
            [c.kwargs for c in call.call_args_list],
            [{"resume_org_id": None}, {"resume_org_id": 5}, {"resume_org_id": 9}],
        )

    def test_stops_at_max_calls(self) -> None:
        call, logs = self.run_task(lambda **_: {"more": True})
        self.assertEqual(call.call_count, 12)
        lines = self.events_named(logs, "signup_records_purge_incomplete")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["system"], "events")
        self.assertEqual(lines[0]["subsystem"], "ledger")

    @override_settings(SIGNUP_RECORDS_PURGE_MAX_CALLS=3)
    def test_max_calls_setting_respected(self) -> None:
        call, logs = self.run_task(lambda **_: {"more": True})
        self.assertEqual(call.call_count, 3)
        self.assertEqual(
            len(self.events_named(logs, "signup_records_purge_incomplete")), 1
        )

    def test_failure_logs_warning_and_stops(self) -> None:
        call, logs = self.run_task([None, {"more": False}])
        self.assertEqual(call.call_count, 1)
        lines = self.events_named(logs, "signup_records_purge_failed")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["log_level"], "warning")
        self.assertEqual(lines[0]["system"], "events")
        self.assertEqual(lines[0]["subsystem"], "ledger")

    def test_failure_after_progress_stops(self) -> None:
        call, logs = self.run_task([{"more": True}, None, {"more": False}])
        self.assertEqual(call.call_count, 2)
        self.assertEqual(len(self.events_named(logs, "signup_records_purge_failed")), 1)

    def test_task_name(self) -> None:
        self.assertEqual(purge_expired_signup_records.name, TASK_NAME)


def crontab_kwargs(filename: str, key: str) -> dict[str, Any]:
    tree = ast.parse((CONFIG / filename).read_text())
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_beat_schedule"
        ):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and k.value == key:
                    for ek, ev in zip(v.keys, v.values):
                        if ek.value == "schedule" and isinstance(ev, ast.Call):
                            return {
                                kw.arg: kw.value.value
                                for kw in ev.keywords
                                if isinstance(kw.value, ast.Constant)
                            }
    raise AssertionError(f"no crontab schedule for {key} in {filename}")


class BeatTest(SimpleTestCase):
    def test_nightly_entry_in_both_schedules(self) -> None:
        for filename in ("celery.py", "celery_light.py"):
            with self.subTest(filename=filename):
                self.assertEqual(beat_schedule(filename)[BEAT_KEY]["task"], TASK_NAME)
                self.assertEqual(
                    crontab_kwargs(filename, BEAT_KEY), {"hour": 4, "minute": 30}
                )
