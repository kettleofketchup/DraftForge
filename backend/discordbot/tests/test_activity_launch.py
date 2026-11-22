"""Notification launch/join routing never chooses the DM's channel."""

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import requests
from asgiref.sync import async_to_sync
from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser, Game, Team, Tournament
from discordbot.activity_auth import authenticate_token, issue_activity_token
from discordbot.activity_ids import decode_draft_launch
from discordbot.activity_intent import peek_intent
from discordbot.activity_launch import BindResult, prepare_activity_launch
from discordbot.activity_launch_gateway import handle_draft_launch
from discordbot.models import DraftActivityChannel, DraftActivityInstance
from discordbot.tests.activity_helpers import ClearIntentsMixin
from draft.models import Draft, DraftTeam, HeroDraft


@override_settings(
    DISCORD_ACTIVITY_ENABLED=True,
    DISCORD_GUILD_ID="1",
    SOCIAL_AUTH_DISCORD_KEY="9",
    DISCORD_BOT_TOKEN="secret",
)
class ActivityLaunchTests(ClearIntentsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = CustomUser.objects.create_user(
            username="launch-captain", discordId="101"
        )
        self.tournament = Tournament.objects.create(
            name="Launch", date_played=date.today()
        )
        self.tournament.users.add(self.user)
        self.team = Team.objects.create(
            name="A", tournament=self.tournament, captain=self.user
        )
        self.hero = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.tournament)
        )
        DraftTeam.objects.create(draft=self.hero, tournament_team=self.team)
        self.team_draft = Draft.objects.create(tournament=self.tournament)

    def fake_discord(self, channel="20"):
        """Answer by path so call order doesn't matter."""

        def call(method, path, **kwargs):
            if "/voice-states/" in path:
                return {"channel_id": channel}
            if path.endswith("/invites"):
                return {"code": "invite-code"}
            if path.startswith("/channels/"):
                return {"id": channel, "type": 2, "guild_id": "1"}
            raise AssertionError(f"unexpected Discord call {method} {path}")

        return call

    def discord_responses(self, channel="20"):
        return [
            {"channel_id": channel},
            {"id": channel, "type": 2, "guild_id": "1"},
            {"code": "invite-code"},
        ]

    @patch("discordbot.activity_launch.discord_json")
    def test_hero_notification_resolves_current_voice_and_creates_app_invite(self, api):
        api.side_effect = self.discord_responses()
        result = prepare_activity_launch("101", "hero", self.hero.pk)
        self.assertTrue(result["success"])
        self.assertIn("<#20>", result["content"])
        self.assertIn("five minutes", result["content"])
        self.assertTrue(all(call.kwargs["timeout"] == 2 for call in api.call_args_list))
        self.assertEqual(
            result["components"][0]["components"][0]["url"],
            "https://discord.gg/invite-code",
        )
        binding = DraftActivityChannel.objects.get(channel_id="20")
        self.assertEqual(binding.draft_id, self.hero.pk)
        self.assertIsNone(binding.team_draft_id)
        self.assertEqual(
            api.call_args_list[0].args, ("GET", "/guilds/1/voice-states/101")
        )
        self.assertEqual(api.call_args_list[-1].args, ("POST", "/channels/20/invites"))
        self.assertEqual(api.call_args_list[-1].kwargs["json"]["target_type"], 2)
        self.assertEqual(
            api.call_args_list[-1].kwargs["json"]["target_application_id"], "9"
        )

    @patch("discordbot.activity_launch.discord_json")
    def test_team_notification_and_second_participant_share_same_binding(self, api):
        api.side_effect = self.discord_responses() + self.discord_responses()
        self.assertTrue(
            prepare_activity_launch("101", "team", self.team_draft.pk)["success"]
        )
        self.assertTrue(
            prepare_activity_launch("101", "team", self.team_draft.pk)["success"]
        )
        self.assertEqual(DraftActivityChannel.objects.count(), 1)
        self.assertEqual(
            DraftActivityChannel.objects.get().team_draft_id, self.team_draft.pk
        )

    @patch("discordbot.activity_launch.discord_json")
    def test_outsider_cannot_assign_channel_or_create_invite(self, api):
        outsider = CustomUser.objects.create_user(username="outsider", discordId="102")
        for kind, draft_id in [("hero", self.hero.pk), ("team", self.team_draft.pk)]:
            self.assertFalse(
                prepare_activity_launch(outsider.discordId, kind, draft_id)["success"]
            )
        api.assert_not_called()
        self.assertFalse(DraftActivityChannel.objects.exists())

    @patch("discordbot.activity_launch.discord_json")
    def test_spectating_match_member_can_join(self, api):
        member = CustomUser.objects.create_user(username="member", discordId="102")
        self.team.members.add(member)
        api.side_effect = self.discord_responses()
        self.assertTrue(
            prepare_activity_launch(member.discordId, "hero", self.hero.pk)["success"]
        )

    @patch("discordbot.activity_launch.discord_json")
    def test_no_voice_connection_has_actionable_error(self, api):
        api.return_value = {"channel_id": None}
        result = prepare_activity_launch("101", "hero", self.hero.pk)
        self.assertFalse(result["success"])
        self.assertIn("Join your team's voice channel", result["content"])
        self.assertFalse(DraftActivityChannel.objects.exists())

    @patch("discordbot.activity_launch.discord_json")
    def test_nonvoice_or_wrong_guild_is_rejected(self, api):
        for channel in [{"type": 0, "guild_id": "1"}, {"type": 2, "guild_id": "99"}]:
            api.side_effect = [{"channel_id": "20"}, channel]
            self.assertFalse(
                prepare_activity_launch("101", "hero", self.hero.pk)["success"]
            )
        self.assertFalse(DraftActivityChannel.objects.exists())

    def invite_calls(self, api):
        return [c for c in api.call_args_list if c.args[1].endswith("/invites")]

    def other_tournament_hero(self, tournament):
        return HeroDraft.objects.create(
            game=Game.objects.create(tournament=tournament), state="drafting"
        )

    @patch("discordbot.activity_launch.discord_json")
    def test_binding_replaced_when_previous_draft_finished(self, api):
        finished = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.tournament), state="completed"
        )
        binding = DraftActivityChannel.objects.create(
            guild_id="1", channel_id="20", draft=finished
        )
        api.side_effect = self.fake_discord()
        with capture_logs() as logs:
            self.assertTrue(
                prepare_activity_launch("101", "hero", self.hero.pk)["success"]
            )
        binding.refresh_from_db()
        self.assertEqual(binding.draft_id, self.hero.pk)
        entry = next(e for e in logs if e["event"] == "activity_launch_resolved")
        self.assertEqual(entry["outcome"], "invite_created")
        self.assertEqual(entry["previous_channel_draft"], f"hero:{finished.pk}")

    @patch("discordbot.activity_launch.discord_json")
    def test_binding_replaced_for_same_tournament_unfinished_draft(self, api):
        self.team_draft.state = "drafting"
        self.team_draft.save()
        binding = DraftActivityChannel.objects.create(
            guild_id="1", channel_id="20", team_draft=self.team_draft
        )
        api.side_effect = self.fake_discord()
        self.assertTrue(prepare_activity_launch("101", "hero", self.hero.pk)["success"])
        binding.refresh_from_db()
        self.assertEqual(binding.draft_id, self.hero.pk)
        self.assertIsNone(binding.team_draft_id)
        self.assertEqual(len(self.invite_calls(api)), 1)

    @patch("discordbot.activity_launch.discord_json")
    def test_launch_does_not_touch_existing_instances(self, api):
        finished = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.tournament), state="completed"
        )
        DraftActivityChannel.objects.create(
            guild_id="1", channel_id="20", draft=finished
        )
        instance = DraftActivityInstance.objects.create(
            instance_id="running", guild_id="1", channel_id="20", draft=finished
        )
        token = issue_activity_token(self.user, instance)
        api.side_effect = self.fake_discord()
        self.assertTrue(prepare_activity_launch("101", "hero", self.hero.pk)["success"])
        instance.refresh_from_db()
        self.assertEqual(instance.draft_id, finished.pk)
        identity = authenticate_token(token, finished.pk, "hero")
        self.assertEqual(identity.user, self.user)
        self.assertEqual(identity.instance.pk, instance.pk)
        self.assertEqual(identity.tournament_id, self.tournament.pk)

    @patch("discordbot.activity_launch.discord_json")
    def test_channel_busy_for_other_tournament_unfinished_draft(self, api):
        other = Tournament.objects.create(name="Other Cup", date_played=date.today())
        busy = self.other_tournament_hero(other)
        binding = DraftActivityChannel.objects.create(
            guild_id="1", channel_id="20", draft=busy
        )
        api.side_effect = self.fake_discord()
        result = prepare_activity_launch("101", "hero", self.hero.pk)
        self.assertFalse(result["success"])
        self.assertIn("<#20>", result["content"])
        self.assertIn("Other Cup, another tournament", result["content"])
        self.assertIn(
            f"{settings.SITE_URL}/herodraft/{self.hero.pk}", result["content"]
        )
        binding.refresh_from_db()
        self.assertEqual(binding.draft_id, busy.pk)
        self.assertEqual(self.invite_calls(api), [])

    @patch("discordbot.activity_launch.discord_json")
    def test_channel_busy_for_tournamentless_configured_draft(self, api):
        busy = self.other_tournament_hero(None)
        binding = DraftActivityChannel.objects.create(
            guild_id="1", channel_id="20", draft=busy
        )
        api.side_effect = self.fake_discord()
        result = prepare_activity_launch("101", "team", self.team_draft.pk)
        self.assertFalse(result["success"])
        self.assertIn("another event, another tournament", result["content"])
        self.assertIn(
            f"{settings.SITE_URL}/tournament/{self.tournament.pk}/teams/draft",
            result["content"],
        )
        binding.refresh_from_db()
        self.assertEqual(binding.draft_id, busy.pk)
        self.assertIsNone(binding.team_draft_id)
        self.assertEqual(self.invite_calls(api), [])

    @patch(
        "discordbot.activity_launch._bind_channel",
        return_value=BindResult("channel_busy", None),
    )
    @patch("discordbot.activity_launch.discord_json")
    def test_channel_busy_without_previous_never_creates_invite(self, api, _bind):
        api.side_effect = self.fake_discord()
        result = prepare_activity_launch("101", "hero", self.hero.pk)
        self.assertFalse(result["success"])
        self.assertIn("<#20>", result["content"])
        self.assertEqual(self.invite_calls(api), [])

    @patch("discordbot.activity_launch.discord_json")
    def test_guild_conflict_kept(self, api):
        binding = DraftActivityChannel.objects.create(
            guild_id="2", channel_id="20", draft=self.hero
        )
        api.side_effect = self.fake_discord()
        result = prepare_activity_launch("101", "team", self.team_draft.pk)
        self.assertFalse(result["success"])
        self.assertIn("already assigned", result["content"])
        binding.refresh_from_db()
        self.assertEqual((binding.guild_id, binding.draft_id), ("2", self.hero.pk))
        self.assertEqual(self.invite_calls(api), [])

    @patch("discordbot.activity_launch.discord_json")
    def test_each_launch_logs_the_resolved_channel_and_outcome(self, api):
        api.side_effect = self.fake_discord(channel="20")
        with capture_logs() as logs:
            prepare_activity_launch("101", "hero", self.hero.pk)
        launches = [e for e in logs if e["event"] == "activity_launch_resolved"]
        self.assertEqual(len(launches), 1)
        entry = launches[0]
        self.assertEqual(entry["system"], "discord")
        self.assertEqual(entry["subsystem"], "activity")
        self.assertEqual(entry["outcome"], "invite_created")
        self.assertEqual(entry["voice_channel_id"], "20")
        self.assertEqual(entry["discord_user_id"], "101")
        self.assertEqual((entry["kind"], entry["draft_id"]), ("hero", self.hero.pk))
        self.assertIsNone(entry["previous_channel_draft"])
        self.assertEqual(entry["tournament_id"], self.tournament.pk)
        self.assertTrue(entry["intent_recorded"])
        self.assertNotIn("rebound", entry)
        self.assertNotIn("previous_draft", entry)

    @patch("discordbot.activity_launch.discord_json")
    def test_successful_launch_records_intent_for_launcher(self, api):
        api.side_effect = self.fake_discord()
        with capture_logs() as logs:
            self.assertTrue(
                prepare_activity_launch("101", "hero", self.hero.pk)["success"]
            )
        intent = peek_intent("101")
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual((intent.kind, intent.draft_id), ("hero", self.hero.pk))
        self.assertEqual(intent.tournament_id, self.tournament.pk)
        self.assertEqual((intent.guild_id, intent.channel_id), ("1", "20"))
        entry = next(e for e in logs if e["event"] == "activity_launch_resolved")
        self.assertTrue(entry["intent_recorded"])

    @patch("discordbot.activity_launch.discord_json")
    def test_failed_or_busy_launch_records_no_intent(self, api):
        other = Tournament.objects.create(name="Other Cup", date_played=date.today())
        for outcome in ("no_voice", "wrong_channel", "channel_busy", "error"):
            DraftActivityChannel.objects.all().delete()
            if outcome == "no_voice":
                api.side_effect = None
                api.return_value = {"channel_id": None}
            elif outcome == "wrong_channel":
                api.side_effect = [
                    {"channel_id": "20"},
                    {"id": "20", "type": 0, "guild_id": "1"},
                ]
            elif outcome == "channel_busy":
                DraftActivityChannel.objects.create(
                    guild_id="1",
                    channel_id="20",
                    draft=self.other_tournament_hero(other),
                )
                api.side_effect = self.fake_discord()
            else:
                api.side_effect = [
                    {"channel_id": "20"},
                    {"id": "20", "type": 2, "guild_id": "1"},
                    {"code": "bad code!"},
                ]
            with self.subTest(outcome=outcome), capture_logs() as logs:
                self.assertFalse(
                    prepare_activity_launch("101", "hero", self.hero.pk)["success"]
                )
                entry = next(
                    e for e in logs if e["event"] == "activity_launch_resolved"
                )
                self.assertEqual(entry["outcome"], outcome)
                self.assertFalse(entry["intent_recorded"])
                self.assertIsNone(peek_intent("101"))

    @patch("discordbot.activity_launch.record_intent", return_value=None)
    @patch("discordbot.activity_launch.discord_json")
    def test_redis_failure_still_creates_invite(self, api, _record):
        api.side_effect = self.fake_discord()
        with capture_logs() as logs:
            result = prepare_activity_launch("101", "hero", self.hero.pk)
        self.assertTrue(result["success"])
        entry = next(e for e in logs if e["event"] == "activity_launch_resolved")
        self.assertEqual(entry["outcome"], "invite_created")
        self.assertFalse(entry["intent_recorded"])

    @patch("discordbot.activity_launch.discord_json")
    def test_channel_busy_is_logged(self, api):
        other = Tournament.objects.create(name="Other Cup", date_played=date.today())
        busy = self.other_tournament_hero(other)
        DraftActivityChannel.objects.create(guild_id="1", channel_id="20", draft=busy)
        api.side_effect = self.fake_discord()
        with capture_logs() as logs:
            prepare_activity_launch("101", "hero", self.hero.pk)
        entry = next(e for e in logs if e["event"] == "activity_launch_resolved")
        self.assertEqual(entry["outcome"], "channel_busy")
        self.assertEqual(entry["busy_draft_id"], busy.pk)
        self.assertEqual(entry["busy_tournament_id"], other.pk)
        self.assertEqual(entry["previous_channel_draft"], f"hero:{busy.pk}")

    @patch("discordbot.activity_launch.discord_json")
    def test_reply_names_destination_and_how_to_recover_after_moving(self, api):
        api.side_effect = self.fake_discord(channel="20")
        content = prepare_activity_launch("101", "hero", self.hero.pk)["content"]
        self.assertTrue(content.startswith("This invite opens DraftForge in <#20>"))
        self.assertIn("no longer in <#20>", content)

    @patch("discordbot.activity_launch.discord_json")
    def test_launch_uses_bot_rate_limited_calls_without_voice_recheck(self, api):
        api.side_effect = self.discord_responses()
        prepare_activity_launch("101", "hero", self.hero.pk)
        self.assertEqual(api.call_count, 3)
        self.assertTrue(all(call.kwargs["bot"] for call in api.call_args_list))

    @patch("discordbot.activity_launch.CustomUser.objects.get")
    @patch("discordbot.activity_launch.discord_json")
    def test_deactivated_user_is_read_without_cache(self, api, cached_get):
        CustomUser.objects.filter(pk=self.user.pk).update(is_active=False)
        result = prepare_activity_launch("101", "hero", self.hero.pk)
        self.assertFalse(result["success"])
        cached_get.assert_not_called()
        api.assert_not_called()

    @patch("discordbot.activity_launch.discord_json")
    def test_discord_failure_does_not_expose_bot_token(self, api):
        api.side_effect = requests.ConnectionError("secret")
        result = prepare_activity_launch("101", "hero", self.hero.pk)
        self.assertFalse(result["success"])
        self.assertNotIn("secret", str(result))

    @override_settings(DISCORD_ACTIVITY_ENABLED=False)
    @patch("discordbot.activity_launch.discord_json")
    def test_disabled_feature_makes_no_external_requests(self, api):
        self.assertFalse(
            prepare_activity_launch("101", "hero", self.hero.pk)["success"]
        )
        api.assert_not_called()

    def test_internal_endpoint_rejects_anonymous_call(self):
        response = APIClient().post(
            "/api/internal/discord/activity-launch/",
            {"discord_user_id": "101", "kind": "hero", "draft_id": self.hero.pk},
        )
        self.assertEqual(response.status_code, 403)

    @patch("discordbot.tasks.complete_activity_launch.apply_async")
    def test_signed_http_component_defers_before_network_preparation(self, enqueue):
        from discordbot.views import handle_message_component

        response = handle_message_component(
            {
                "application_id": "9",
                "token": "private-token",
                "user": {"id": "101"},
                "data": {"custom_id": f"draft_activity:hero:{self.hero.pk}"},
            }
        )
        self.assertJSONEqual(response.content, {"type": 5, "data": {"flags": 64}})
        self.assertEqual(
            enqueue.call_args.kwargs["args"],
            ["9", "private-token", "101", "hero", self.hero.pk],
        )
        self.assertIn("redacted", enqueue.call_args.kwargs["argsrepr"])
        # Outlive a busy or restarting worker but not the 15-minute token.
        self.assertGreaterEqual(enqueue.call_args.kwargs["expires"], 10 * 60)
        self.assertLess(enqueue.call_args.kwargs["expires"], 15 * 60)

    def test_generic_channel_launcher_requires_binding(self):
        from discordbot.views import handle_message_component

        payload = {
            "guild_id": "1",
            "channel_id": "20",
            "data": {"custom_id": "draft_activity:launch"},
        }
        self.assertEqual(
            json.loads(handle_message_component(payload).content)["type"], 4
        )
        DraftActivityChannel.objects.create(
            guild_id="1", channel_id="20", draft=self.hero
        )
        self.assertEqual(
            json.loads(handle_message_component(payload).content), {"type": 12}
        )

    @patch("discordbot.activity_launch.discord_json")
    def test_finished_requested_draft_cannot_reserve_channel(self, api):
        self.hero.state = "completed"
        self.hero.save()
        result = prepare_activity_launch("101", "hero", self.hero.pk)
        self.assertFalse(result["success"])
        self.assertIn("finished", result["content"])
        self.assertFalse(DraftActivityChannel.objects.exists())
        api.assert_not_called()

    @patch(
        "discordbot.tasks.complete_activity_launch.apply_async",
        side_effect=OSError("broker unavailable"),
    )
    def test_signed_http_returns_actionable_error_when_queue_unavailable(self, enqueue):
        from discordbot.views import handle_message_component

        response = handle_message_component(
            {
                "application_id": "9",
                "token": "private-token",
                "user": {"id": "101"},
                "data": {"custom_id": f"draft_activity:hero:{self.hero.pk}"},
            }
        )
        data = json.loads(response.content)
        self.assertEqual(data["type"], 4)
        self.assertNotIn("private-token", data["data"]["content"])


