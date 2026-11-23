"""Draft notifications carry a one-click Activity invite when every recipient shares a channel."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser
from discordbot.activity_launch import prepare_notification_invite
from discordbot.models import DraftActivityChannel
from draft.models import Draft, HeroDraft
from events.models import Event
from org.models import Organization
from tournament.models import Game, Tournament

DiscordCall = Callable[..., dict[str, Any]]


def fake_discord(channel_type: int = 2, guild_id: str = "1") -> DiscordCall:
    def call(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if path.endswith("/invites"):
            return {"code": "team-room"}
        if path.startswith("/channels/"):
            return {
                "id": path.rsplit("/", 1)[-1],
                "type": channel_type,
                "guild_id": guild_id,
            }
        raise AssertionError(f"unexpected Discord call {method} {path}")

    return call


@override_settings(
    DISCORD_ACTIVITY_ENABLED=True,
    DISCORD_GUILD_ID="1",
    SOCIAL_AUTH_DISCORD_KEY="9",
    DISCORD_BOT_TOKEN="secret",
)
class NotificationInviteTests(TestCase):
    def setUp(self) -> None:
        owner = CustomUser.objects.create_user(username="invite-owner")
        self.org = Organization.objects.create(name="Invite Org", owner=owner)
        self.tournament = Tournament.objects.create(
            name="Invite Cup", date_played=date.today()
        )
        self.team_draft = Draft.objects.create(tournament=self.tournament)
        self.hero = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.tournament)
        )

    def attach_event(self, voice_channel_id: str = "30") -> Event:
        start = tz.now()
        return Event.objects.create(
            organization=self.org,
            name="Invite Night",
            scheduled_at=start,
            ends_at=start + timedelta(hours=3),
            created_by=self.org.owner,
            tournament=self.tournament,
            event_voice_channel_id=voice_channel_id,
        )

    @patch("discordbot.activity_launch.discord_json")
    def test_team_draft_uses_event_voice_channel_and_binds_it(
        self, api: MagicMock
    ) -> None:
        self.attach_event("30")
        api.side_effect = fake_discord()

        result = prepare_notification_invite("team", self.team_draft.pk)

        self.assertEqual(
            result, {"url": "https://discord.gg/team-room", "channel_id": "30"}
        )
        binding = DraftActivityChannel.objects.get(channel_id="30")
        self.assertEqual(binding.team_draft_id, self.team_draft.pk)
        method, path = api.call_args_list[-1].args
        self.assertEqual((method, path), ("POST", "/channels/30/invites"))
        body = api.call_args_list[-1].kwargs["json"]
        self.assertEqual(body["target_type"], 2)
        self.assertEqual(body["target_application_id"], "9")
        self.assertEqual(body["max_uses"], 0)
        self.assertEqual(body["max_age"], 24 * 60 * 60)

    @patch("discordbot.activity_launch.discord_json")
    def test_channel_bound_to_the_draft_wins_over_event_channel(
        self, api: MagicMock
    ) -> None:
        self.attach_event("30")
        DraftActivityChannel.objects.create(
            guild_id="1", channel_id="40", team_draft=self.team_draft
        )
        api.side_effect = fake_discord()

        result = prepare_notification_invite("team", self.team_draft.pk)

        self.assertEqual(result["channel_id"], "40")
        self.assertFalse(DraftActivityChannel.objects.filter(channel_id="30").exists())

    @patch("discordbot.activity_launch.discord_json")
    def test_hero_draft_never_claims_the_shared_event_channel(
        self, api: MagicMock
    ) -> None:
        self.attach_event("30")

        result = prepare_notification_invite("hero", self.hero.pk)

        self.assertEqual(result, {"url": None, "channel_id": None})
        api.assert_not_called()
        self.assertFalse(DraftActivityChannel.objects.exists())

    @patch("discordbot.activity_launch.discord_json")
    def test_hero_draft_with_its_own_bound_channel_gets_invite(
        self, api: MagicMock
    ) -> None:
        DraftActivityChannel.objects.create(
            guild_id="1", channel_id="50", draft=self.hero
        )
        api.side_effect = fake_discord()

        result = prepare_notification_invite("hero", self.hero.pk)

        self.assertEqual(
            result, {"url": "https://discord.gg/team-room", "channel_id": "50"}
        )

    @patch("discordbot.activity_launch.discord_json")
    def test_several_bound_channels_fall_back_to_per_user_launch(
        self, api: MagicMock
    ) -> None:
        for channel_id in ("50", "51"):
            DraftActivityChannel.objects.create(
                guild_id="1", channel_id=channel_id, draft=self.hero
            )

        self.assertIsNone(prepare_notification_invite("hero", self.hero.pk)["url"])
        api.assert_not_called()

    @patch("discordbot.activity_launch.discord_json")
    def test_no_known_channel_falls_back(self, api: MagicMock) -> None:
        self.assertIsNone(
            prepare_notification_invite("team", self.team_draft.pk)["url"]
        )
        api.assert_not_called()

    @patch("discordbot.activity_launch.discord_json")
    def test_channel_busy_with_another_tournament_falls_back(
        self, api: MagicMock
    ) -> None:
        self.attach_event("30")
        other = Draft.objects.create(
            tournament=Tournament.objects.create(name="Other", date_played=date.today())
        )
        DraftActivityChannel.objects.create(
            guild_id="1", channel_id="30", team_draft=other
        )
        api.side_effect = fake_discord()

        self.assertIsNone(
            prepare_notification_invite("team", self.team_draft.pk)["url"]
        )
        self.assertEqual(
            DraftActivityChannel.objects.get(channel_id="30").team_draft_id, other.pk
        )
        self.assertFalse(any(c.args[0] == "POST" for c in api.call_args_list))

    @patch("discordbot.activity_launch.discord_json")
    def test_non_voice_channel_falls_back_without_binding(self, api: MagicMock) -> None:
        self.attach_event("30")
        api.side_effect = fake_discord(channel_type=0)

        self.assertIsNone(
            prepare_notification_invite("team", self.team_draft.pk)["url"]
        )
        self.assertFalse(DraftActivityChannel.objects.exists())

    @patch("discordbot.activity_launch.discord_json")
    def test_finished_draft_gets_no_invite(self, api: MagicMock) -> None:
        self.attach_event("30")
        Draft.objects.filter(pk=self.team_draft.pk).update(state="completed")

        self.assertIsNone(
            prepare_notification_invite("team", self.team_draft.pk)["url"]
        )
        api.assert_not_called()

    @override_settings(DISCORD_ACTIVITY_ENABLED=False)
    @patch("discordbot.activity_launch.discord_json")
    def test_disabled_activity_gets_no_invite(self, api: MagicMock) -> None:
        self.attach_event("30")

        self.assertIsNone(
            prepare_notification_invite("team", self.team_draft.pk)["url"]
        )
        api.assert_not_called()

    @patch("discordbot.activity_launch.discord_json")
    def test_internal_endpoint_requires_service_token(self, api: MagicMock) -> None:
        response = APIClient().post(
            "/api/internal/discord/activity-notification-invite/",
            {"kind": "team", "draft_id": self.team_draft.pk},
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))
        api.assert_not_called()
