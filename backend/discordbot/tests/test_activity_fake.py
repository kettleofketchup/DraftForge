"""The TEST-stack Discord stand-in is inert outside TEST and answers inside it."""

from datetime import date
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser
from discordbot import activity_fake
from discordbot.activity import discord_json
from discordbot.models import DraftActivityChannel
from discordbot.tests.activity_helpers import ClearIntentsMixin
from draft.models import DraftTeam, HeroDraft
from tournament.models import Game, Team, Tournament

DISCORD_ID = "424242424242"
INSTANCE_ID = "fake-instance-test"
OAUTH: dict[str, Any] = {"data": {"code": f"e2e-{DISCORD_ID}"}}
ME: dict[str, Any] = {"headers": {"Authorization": f"Bearer e2e-{DISCORD_ID}"}}
INSTANCE_PATH = f"/applications/123/activity-instances/{INSTANCE_ID}"


def _upstream_response() -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"upstream": True}
    return response


class FakeCleanupMixin:
    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        cache.delete(activity_fake._instance_key(INSTANCE_ID))
        self.addCleanup(cache.delete, activity_fake._instance_key(INSTANCE_ID))  # type: ignore[attr-defined]


@override_settings(TEST=False, SOCIAL_AUTH_DISCORD_KEY=None)
class ActivityFakeInertTests(FakeCleanupMixin, TestCase):
    def test_answers_nothing(self) -> None:
        self.assertIsNone(activity_fake.answer("POST", "/oauth2/token", OAUTH))
        self.assertIsNone(activity_fake.answer("GET", "/users/@me", ME))
        self.assertIsNone(activity_fake.answer("GET", INSTANCE_PATH, {}))

    def test_register_instance_stores_nothing(self) -> None:
        activity_fake.register_instance(INSTANCE_ID, "1", "2", [DISCORD_ID])
        self.assertIsNone(cache.get(activity_fake._instance_key(INSTANCE_ID)))

    def test_client_id_is_the_configured_value(self) -> None:
        self.assertIsNone(activity_fake.client_id())
        with override_settings(SOCIAL_AUTH_DISCORD_KEY="555"):
            self.assertEqual(activity_fake.client_id(), "555")

    @patch("discordbot.activity.requests.request")
    def test_discord_json_still_calls_discord_for_fake_codes(
        self, request: MagicMock
    ) -> None:
        request.return_value = _upstream_response()
        self.assertEqual(
            discord_json("POST", "/oauth2/token", **OAUTH), {"upstream": True}
        )
        request.assert_called_once()

    @override_settings(TEST=True, RELEASE=True)
    def test_release_builds_stay_inert(self) -> None:
        self.assertFalse(activity_fake.active())
        self.assertIsNone(activity_fake.answer("POST", "/oauth2/token", OAUTH))


@override_settings(TEST=True, RELEASE=False, SOCIAL_AUTH_DISCORD_KEY=None)
class ActivityFakeActiveTests(FakeCleanupMixin, TestCase):
    def test_answers_the_three_session_calls(self) -> None:
        self.assertEqual(
            activity_fake.answer("POST", "/oauth2/token", OAUTH),
            {"access_token": f"e2e-{DISCORD_ID}"},
        )
        self.assertEqual(
            activity_fake.answer("GET", "/users/@me", ME), {"id": DISCORD_ID}
        )
        activity_fake.register_instance(INSTANCE_ID, "11", "22", [DISCORD_ID])
        self.assertEqual(
            activity_fake.answer("GET", INSTANCE_PATH, {}),
            {
                "id": INSTANCE_ID,
                "users": [DISCORD_ID],
                "location": {"kind": "gc", "guild_id": "11", "channel_id": "22"},
            },
        )

    def test_real_identities_fall_through(self) -> None:
        self.assertIsNone(
            activity_fake.answer("POST", "/oauth2/token", {"data": {"code": "abc"}})
        )
        self.assertIsNone(
            activity_fake.answer(
                "GET", "/users/@me", {"headers": {"Authorization": "Bearer real"}}
            )
        )
        self.assertIsNone(activity_fake.answer("GET", INSTANCE_PATH, {}))
        self.assertIsNone(activity_fake.answer("GET", "/users/@me/guilds", ME))

    def test_client_id_falls_back_only_when_unconfigured(self) -> None:
        self.assertEqual(activity_fake.client_id(), activity_fake.FAKE_CLIENT_ID)
        with override_settings(SOCIAL_AUTH_DISCORD_KEY="555"):
            self.assertEqual(activity_fake.client_id(), "555")

    @patch("discordbot.activity.requests.request")
    def test_discord_json_short_circuits_fake_calls_only(
        self, request: MagicMock
    ) -> None:
        request.return_value = _upstream_response()
        self.assertEqual(
            discord_json("POST", "/oauth2/token", **OAUTH),
            {"access_token": f"e2e-{DISCORD_ID}"},
        )
        request.assert_not_called()
        self.assertEqual(
            discord_json("POST", "/oauth2/token", data={"code": "real"}),
            {"upstream": True},
        )
        request.assert_called_once()


@override_settings(
    TEST=True,
    RELEASE=False,
    SOCIAL_AUTH_DISCORD_KEY=None,
    DISCORD_ACTIVITY_ENABLED=True,
)
class ActivityFakeSessionTests(ClearIntentsMixin, FakeCleanupMixin, TestCase):
    intent_user_ids: ClassVar[tuple[str, ...]] = (DISCORD_ID,)

    def setUp(self) -> None:
        super().setUp()
        self.user = CustomUser.objects.create_user(
            username="fake-activity", discordId=DISCORD_ID
        )
        self.tournament = Tournament.objects.create(
            name="Fake Activity", date_played=date.today()
        )
        team = Team.objects.create(
            name="A", tournament=self.tournament, captain=self.user
        )
        self.hero = HeroDraft.objects.create(
            game=Game.objects.create(tournament=self.tournament)
        )
        DraftTeam.objects.create(draft=self.hero, tournament_team=team)
        DraftActivityChannel.objects.create(
            guild_id="11", channel_id="22", draft=self.hero
        )

    @patch("discordbot.activity.requests.request")
    @patch("discordbot.activity._rate_limited_request")
    def test_session_verifies_without_reaching_discord(
        self, bot_request: MagicMock, request: MagicMock
    ) -> None:
        activity_fake.register_instance(INSTANCE_ID, "11", "22", [DISCORD_ID])
        response = APIClient().post(
            "/api/discord/activity/session/",
            {
                "code": activity_fake.fake_code(DISCORD_ID),
                "instance_id": INSTANCE_ID,
                "mode": "first",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["tournament_id"], self.tournament.pk)
        self.assertEqual(response.data["scope"], "tournament")
        self.assertEqual(response.data["user"]["pk"], self.user.pk)
        request.assert_not_called()
        bot_request.assert_not_called()
