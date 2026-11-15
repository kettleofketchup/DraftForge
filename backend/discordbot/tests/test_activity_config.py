"""Runtime application configuration without a frontend image rebuild."""

from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from discordbot.activity_config import activity_config


class ActivityConfigTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @override_settings(
        DISCORD_ACTIVITY_ENABLED=True,
        SOCIAL_AUTH_DISCORD_KEY="123456789012345678",
        SOCIAL_AUTH_DISCORD_SECRET="private-oauth-secret",
        DISCORD_BOT_TOKEN="private-bot-token",
    )
    def test_runtime_id_is_public_but_credentials_are_not(self):
        response = activity_config(self.factory.get("/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"enabled": True, "client_id": "123456789012345678"},
        )
        self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(DISCORD_ACTIVITY_ENABLED=False, SOCIAL_AUTH_DISCORD_KEY="123")
    def test_disabled_activity_has_no_usable_app_id(self):
        response = activity_config(self.factory.get("/"))
        self.assertEqual(response.data, {"enabled": False, "client_id": None})

    @override_settings(DISCORD_ACTIVITY_ENABLED=True, SOCIAL_AUTH_DISCORD_KEY=None)
    def test_enabled_but_unconfigured_has_null_app_id(self):
        response = activity_config(self.factory.get("/"))
        self.assertEqual(response.data, {"enabled": True, "client_id": None})

    @override_settings(DISCORD_ACTIVITY_ENABLED=True, SOCIAL_AUTH_DISCORD_KEY="456")
    def test_updated_runtime_settings_are_reflected_on_next_request(self):
        first = activity_config(self.factory.get("/"))
        with override_settings(SOCIAL_AUTH_DISCORD_KEY="789"):
            second = activity_config(self.factory.get("/"))
        self.assertEqual(first.data["client_id"], "456")
        self.assertEqual(second.data["client_id"], "789")

    @override_settings(DISCORD_ACTIVITY_ENABLED=True, SOCIAL_AUTH_DISCORD_KEY="123")
    def test_existing_stale_authorization_does_not_block_config(self):
        response = activity_config(
            self.factory.get("/", HTTP_AUTHORIZATION="DraftActivity expired")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["client_id"], "123")

    def test_config_route_is_registered(self):
        self.assertEqual(
            reverse("discord-activity-config"), "/api/discord/activity/config/"
        )
