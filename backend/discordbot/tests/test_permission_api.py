import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.response import Response
from rest_framework.test import APIClient, APITestCase

from app.models import CustomUser
from discordbot.models import DiscordEvent, DiscordMessageLog
from discordbot.permissions.schemas import PermissionChecksResponse
from discordbot.tests.test_permission_reader import B, C, G, scenario
from org.models import Organization, OrgUser


@override_settings(
    TEST=True,
    DISCORD_BOT_TOKEN="synthetic",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class PermissionApiTests(APITestCase):
    staff: CustomUser
    member: CustomUser
    unrelated: CustomUser
    superuser: CustomUser
    org: Organization
    other_org: Organization

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = CustomUser.objects.create_user(
            username="permission_staff", password="x"
        )
        cls.member = CustomUser.objects.create_user(
            username="permission_member", password="x"
        )
        cls.unrelated = CustomUser.objects.create_user(
            username="permission_other", password="x"
        )
        cls.superuser = CustomUser.objects.create_user(
            username="permission_super", is_superuser=True
        )
        cls.org = Organization.objects.create(
            name="Permission Org", discord_server_id=G
        )
        cls.org.staff.add(cls.staff)
        OrgUser.objects.create(organization=cls.org, user=cls.member)
        cls.other_org = Organization.objects.create(name="Other Permission Org")
        cls.other_org.staff.add(cls.unrelated)

    def setUp(self) -> None:
        cache.clear()
        cache.set(f"discord_perm_fixture:{G}", scenario())
        self.client.force_authenticate(self.staff)
        self.url: str = f"/api/discord/organizations/{self.org.pk}/permission-checks/"

    def post(self, **overrides: Any) -> Response:
        data = {"checks": [{"key": "post", "action": "announcement", "channel_id": C}]}
        data.update(overrides)
        return self.client.post(self.url, data, format="json")

    def test_auth_matrix(self) -> None:
        for user, expected in (
            (None, 403),
            (self.member, 403),
            (self.unrelated, 403),
            (self.staff, 200),
            (self.superuser, 200),
        ):
            for refresh in (False, True):
                with self.subTest(user=user, refresh=refresh):
                    cache.clear()
                    cache.set(f"discord_perm_fixture:{G}", scenario())
                    self.client.force_authenticate(user)
                    if expected == 403:
                        before = set(cache._cache)
                        with patch("discordbot.permissions.service.run_checks") as run:
                            response = self.post(refresh=refresh)
                        run.assert_not_called()
                        self.assertEqual(set(cache._cache), before)
                    else:
                        response = self.post(refresh=refresh)
                    self.assertEqual(response.status_code, expected)

    def test_guild_derived_from_org(self) -> None:
        response = self.post(guild_id=G)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"][0]["type"], "extra_forbidden")

    def test_rejects_disallowed_actions(self) -> None:
        for action in ("admin_channel_post", "signup_edit", "announcement_edit"):
            with self.subTest(action=action):
                response = self.post(
                    checks=[{"key": "post", "action": action, "channel_id": C}]
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json())

    def test_prospective_update_without_resource_is_never_green(self) -> None:
        response = self.post(
            checks=[
                {
                    "key": "update",
                    "action": "scheduled_event_update",
                    "channel_id": None,
                }
            ]
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()["checks"][0]
        self.assertEqual(result["status"], "unconfigured")
        self.assertIn("missing_reference", [b["code"] for b in result["blockers"]])

    def test_rejects_oversize_and_duplicate_keys(self) -> None:
        check = {"key": "post", "action": "announcement", "channel_id": C}
        for checks in (
            [],
            [check] * 21,
            [check, check],
            [{**check, "role_ids": [C] * 26}],
        ):
            with self.subTest(checks=checks):
                response = self.post(checks=checks)
                self.assertEqual(response.status_code, 400)
                data = response.json()
                self.assertEqual(data["error"], "Invalid permission check request")
                self.assertTrue(data["detail"])
                self.assertTrue(all("ctx" not in item for item in data["detail"]))
        response = self.post(checks=[check, check])
        self.assertEqual(response.json()["detail"][0]["type"], "value_error")

    def test_rejects_numeric_ids(self) -> None:
        for fields in ({"channel_id": int(C)}, {"channel_id": C, "role_ids": [int(B)]}):
            response = self.post(
                checks=[{"key": "post", "action": "announcement", **fields}]
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("detail", response.json())

    def test_org_without_server_returns_unconfigured(self) -> None:
        Organization.objects.filter(pk=self.org.pk).update(discord_server_id=None)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        result = response.json()["checks"][0]
        self.assertEqual(result["status"], "unconfigured")
        self.assertEqual(result["reason"], "no_server_configured")

    def test_foreign_channel_leaks_no_metadata(self) -> None:
        foreign = "800000000000000001"
        data = scenario()
        data[f"/channels/{foreign}"] = {
            "id": foreign,
            "guild_id": "800000000000000002",
            "type": 0,
            "name": "private name",
            "permission_overwrites": [],
        }
        cache.set(f"discord_perm_fixture:{G}", data)
        response = self.post(
            checks=[{"key": "post", "action": "announcement", "channel_id": foreign}]
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()["checks"][0]
        self.assertIsNone(result["destination"]["name"])
        self.assertIsNone(result["destination"]["channel_type"])
        self.assertEqual(result["reason"], "resource_unavailable")

    def test_response_validates_against_pydantic(self) -> None:
        response = self.post()
        self.assertEqual(response.status_code, 200)
        body = PermissionChecksResponse.model_validate(response.json())
        self.assertEqual(body.guild_id, G)
        self.assertEqual(body.checks[0].status, "verified")
        self.assertEqual(body.checks[0].destination.channel_id, C)
        self.assertIn("SEND_MESSAGES", body.checks[0].granted)

    def test_post_requires_csrf(self) -> None:
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.staff)
        response = client.post(
            self.url,
            {"checks": [{"key": "post", "action": "announcement", "channel_id": C}]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("CSRF", response.json()["detail"])

    def test_refresh_throttled_after_five(self) -> None:
        for _ in range(5):
            response = self.post(refresh=True)
            self.assertEqual(response.status_code, 200)
            self.assertNotEqual(
                response.json()["checks"][0]["refresh_state"], "throttled"
            )
        response = self.post(refresh=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"][0]["refresh_state"], "throttled")
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()["checks"][0]["refresh_state"], "throttled")

    def test_no_writes(self) -> None:
        before = (DiscordMessageLog.objects.count(), DiscordEvent.objects.count())
        with patch(
            "celery.current_app.send_task",
            side_effect=AssertionError("No jobs allowed"),
        ):
            response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (DiscordMessageLog.objects.count(), DiscordEvent.objects.count()), before
        )


class ExporterTest(SimpleTestCase):
    def test_script_runs_isolated(self) -> None:
        script = (
            Path(__file__).resolve().parents[1] / "permissions" / "export_schema.py"
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("DJANGO_")
        }
        result = subprocess.run(
            [sys.executable, "-I", str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = json.loads(result.stdout)
        self.assertEqual(bundle["schema"]["title"], "PermissionChecksApi")
        self.assertTrue(
            {
                "PermissionChecksRequest",
                "PermissionChecksResponse",
                "PermissionCheckResult",
                "ActionKind",
            }
            <= bundle["schema"]["$defs"].keys()
        )
