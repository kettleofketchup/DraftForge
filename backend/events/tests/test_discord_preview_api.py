"""HTTP contract of POST /api/events/discord-preview/."""

import subprocess
import sys
from datetime import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

from django.test import Client
from django.urls import resolve
from rest_framework.test import APIClient

from app.models import CustomUser
from discordbot.models import DiscordMessageLog
from events.constants import RepeatFrequency
from events.discord.preview_schema import DiscordPreviewResponse
from events.models import Event, EventRepeater
from events.tests.base import EventTestCase
from org.models import Organization

URL = "/api/events/discord-preview/"
BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent


class DiscordPreviewApiTest(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Series",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=self.event.scheduled_at.date(),
            created_by=self.admin,
        )
        self.other_org_owner = CustomUser.objects.create_user(
            username="preview_other_owner", password="testpass"
        )
        self.other_org = Organization.objects.create(
            name="Other Org", owner=self.other_org_owner
        )
        self.other_staff = CustomUser.objects.create_user(
            username="preview_other_staff", password="testpass"
        )
        self.other_org.staff.add(self.other_staff)
        self.other_event = Event.objects.create(
            organization=self.other_org,
            name="Other Event",
            scheduled_at=self.event.scheduled_at,
            created_by=self.other_org_owner,
        )
        self.other_repeater = EventRepeater.objects.create(
            organization=self.other_org,
            name="Other Series",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=self.event.scheduled_at.date(),
            created_by=self.other_org_owner,
        )
        self.member = self.make_user()
        self.org_staff = CustomUser.objects.create_user(
            username="preview_org_staff", password="testpass"
        )
        self.org.staff.add(self.org_staff)
        self.org_admin = CustomUser.objects.create_user(
            username="preview_org_admin", password="testpass"
        )
        self.org.admins.add(self.org_admin)
        self.superuser = CustomUser.objects.create_superuser(
            username="preview_superuser", password="testpass"
        )

    def _contexts(self, org: Organization | None = None) -> dict[str, dict[str, Any]]:
        own = org is None
        org = org or self.org
        event = self.event if own else self.other_event
        repeater = self.repeater if own else self.other_repeater
        return {
            "event": {"type": "event", "event_id": event.pk},
            "new_event": {"type": "new_event", "organization_id": org.pk},
            "series_one_off": {"type": "series_one_off", "repeater_id": repeater.pk},
            "repeater": {"type": "repeater", "repeater_id": repeater.pk},
            "new_repeater": {"type": "new_repeater", "organization_id": org.pk},
            "org_defaults": {"type": "org_defaults", "organization_id": org.pk},
        }

    def _post(
        self, user: CustomUser | None, body: dict[str, Any], client: Any = None
    ) -> Any:
        client = client or APIClient()
        if user is not None:
            client.force_login(user)
        return client.post(URL, body, format="json")

    def _body(self, context: dict[str, Any], **extra: Any) -> dict[str, Any]:
        return {"kind": "signup_post", "context": context, "values": {}, **extra}

    def _assert_error_body(self, response: Any) -> dict[str, Any]:
        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"])
        return body

    def test_url_resolves_to_preview_not_detail(self) -> None:
        match = resolve(URL)
        self.assertEqual(match.func.actions, {"post": "discord_preview"})

    def test_denied_callers_get_403_in_every_context(self) -> None:
        denied: dict[str, CustomUser | None] = {
            "anonymous": None,
            "non_member": self.unrelated_user,
            "member": self.member,
            "league_staff": self.league_staff,
            "other_org_staff": self.other_staff,
        }
        for who, user in denied.items():
            for name, context in self._contexts().items():
                with self.subTest(who=who, context=name):
                    response = self._post(user, self._body(context))
                    self.assertEqual(response.status_code, 403, response.content)
                    if user is not None:
                        self.assertTrue(response.json().get("error"), response.content)

    def test_own_staff_denied_on_other_org_ids(self) -> None:
        for name, context in self._contexts(self.other_org).items():
            with self.subTest(context=name):
                response = self._post(self.org_staff, self._body(context))
                self.assertEqual(response.status_code, 403, response.content)
                self.assertTrue(response.json().get("error"), response.content)

    def test_allowed_callers_get_200_in_every_context(self) -> None:
        allowed = {
            "owner": self.admin,
            "admin": self.org_admin,
            "staff": self.org_staff,
            "superuser": self.superuser,
        }
        logs_before = DiscordMessageLog.objects.count()
        for who, user in allowed.items():
            for name, context in self._contexts().items():
                with self.subTest(who=who, context=name):
                    response = self._post(user, self._body(context))
                    self.assertEqual(response.status_code, 200, response.content)
                    parsed = DiscordPreviewResponse.model_validate(response.json())
                    self.assertEqual(parsed.kind, "signup_post")
        self.assertEqual(DiscordMessageLog.objects.count(), logs_before)

    def test_response_includes_every_field(self) -> None:
        context = self._contexts()["event"]
        response = self._post(self.admin, self._body(context))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(set(response.json()), set(DiscordPreviewResponse.model_fields))

    def test_missing_event_and_repeater_404(self) -> None:
        missing = {
            "event": {"type": "event", "event_id": 999999},
            "series_one_off": {"type": "series_one_off", "repeater_id": 999999},
            "repeater": {"type": "repeater", "repeater_id": 999999},
        }
        for name, context in missing.items():
            with self.subTest(context=name):
                response = self._post(self.admin, self._body(context))
                self.assertEqual(response.status_code, 404, response.content)
                self.assertTrue(response.json().get("error"), response.content)

    def test_csrf_enforced(self) -> None:
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(
            URL,
            self._body(self._contexts()["event"]),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn("CSRF", response.json()["detail"])

    def test_get_not_allowed(self) -> None:
        client = APIClient()
        client.force_login(self.admin)
        self.assertEqual(client.get(URL).status_code, 405)

    def test_unknown_kind_400(self) -> None:
        body = self._body(self._contexts()["event"])
        body["kind"] = "lobby_info"
        result = self._assert_error_body(self._post(self.admin, body))
        self.assertEqual(result["error"], "Invalid preview request.")
        self.assertEqual(result["detail"][0]["loc"], ["kind"])

    def test_bad_context_400(self) -> None:
        for context in (
            {"type": "tournament", "event_id": self.event.pk},
            {"type": "event"},
            {"type": "event", "event_id": self.event.pk, "organization_id": 1},
            "event",
        ):
            with self.subTest(context=context):
                body = self._body(context)  # type: ignore[arg-type]
                self._assert_error_body(self._post(self.admin, body))

    def test_extra_request_key_400(self) -> None:
        body = self._body(self._contexts()["event"], organization_id=self.org.pk)
        result = self._assert_error_body(self._post(self.admin, body))
        self.assertEqual(result["detail"][0]["type"], "extra_forbidden")

    def test_non_object_body_400(self) -> None:
        client = APIClient()
        client.force_login(self.admin)
        response = client.post(URL, ["signup_post"], format="json")
        self._assert_error_body(response)

    def test_invalid_timezone_400(self) -> None:
        body = self._body(self._contexts()["event"], values={"timezone": "Not/AZone"})
        result = self._assert_error_body(self._post(self.admin, body))
        self.assertIn("timezone", result)

    def test_invalid_role_ids_400(self) -> None:
        body = self._body(
            self._contexts()["event"], values={"discord_signup_role_ids": ["abc"]}
        )
        result = self._assert_error_body(self._post(self.admin, body))
        self.assertIn("discord_signup_role_ids", result)

    def test_builder_error_400_not_500(self) -> None:
        with patch(
            "events.discord.preview.build_announcement_v2",
            side_effect=ValueError("boom"),
        ):
            response = self._post(self.admin, self._body(self._contexts()["event"]))
        result = self._assert_error_body(response)
        self.assertNotIn("boom", result["error"])

    def test_values_override_without_saving(self) -> None:
        name_before = self.event.name
        body = self._body(
            self._contexts()["event"], values={"discord_event_title": "Preview Only"}
        )
        response = self._post(self.admin, body)
        self.assertEqual(response.status_code, 200, response.content)
        self.event.refresh_from_db()
        self.assertEqual(self.event.name, name_before)
        self.assertNotEqual(self.event.discord_event_title, "Preview Only")


class DiscordPreviewExporterTest(EventTestCase):
    def test_script_runs_isolated(self) -> None:
        script = BACKEND / "events" / "discord" / "export_preview_schema.py"
        code = (
            "import runpy, sys; "
            f"runpy.run_path({str(script)!r}, run_name='__main__'); "
            "assert 'django' not in sys.modules, 'django imported'"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"DiscordPreviewApi"', result.stdout)
