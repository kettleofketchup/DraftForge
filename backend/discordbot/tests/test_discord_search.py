from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, Organization
from org.models import OrgUser

MOCK_DISCORD_MEMBERS = [
    {
        "user": {
            "id": "111",
            "username": "johndiscord",
            "global_name": "John D",
            "avatar": "abc",
        },
        "nick": "JohnnyD",
        "joined_at": "2024-01-01T00:00:00+00:00",
    },
    {
        "user": {
            "id": "222",
            "username": "janediscord",
            "global_name": "Jane D",
            "avatar": None,
        },
        "nick": None,
        "joined_at": "2024-01-01T00:00:00+00:00",
    },
    {
        "user": {
            "id": "333",
            "username": "bobdiscord",
            "global_name": "Bob",
            "avatar": "def",
        },
        "nick": "BobNick",
        "joined_at": "2024-01-01T00:00:00+00:00",
    },
]


class SearchDiscordMembersTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        cache.clear()

        self.org = Organization.objects.create(
            name="Test Org", discord_server_id="999888777"
        )

        # Staff user with org access
        self.staff = CustomUser.objects.create_user(
            username="staffuser", password="test123"
        )
        OrgUser.objects.create(user=self.staff, organization=self.org)
        self.org.staff.add(self.staff)
        self.client.force_authenticate(user=self.staff)

        # User with linked Discord account
        self.linked_user = CustomUser.objects.create_user(
            username="linkeduser", password="test", discordId="111"
        )

    @patch("discordbot.services.users.get_discord_members_data")
    def test_search_discord_members(self, mock_fetch):
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["user"]["username"], "johndiscord")
        self.assertTrue(results[0]["has_site_account"])
        self.assertEqual(results[0]["site_user_pk"], self.linked_user.pk)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_search_no_site_account(self, mock_fetch):
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "jane", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["has_site_account"])
        self.assertIsNone(results[0]["site_user_pk"])

    @patch("discordbot.services.users.get_discord_members_data")
    def test_search_uses_redis_cache(self, mock_fetch):
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS

        # First call populates cache
        self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        # Second call should use cache
        self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "bob", "org_id": self.org.pk},
        )
        # get_discord_members_data should only be called once (cache hit on second)
        self.assertEqual(mock_fetch.call_count, 1)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_search_min_3_chars(self, mock_fetch):
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "jo", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 400)

    def test_search_requires_org_id(self):
        resp = self.client.get("/api/discord/search-discord-members/", {"q": "john"})
        self.assertEqual(resp.status_code, 400)

    def test_search_no_discord_server(self):
        org_no_discord = Organization.objects.create(name="No Discord Org")
        org_no_discord.staff.add(self.staff)
        OrgUser.objects.create(user=self.staff, organization=org_no_discord)
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": org_no_discord.pk},
        )
        self.assertEqual(resp.status_code, 400)

    def test_search_unauthenticated_returns_401(self):
        self.client.logout()
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        self.assertIn(resp.status_code, [401, 403])

    def test_search_non_staff_returns_403(self):
        regular = CustomUser.objects.create_user(username="regular", password="test123")
        self.client.force_authenticate(user=regular)
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 403)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_search_handles_discord_api_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("Discord API error")
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 502)


class RefreshDiscordMembersTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        cache.clear()

        self.org = Organization.objects.create(
            name="Test Org", discord_server_id="999888777"
        )
        self.staff = CustomUser.objects.create_user(
            username="staffuser", password="test123"
        )
        OrgUser.objects.create(user=self.staff, organization=self.org)
        self.org.staff.add(self.staff)
        self.client.force_authenticate(user=self.staff)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_refresh_clears_and_repopulates(self, mock_fetch):
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS

        # Pre-populate cache
        cache_key = f"discord_members_{self.org.discord_server_id}"
        cache.set(cache_key, [{"old": "data"}], timeout=3600)

        resp = self.client.post(
            "/api/discord/refresh-discord-members/",
            {"org_id": self.org.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["refreshed"])
        self.assertEqual(data["count"], 3)

        # Verify cache was repopulated (uses search-specific key)
        search_cache_key = f"discord_members_search_{self.org.discord_server_id}"
        cached = cache.get(search_cache_key)
        self.assertEqual(len(cached), 3)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_refresh_rate_limited(self, mock_fetch):
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS
        # First refresh should succeed
        resp = self.client.post(
            "/api/discord/refresh-discord-members/",
            {"org_id": self.org.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        # Second immediate refresh should be rate limited
        resp = self.client.post(
            "/api/discord/refresh-discord-members/",
            {"org_id": self.org.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 429)

    def test_refresh_non_staff_returns_403(self):
        regular = CustomUser.objects.create_user(username="regular", password="test123")
        self.client.force_authenticate(user=regular)
        resp = self.client.post(
            "/api/discord/refresh-discord-members/",
            {"org_id": self.org.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    @patch("discordbot.services.users.get_discord_members_data")
    def test_refresh_handles_discord_api_error(self, mock_fetch):
        mock_fetch.side_effect = Exception("Discord API error")
        resp = self.client.post(
            "/api/discord/refresh-discord-members/",
            {"org_id": self.org.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 502)
