from typing import Any
from unittest.mock import patch

from celery import Celery
from celery.app.task import Task
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient, APIRequestFactory

from app.models import CustomUser
from discordbot.models import DiscordEvent, DiscordEventMsgSignup
from discordbot.permissions.schemas import PermissionChecksResponse
from events.models import Event
from tests.data.discord_permissions import (
    PERMISSION_ATTENDANCE_CHANNEL_ID,
    PERMISSION_GUILD_ID,
    PERMISSION_ORG,
)
from tests.populate.discord_permissions import (
    discord_permissions_test_data,
    populate_discord_permissions_data,
)
from tests.test_discord_permissions import (
    discord_permissions_data,
    reset_discord_permissions,
    set_discord_permission_scenario,
)

DATA_KEYS: set[str] = {
    "org_pk",
    "league_pk",
    "fresh_event_pk",
    "posted_event_pk",
    "staff_pk",
    "league_staff_pk",
    "outsider_pk",
    "channel_ids",
    "message_log_count",
}


def _forbid(*args: Any, **kwargs: Any) -> None:
    raise AssertionError("populate dispatched a task")


@override_settings(TEST=True)
class DiscordPermissionsFixtureTest(TestCase):
    def setUp(self) -> None:
        self.clear_snapshot_cache()
        self.addCleanup(self.clear_snapshot_cache)
        populate_discord_permissions_data(force=True)
        self.data: dict[str, Any] = discord_permissions_test_data()
        self.factory = APIRequestFactory()

    def clear_snapshot_cache(self) -> None:
        cache.delete_pattern(f"discord_perm*{PERMISSION_GUILD_ID}*")

    def scenario(self, name: str) -> Any:
        request = self.factory.post(
            "/api/tests/discord-permissions/scenario/",
            {"scenario": name},
            format="json",
        )
        return set_discord_permission_scenario(request)

    def attendance_status(self) -> str:
        client = APIClient()
        client.force_authenticate(CustomUser.objects.get(pk=self.data["staff_pk"]))
        response = client.post(
            f"/api/discord/organizations/{self.data['org_pk']}/permission-checks/",
            {
                "checks": [
                    {
                        "key": "attendance_reminder",
                        "action": "attendance_reminder",
                        "channel_id": PERMISSION_ATTENDANCE_CHANNEL_ID,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = PermissionChecksResponse.model_validate(response.json())
        return body.checks[0].status

    def test_data_shape(self) -> None:
        self.assertEqual(set(self.data), DATA_KEYS)
        self.assertEqual(self.data["org_pk"], PERMISSION_ORG.pk)
        self.assertEqual(
            set(self.data["channel_ids"]),
            {"announcement", "attendance", "historical_thread"},
        )
        self.assertTrue(
            all(isinstance(v, str) for v in self.data["channel_ids"].values())
        )
        self.assertEqual(self.data["message_log_count"], 0)

    def test_fresh_and_posted_events(self) -> None:
        fresh = Event.objects.nocache().get(pk=self.data["fresh_event_pk"])
        posted = Event.objects.nocache().get(pk=self.data["posted_event_pk"])
        self.assertFalse(DiscordEvent.objects.filter(event=fresh).exists())
        state = DiscordEvent.objects.get(event=posted)
        self.assertTrue(state.signup_message.has_posted)
        self.assertEqual(
            state.signup_message.thread_id,
            self.data["channel_ids"]["historical_thread"],
        )
        for event in (fresh, posted):
            self.assertTrue(event.discord_create_event)
            self.assertEqual(
                event.discord_confirm_attendance_channel_id,
                self.data["channel_ids"]["attendance"],
            )
            self.assertEqual(event.tournament_league_id, self.data["league_pk"])

    @patch("tests.test_discord_permissions.isTestEnvironment", return_value=True)
    def test_scenario_switch_changes_org_result(self, _env: Any) -> None:
        self.assertEqual(self.scenario("attendance_missing_embed").status_code, 200)
        self.assertEqual(self.attendance_status(), "missing_permissions")
        self.assertEqual(self.scenario("all_granted").status_code, 200)
        self.assertEqual(self.attendance_status(), "verified")

    def event_statuses(self, event_pk: int) -> dict[str, str]:
        client = APIClient()
        client.force_authenticate(
            CustomUser.objects.get(pk=self.data["league_staff_pk"])
        )
        response = client.get(f"/api/events/{event_pk}/permission-checks/")
        self.assertEqual(response.status_code, 200, response.content)
        body = PermissionChecksResponse.model_validate(response.json())
        return {check.key: check.status for check in body.checks}

    @patch("tests.test_discord_permissions.isTestEnvironment", return_value=True)
    def test_posted_event_scenarios(self, _env: Any) -> None:
        verified = {
            "announcement",
            "attendance_reminder",
            "signup_edit",
            "scheduled_event_create",
            "scheduled_event_update",
            "scheduled_event_delete",
        }
        cases = {
            "all_granted": {},
            "attendance_missing_embed": {"attendance_reminder": "missing_permissions"},
            "no_create_events": {"scheduled_event_create": "missing_permissions"},
            "edit_access_denied": {"signup_edit": "missing_permissions"},
        }
        for name, changed in cases.items():
            with self.subTest(scenario=name):
                self.scenario(name)
                statuses = self.event_statuses(self.data["posted_event_pk"])
                for key in verified:
                    self.assertEqual(statuses[key], changed.get(key, "verified"), key)
                self.assertEqual(statuses["mark_interested"], "unsupported")
                self.assertNotEqual(statuses["signup_reminder"], "verified")
        self.scenario("all_granted")
        fresh = self.event_statuses(self.data["fresh_event_pk"])
        self.assertNotIn("signup_edit", fresh)
        self.assertEqual(fresh["attendance_reminder"], "verified")
        self.scenario("upstream_unavailable")
        statuses = self.event_statuses(self.data["posted_event_pk"])
        self.assertTrue(all(s != "verified" for s in statuses.values()), statuses)

    @patch("tests.test_discord_permissions.isTestEnvironment", return_value=True)
    def test_upstream_unavailable_is_unknown(self, _env: Any) -> None:
        self.scenario("upstream_unavailable")
        self.assertEqual(self.attendance_status(), "unknown")

    @patch("tests.test_discord_permissions.isTestEnvironment", return_value=True)
    def test_unknown_scenario_is_400(self, _env: Any) -> None:
        self.assertEqual(self.scenario("not_a_scenario").status_code, 400)
        request = self.factory.post(
            "/api/tests/discord-permissions/scenario/",
            {"scenario": {"/users/@me": {"id": "1"}}},
            format="json",
        )
        self.assertEqual(set_discord_permission_scenario(request).status_code, 400)

    @patch("tests.test_discord_permissions.isTestEnvironment", return_value=True)
    def test_reset_is_idempotent(self, _env: Any) -> None:
        self.scenario("all_granted")
        first = reset_discord_permissions(
            self.factory.post("/api/tests/discord-permissions/reset/")
        )
        second = reset_discord_permissions(
            self.factory.post("/api/tests/discord-permissions/reset/")
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(set(second.data), DATA_KEYS)
        self.assertEqual(
            {k: v for k, v in first.data.items() if not k.endswith("event_pk")},
            {k: v for k, v in second.data.items() if not k.endswith("event_pk")},
        )
        for name in ("Permission Badges Fresh Event", "Permission Badges Posted Event"):
            self.assertEqual(
                Event.objects.nocache()
                .filter(organization_id=PERMISSION_ORG.pk, name=name)
                .count(),
                1,
            )
        self.assertEqual(
            DiscordEventMsgSignup.objects.filter(
                event__organization_id=PERMISSION_ORG.pk
            ).count(),
            1,
        )
        self.assertEqual(self.attendance_status(), "missing_permissions")
        data = discord_permissions_data(
            self.factory.get("/api/tests/discord-permissions/data/")
        )
        self.assertEqual(data.data, second.data)

    def test_populate_dispatches_no_tasks(self) -> None:
        with (
            patch.object(Task, "apply_async", _forbid),
            patch.object(Celery, "send_task", _forbid),
            patch("requests.post", _forbid),
            patch("requests.get", _forbid),
        ):
            populate_discord_permissions_data(force=True)
            populate_discord_permissions_data(force=False)
        self.assertEqual(discord_permissions_test_data()["message_log_count"], 0)

    def test_endpoints_404_outside_test(self) -> None:
        calls = (
            lambda: discord_permissions_data(
                self.factory.get("/api/tests/discord-permissions/data/")
            ),
            lambda: reset_discord_permissions(
                self.factory.post("/api/tests/discord-permissions/reset/")
            ),
            lambda: self.scenario("all_granted"),
        )
        with patch(
            "tests.test_discord_permissions.isTestEnvironment", return_value=True
        ):
            with override_settings(TEST=False):
                for call in calls:
                    self.assertEqual(call().status_code, 404)
        with patch(
            "tests.test_discord_permissions.isTestEnvironment", return_value=False
        ):
            for call in calls:
                self.assertEqual(call().status_code, 404)
        self.assertIsNone(cache.get(f"discord_perm_fixture:{PERMISSION_GUILD_ID}"))