class ActivityLaunchGatewayTests(SimpleTestCase):
    def test_id_codec_rejects_malformed_or_oversized_ids(self):
        self.assertEqual(decode_draft_launch("draft_activity:team:7"), ("team", 7))
        for custom_id in [
            "draft_activity:launch",
            "draft_activity:team:0",
            "draft_activity:hero:-1",
            "draft_activity:hero:1/2",
            "draft_activity:bad:1",
            "draft_activity:hero:" + "9" * 19,
        ]:
            self.assertIsNone(decode_draft_launch(custom_id))

    @patch("discordbot.activity_launch_gateway.prepare_launch_payload")
    def test_gateway_defers_then_returns_invite_confirmation(self, prepare):
        prepare.return_value = {
            "content": "Launch in your current channel",
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 5,
                            "label": "Launch / Join Activity",
                            "url": "https://discord.gg/test",
                        }
                    ],
                }
            ],
        }
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=101),
            response=SimpleNamespace(defer=AsyncMock()),
            edit_original_response=AsyncMock(),
        )
        async_to_sync(handle_draft_launch)(interaction, "hero", 3)
        interaction.response.defer.assert_awaited_once_with(
            ephemeral=True, thinking=True
        )
        prepare.assert_called_once_with("101", "hero", 3)
        self.assertEqual(
            interaction.edit_original_response.await_args.kwargs["view"]
            .children[0]
            .url,
            "https://discord.gg/test",
        )

    @patch("requests.patch")
    @patch("discordbot.tasks.prepare_launch_payload")
    def test_deferred_http_followup_uses_same_launch_service(
        self, prepare, patch_response
    ):
        from discordbot.tasks import complete_activity_launch

        prepare.return_value = {"content": "Ready", "components": []}
        complete_activity_launch.run("9", "private-token", "101", "team", 7)
        prepare.assert_called_once_with("101", "team", 7)
        self.assertEqual(
            patch_response.call_args.args[0],
            "https://discord.com/api/v10/webhooks/9/private-token/messages/@original",
        )
        self.assertEqual(patch_response.call_args.kwargs["timeout"], 10)


@override_settings(DISCORD_BOT_TOKEN="secret")
class DiscordJsonTests(SimpleTestCase):
    @patch("discordbot.activity.requests.request")
    @patch("discordbot.activity._rate_limited_request")
    def test_bot_calls_share_rate_limiter_and_oauth_calls_do_not(self, limited, direct):
        from discordbot.activity import discord_json

        limited.return_value.json.return_value = {"ok": True}
        self.assertEqual(discord_json("GET", "/channels/1", bot=True), {"ok": True})
        self.assertEqual(
            limited.call_args.kwargs["headers"]["Authorization"], "Bot secret"
        )
        discord_json("GET", "/users/@me", headers={"Authorization": "Bearer t"})
        direct.assert_called_once()
        limited.assert_called_once()

    @patch("discordbot.activity._rate_limited_request", side_effect=RuntimeError)
    def test_exhausted_rate_limit_is_a_request_failure(self, _limited):
        from discordbot.activity import discord_json

        with self.assertRaises(requests.RequestException):
            discord_json("GET", "/channels/1", bot=True)
