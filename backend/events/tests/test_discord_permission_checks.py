import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from discordbot.models import (
    DiscordEvent,
    DiscordEventMsgAnnouncement,
    DiscordEventMsgSignup,
    DiscordMessageLog,
)
from discordbot.permissions.schemas import PermissionChecksResponse
from discordbot.tests.test_permission_reader import C, E, G, M, T, scenario
from events.models import EventRepeater
from events.tests.base import EventTestCase
from org.models import Organization


@override_settings(
    TEST=True,
    DISCORD_BOT_TOKEN="synthetic",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class EventPermissionTests(EventTestCase):
    def setUp(self) -> None:
        cache.clear()
        cache.set(f"discord_perm_fixture:{G}", scenario())
        self.org.discord_server_id = G
        self.org.save(update_fields=["discord_server_id"])
        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = C
        self.event.save()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url: str = f"/api/events/{self.event.pk}/permission-checks/"
        self.body: dict[str, Any] = {
            "checks": [
                {"key": "announcement", "action": "announcement", "channel_id": C}
            ]
        }

    def results(self) -> dict[str, Any]:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        PermissionChecksResponse.model_validate(response.json())
        return {check["key"]: check for check in response.json()["checks"]}

    def state(self, **kwargs: Any) -> DiscordEvent:
        return DiscordEvent.objects.create(event=self.event, guild_id=G, **kwargs)

    def test_auth_matrix(self) -> None:
        other = Organization.objects.create(name="Unrelated permission org")
        other.staff.add(self.unrelated_user)
        self.event.host = self.user
        self.event.save()
        for user, expected in (
            (self.admin, 200),
            (self.league_staff, 200),
            (self.user, 403),
            (self.unrelated_user, 403),
            (None, 403),
        ):
            with self.subTest(user=user):
                self.client.force_authenticate(user)
                if expected == 403:
                    before = set(cache._cache)
                    with patch("discordbot.permissions.service.run_checks") as run:
                        responses = [
                            self.client.get(self.url),
                            self.client.post(self.url, self.body, format="json"),
                        ]
                    run.assert_not_called()
                    self.assertEqual(set(cache._cache), before)
                else:
                    responses = [
                        self.client.get(self.url),
                        self.client.post(self.url, self.body, format="json"),
                    ]
                for response in responses:
                    self.assertEqual(response.status_code, expected)
        self.client.force_authenticate(self.league_staff)
        self.assertEqual(
            self.client.post(
                f"/api/discord/organizations/{self.org.pk}/permission-checks/",
                self.body,
                format="json",
            ).status_code,
            403,
        )

    def test_fresh_event_without_discord_event_row(self) -> None:
        self.assertFalse(DiscordEvent.objects.filter(event=self.event).exists())
        self.assertEqual(self.results()["announcement"]["status"], "verified")

    def test_destination_cases_fixture(self) -> None:
        cases = json.loads(
            Path(__file__).with_name("permission_destination_cases.json").read_text()
        )
        for case in cases:
            with self.subTest(case=case["name"]):
                event = self.make_event(**case["settings"])
                self.url = f"/api/events/{event.pk}/permission-checks/"
                results = self.results()
                for key, expected in case["expected"].items():
                    if expected is None:
                        self.assertNotIn(key, results)
                    else:
                        for field, value in expected.items():
                            self.assertEqual(results[key]["destination"][field], value)
                        if expected["channel_id"] is None:
                            self.assertEqual(
                                results[key]["reason"], "no_channel_configured"
                            )

    def test_primary_failure_with_fallback_success_keeps_primary_red(self) -> None:
        self.event.discord_post_signups = True
        self.event.discord_post_signups_channel_id = E
        self.event.save()
        results = self.results()
        self.assertEqual(results["signup_post"]["status"], "unknown")
        self.assertEqual(results["signup_fallback"]["status"], "verified")

    def test_announcement_roles_apply_only_when_notice_is_sent(self) -> None:
        deleted, unmentionable = "900000000000000099", "900000000000000098"
        data = scenario()
        roles = data[f"/guilds/{G}"]["roles"]
        roles[0]["permissions"] = str((1 << 10) | (1 << 11) | (1 << 14))
        roles.append(
            {
                "id": unmentionable,
                "permissions": "0",
                "mentionable": False,
                "managed": False,
            }
        )
        cache.set(f"discord_perm_fixture:{G}", data)
        self.event.discord_announcement_role_ids = [unmentionable, deleted]
        for post_signups, signup_channel, notice in (
            (False, "", False),
            (True, "", False),
            (True, E, True),
        ):
            with self.subTest(post_signups=post_signups, channel=signup_channel):
                self.event.discord_post_signups = post_signups
                self.event.discord_post_signups_channel_id = signup_channel
                self.event.save()
                result = self.results()["announcement"]
                self.assertEqual(
                    result["action"], "announcement" if notice else "signup_fallback"
                )
                blockers = [b["code"] for b in result["blockers"]]
                if notice:
                    self.assertNotEqual(result["status"], "verified")
                    self.assertIn("role_missing", blockers)
                    self.assertIn("role_not_mentionable", blockers)
                    self.assertIn("MENTION_EVERYONE", result["missing"])
                else:
                    self.assertEqual(result["status"], "verified")
                    self.assertEqual(blockers, [])
                    self.assertEqual(result["destination"]["source"], "fallback")
                    self.assertNotIn("MENTION_EVERYONE", result["required_all"])
                    response = self.client.post(
                        self.url,
                        {
                            "checks": [
                                {
                                    "key": "announcement",
                                    "action": "signup_fallback",
                                    "channel_id": C,
                                    "role_ids": [],
                                }
                            ]
                        },
                        format="json",
                    )
                    self.assertEqual(response.status_code, 200)
                    preview = response.json()["checks"][0]
                    self.assertEqual(preview["status"], "verified")
                    self.assertEqual(preview["destination"], result["destination"])

    def test_historical_thread_vs_changed_configuration(self) -> None:
        signup = DiscordEventMsgSignup.objects.create(
            event=self.event,
            channel_id=C,
            thread_id=T,
            channel_type="forum",
            message_id=M,
            has_posted=True,
        )
        self.state(signup_message=signup)
        self.event.discord_post_signups = True
        self.event.discord_post_signups_channel_id = E
        self.event.discord_start_mention = True
        self.event.save()
        results = self.results()
        self.assertEqual(results["signup_edit"]["destination"]["channel_id"], T)
        self.assertEqual(results["signup_edit"]["destination"]["source"], "posted")
        self.assertEqual(results["signup_edit"]["status"], "verified")
        self.assertEqual(results["start_mention"]["destination"]["channel_id"], T)
        self.assertEqual(results["signup_post"]["destination"]["channel_id"], E)

    def test_posted_message_ownership_must_be_read(self) -> None:
        signup = DiscordEventMsgSignup.objects.create(
            event=self.event, channel_id=T, message_id=M, has_posted=True
        )
        self.state(signup_message=signup)
        data = scenario()
        data[f"/channels/{T}/messages/{M}"]["author"]["id"] = E
        cache.set(f"discord_perm_fixture:{G}", data)
        self.assertNotEqual(self.results()["signup_edit"]["status"], "verified")

    def test_missing_posted_metadata_is_unknown(self) -> None:
        signup = DiscordEventMsgSignup.objects.create(
            event=self.event, channel_id="", message_id=M, has_posted=True
        )
        self.state(signup_message=signup)
        self.assertEqual(self.results()["signup_edit"]["status"], "unknown")

    def test_start_mention_pending_without_post(self) -> None:
        self.event.discord_start_mention = True
        self.event.save()
        self.assertEqual(
            self.results()["start_mention"]["reason"], "pending_signup_post"
        )

    def test_scheduled_update_delete_only_with_persisted_id(self) -> None:
        self.event.discord_create_event = True
        self.event.discord_sync_signups = True
        self.event.save()
        self.assertNotIn("scheduled_event_update", self.results())
        state = self.state(scheduled_event_id=E)
        results = self.results()
        for key in (
            "scheduled_event_create",
            "scheduled_event_update",
            "scheduled_event_delete",
        ):
            self.assertEqual(results[key]["status"], "verified")
        response = self.client.post(
            self.url,
            {
                "checks": [
                    {
                        "key": "update",
                        "action": "scheduled_event_update",
                        "channel_id": None,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.json()["checks"][0]["status"], "verified")
        state.scheduled_event_id = None
        state.save()
        response = self.client.post(
            self.url,
            {
                "checks": [
                    {
                        "key": "update",
                        "action": "scheduled_event_update",
                        "channel_id": None,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.json()["checks"][0]["status"], "unconfigured")

    def test_unknown_creator_update_not_green(self) -> None:
        self.state(scheduled_event_id=E)
        data = scenario()
        data[f"/guilds/{G}"]["roles"][0]["permissions"] = str(1 << 44)
        del data[f"/guilds/{G}/scheduled-events/{E}"]["creator_id"]
        cache.set(f"discord_perm_fixture:{G}", data)
        self.assertNotEqual(
            self.results()["scheduled_event_update"]["status"], "verified"
        )

    def test_preview_rejects_foreign_scope_and_non_event_actions(self) -> None:
        bodies = [{**self.body, "organization_id": self.org.pk}]
        bodies.extend(
            {"checks": [{"key": "post", "action": action, "channel_id": C}]}
            for action in (
                "template_post",
                "admin_channel_post",
                "signup_edit",
                "announcement_edit",
            )
        )
        for body in bodies:
            with self.subTest(body=body):
                self.assertEqual(
                    self.client.post(self.url, body, format="json").status_code, 400
                )

    def test_new_event_notice_requires_series_and_resolves_own_channel(self) -> None:
        self.assertNotIn("new_event_notice", self.results())
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Permission series",
            frequency="weekly",
            time_of_day=self.event.scheduled_at.time(),
            starts_at=self.event.scheduled_at.date(),
            discord_notify_new_events=True,
        )
        self.event.event_repeater = repeater
        self.event.discord_new_event_channel_id = C
        self.event.save()
        result = self.results()["new_event_notice"]
        self.assertEqual(result["destination"]["channel_id"], C)
        self.assertEqual(result["destination"]["source"], "configured")
        self.event.discord_new_event_channel_id = ""
        self.event.discord_announcement = False
        self.event.save()
        self.assertEqual(
            self.results()["new_event_notice"]["destination"]["source"], "fallback"
        )
        repeater.discord_notify_new_events = False
        repeater.save()
        self.assertNotIn("new_event_notice", self.results())

    def test_dm_toggles_and_disabled_actions(self) -> None:
        self.event.discord_announcement = False
        self.event.discord_post_signups = False
        self.event.discord_create_event = False
        self.event.discord_signup_reminder = True
        self.event.discord_send_draft_link = True
        self.event.discord_send_herodraft_link = True
        self.event.save()
        results = self.results()
        for key in ("signup_reminder", "draft_dm", "herodraft_dm"):
            self.assertEqual(results[key]["status"], "not_applicable")
        for key in (
            "announcement",
            "signup_post",
            "signup_fallback",
            "scheduled_event_create",
            "mark_interested",
        ):
            self.assertNotIn(key, results)

    def test_preview_fallback_source_matches_saved_resolver(self) -> None:
        self.event.discord_confirm_attendance = True
        self.event.discord_confirm_attendance_channel_id = ""
        self.event.save()
        saved = self.results()["attendance_reminder"]["destination"]
        response = self.client.post(
            self.url,
            {
                "checks": [
                    {
                        "key": "attendance_reminder",
                        "action": "attendance_reminder",
                        "channel_id": C,
                        "fallback": True,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        preview = response.json()["checks"][0]["destination"]
        self.assertEqual(saved["source"], "fallback")
        self.assertEqual(
            (preview["source"], preview["channel_id"]),
            (saved["source"], saved["channel_id"]),
        )

    def test_preview_start_mention_remains_prospective(self) -> None:
        signup = DiscordEventMsgSignup.objects.create(
            event=self.event, channel_id=T, message_id=M, has_posted=True
        )
        self.state(signup_message=signup)
        response = self.client.post(
            self.url,
            {"checks": [{"key": "start", "action": "start_mention", "channel_id": C}]},
            format="json",
        )
        result = response.json()["checks"][0]
        self.assertEqual(result["reason"], "pending_signup_post")
        self.assertEqual(result["destination"]["source"], "prospective")

    def test_announcement_edit_uses_posted_destination(self) -> None:
        message = DiscordEventMsgAnnouncement.objects.create(
            event=self.event, channel_id=T, message_id=M, has_posted=True
        )
        self.state(announcement=message)
        result = self.results()["announcement_edit"]
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["destination"]["channel_id"], T)

    def test_refresh_throttled_after_five(self) -> None:
        for _ in range(5):
            self.assertNotEqual(
                self.client.get(self.url, {"refresh": "true"}).json()["checks"][0][
                    "refresh_state"
                ],
                "throttled",
            )
        self.assertEqual(
            self.client.get(self.url, {"refresh": "true"}).json()["checks"][0][
                "refresh_state"
            ],
            "throttled",
        )

    def test_preview_requires_csrf(self) -> None:
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(
            client.post(self.url, self.body, format="json").status_code, 403
        )

    def test_preview_duplicate_keys_returns_json_400(self) -> None:
        response = self.client.post(
            self.url, {"checks": self.body["checks"] * 2}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Invalid permission check request")
        self.assertEqual(data["detail"][0]["type"], "value_error")
        self.assertTrue(all("ctx" not in item for item in data["detail"]))

    def test_discord_history_cache_untouched_and_no_writes(self) -> None:
        before = (DiscordMessageLog.objects.count(), DiscordEvent.objects.count())
        self.assertEqual(
            self.client.get(f"/api/events/{self.event.pk}/discord/").status_code, 404
        )
        with (
            patch(
                "events.views.cached_as",
                side_effect=AssertionError("history cache accessed"),
            ),
            patch(
                "celery.current_app.send_task",
                side_effect=AssertionError("task dispatched"),
            ),
        ):
            self.results()
        self.assertEqual(
            (DiscordMessageLog.objects.count(), DiscordEvent.objects.count()), before
        )
