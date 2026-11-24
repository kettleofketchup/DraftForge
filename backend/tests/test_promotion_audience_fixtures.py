from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from app.models import CustomUser
from discordbot.services.discord_members import get_discord_members_data
from org.models import Organization
from org.promotion.recipients import user_for_guild_member
from tests.data.org_features import FEATURES_ORG
from tests.populate.org_features import (
    populate_org_features_data,
    reset_org_features_data,
)
from tests.populate.promotion_audiences import GUILD_ID
from tests.test_org_features import reset_org_features


class PromotionAudienceFixtureTests(TestCase):
    def setUp(self) -> None:
        self.original_token: str | None = settings.DISCORD_BOT_TOKEN
        self.original_api_url: str = settings.DISCORD_API_BASE_URL
        self.addCleanup(reset_org_features_data)
        populate_org_features_data()

    def test_opt_in_cache_and_ordinary_reset_restores_settings(self) -> None:
        with patch("discordbot.services.discord_members.requests.get") as fetch:
            data = reset_org_features_data(audiences=True)
            self.assertEqual(settings.DISCORD_BOT_TOKEN, "audience-e2e-cache-only")
            self.assertEqual(settings.DISCORD_API_BASE_URL, "http://127.0.0.1:9")
            members = get_discord_members_data(GUILD_ID)
            self.assertEqual(len(members), 11)
            unlinked = data["audiences"]["unlinked"]
            member = next(
                m for m in members if m["user"]["id"] == unlinked["discord_id"]
            )
            first = user_for_guild_member(member)
            self.assertEqual(user_for_guild_member(member).pk, first.pk)
            reseeded = reset_org_features_data(audiences=True)
            self.assertFalse(
                CustomUser.objects.filter(discordId=unlinked["discord_id"]).exists()
            )
            self.assertEqual(reseeded["audiences"], data["audiences"])
            reset_org_features_data()
            self.assertEqual(settings.DISCORD_BOT_TOKEN, self.original_token)
            self.assertEqual(settings.DISCORD_API_BASE_URL, self.original_api_url)
            self.assertIsNone(cache.get(f"discord_members_{GUILD_ID}"))
            self.assertFalse(
                CustomUser.objects.filter(
                    discordId__in=[
                        ref["discord_id"] for ref in data["audiences"].values()
                    ]
                ).exists()
            )
            self.assertIsNone(
                Organization.objects.get(pk=FEATURES_ORG.pk).discord_server_id
            )
            fetch.assert_not_called()

    def test_restores_settings_present_at_opt_in_not_at_module_import(self) -> None:
        with override_settings(
            DISCORD_BOT_TOKEN="fixture-original",
            DISCORD_API_BASE_URL="http://127.0.0.1:8",
        ):
            reset_org_features_data(audiences=True)
            reset_org_features_data()
            self.assertEqual(settings.DISCORD_BOT_TOKEN, "fixture-original")
            self.assertEqual(settings.DISCORD_API_BASE_URL, "http://127.0.0.1:8")

    def test_reset_rejects_non_boolean_audience_option(self) -> None:
        request = APIRequestFactory().post("/", {"audiences": "true"}, format="json")
        with patch("tests.test_org_features.isTestEnvironment", return_value=True):
            response = reset_org_features(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(settings.DISCORD_BOT_TOKEN, self.original_token)

    @override_settings(TEST=False)
    def test_audience_reset_is_not_available_outside_test_environment(self) -> None:
        request = APIRequestFactory().post("/", {"audiences": True}, format="json")
        response = reset_org_features(request)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(settings.DISCORD_BOT_TOKEN, self.original_token)
