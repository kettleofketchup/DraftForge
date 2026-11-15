"""Notification launch/join routing never chooses the DM's channel."""

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import requests
from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser, Draft, DraftTeam, Game, HeroDraft, Team, Tournament
from discordbot.activity_ids import decode_draft_launch
from discordbot.activity_launch import prepare_activity_launch
from discordbot.activity_launch_gateway import handle_draft_launch
from discordbot.models import DraftActivityChannel


@override_settings(
    DISCORD_ACTIVITY_ENABLED=True,
    DISCORD_GUILD_ID="1",
    SOCIAL_AUTH_DISCORD_KEY="9",
    DISCORD_BOT_TOKEN="secret",
)
class ActivityLaunchTests(TestCase):
    def setUp(self):
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

    def discord_responses(self, channel="20"):
        return [
            {"channel_id": channel},
            {"id": channel, "type": 2, "guild_id": "1"},
            {"channel_id": channel},
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
    def test_move_during_preparation_does_not_bind_old_channel(self, api):
        api.side_effect = self.discord_responses()[:2] + [{"channel_id": "21"}]
        result = prepare_activity_launch("101", "hero", self.hero.pk)
        self.assertFalse(result["success"])
        self.assertIn("changed", result["content"])
        self.assertFalse(DraftActivityChannel.objects.exists())

    @patch("discordbot.activity_launch.discord_json")
    def test_nonvoice_or_wrong_guild_is_rejected(self, api):
        for channel in [{"type": 0, "guild_id": "1"}, {"type": 2, "guild_id": "99"}]:
            api.side_effect = [{"channel_id": "20"}, channel]
            self.assertFalse(
                prepare_activity_launch("101", "hero", self.hero.pk)["success"]
            )
        self.assertFalse(DraftActivityChannel.objects.exists())

    @patch("discordbot.activity_launch.discord_json")
    def test_conflicting_binding_is_never_replaced_even_after_completion(self, api):
        binding = DraftActivityChannel.objects.create(
            guild_id="1", channel_id="20", team_draft=self.team_draft
        )
        for state in ["drafting", "completed"]:
            self.team_draft.state = state
            self.team_draft.save()
            api.side_effect = self.discord_responses()[:3]
            result = prepare_activity_launch("101", "hero", self.hero.pk)
            self.assertFalse(result["success"])
            self.assertIn("another draft", result["content"])
            binding.refresh_from_db()
            self.assertEqual(binding.team_draft_id, self.team_draft.pk)
        self.assertEqual(api.call_count, 6)

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
    @patch("discordbot.activity_launch_gateway.prepare_launch_payload")
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
