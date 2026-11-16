from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser, Organization
from org.activity import guild_sync_lock
from org.models import OrgUser

LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "discord-search-test",
    }
}

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


@override_settings(CACHES=LOCMEM_CACHE)
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


@override_settings(CACHES=LOCMEM_CACHE)
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


@override_settings(CACHES=LOCMEM_CACHE)
class RefreshDiscordMembersNameSyncTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        cache.clear()
        self.guild = "999888777"
        self.org = Organization.objects.create(
            name="Test Org", discord_server_id=self.guild
        )
        self.sibling = Organization.objects.create(
            name="Sibling Org", discord_server_id=self.guild
        )
        self.other = Organization.objects.create(
            name="Other Guild Org", discord_server_id="555"
        )
        self.staff = CustomUser.objects.create_user(
            username="staffuser", password="test123"
        )
        OrgUser.objects.create(user=self.staff, organization=self.org)
        self.org.staff.add(self.staff)
        self.client.force_authenticate(user=self.staff)

    def _refresh(self):
        return self.client.post(
            "/api/discord/refresh-discord-members/",
            {"org_id": self.org.pk},
            format="json",
        )

    @patch("discordbot.services.users.apply_guild_member_names")
    @patch("discordbot.services.users.get_discord_members_data")
    def test_refresh_forces_refetch_and_applies_to_every_guild_org(
        self, mock_fetch, mock_apply
    ) -> None:
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS
        cache.set(f"discord_members_{self.guild}", [{"old": "data"}], timeout=3600)

        resp = self._refresh()

        self.assertEqual(resp.status_code, 200)
        mock_fetch.assert_called_once_with(guild_id=self.guild, force=True)
        mock_apply.assert_called_once()
        args, kwargs = mock_apply.call_args
        self.assertEqual(args[0], self.guild)
        self.assertEqual(sorted(args[1]), sorted([self.org.pk, self.sibling.pk]))
        self.assertEqual([m.discord_id for m in args[2]], ["111", "222", "333"])
        self.assertTrue(kwargs["complete"])
        self.assertIsInstance(kwargs["fetched_at"], float)
        self.assertIsNone(cache.get(f"discord_name_sync_guild_{self.guild}"))

    @patch("discordbot.services.users.get_discord_members_data")
    def test_refresh_writes_server_nicknames_and_global_names(self, mock_fetch) -> None:
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS
        john = CustomUser.objects.create_user(
            username="john", password="x", discordId="111"
        )
        sibling_member = OrgUser.objects.create(user=john, organization=self.sibling)

        resp = self._refresh()

        self.assertEqual(resp.status_code, 200)
        sibling_member.refresh_from_db()
        self.assertEqual(sibling_member.guild_nickname, "JohnnyD")
        self.assertEqual(
            CustomUser.objects.nocache().get(pk=john.pk).discordNickname, "John D"
        )

    @patch("discordbot.services.users.apply_guild_member_names")
    @patch("discordbot.services.users.get_discord_members_data")
    def test_refresh_with_guild_lock_held_repaves_search_cache_but_skips_apply(
        self, mock_fetch, mock_apply
    ) -> None:
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS
        self.assertTrue(guild_sync_lock(self.guild))

        resp = self._refresh()

        self.assertEqual(resp.status_code, 200)
        mock_fetch.assert_called_once_with(guild_id=self.guild, force=True)
        self.assertEqual(len(cache.get(f"discord_members_search_{self.guild}")), 3)
        mock_apply.assert_not_called()
        self.assertIsNotNone(cache.get(f"discord_name_sync_guild_{self.guild}"))

    @patch("discordbot.services.users.apply_guild_member_names")
    @patch("discordbot.services.users.get_discord_members_data")
    def test_refresh_fetch_failure_releases_lock(self, mock_fetch, mock_apply) -> None:
        mock_fetch.side_effect = Exception("Discord API error")

        resp = self._refresh()

        self.assertEqual(resp.status_code, 502)
        mock_apply.assert_not_called()
        self.assertIsNone(cache.get(f"discord_name_sync_guild_{self.guild}"))

    @patch("discordbot.services.users.touch_org_activity")
    @patch("discordbot.services.users.get_discord_members_data")
    def test_refresh_touches_requesting_org(self, mock_fetch, mock_touch) -> None:
        mock_fetch.return_value = []

        self._refresh()

        mock_touch.assert_called_once()
        args, kwargs = mock_touch.call_args
        self.assertEqual(args[1], self.org.pk)
        self.assertEqual(kwargs["guild_id"], self.guild)


@override_settings(CACHES=LOCMEM_CACHE)
class DiscordMemberActivityTouchTest(TestCase):
    def setUp(self) -> None:
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

    def _assert_touched(self, mock_touch) -> None:
        mock_touch.assert_called_once()
        args, kwargs = mock_touch.call_args
        self.assertEqual(args[1], self.org.pk)
        self.assertEqual(kwargs["guild_id"], "999888777")

    @patch("discordbot.services.users.touch_org_activity")
    @patch("discordbot.services.users.get_discord_members_data")
    def test_search_touches_org_activity(self, mock_fetch, mock_touch) -> None:
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self._assert_touched(mock_touch)

    @patch("discordbot.services.users.touch_org_activity")
    @patch("discordbot.services.users.get_discord_members_data")
    def test_get_org_members_touches_org_activity(self, mock_fetch, mock_touch) -> None:
        mock_fetch.return_value = MOCK_DISCORD_MEMBERS
        resp = self.client.get(
            f"/api/discord/organizations/{self.org.pk}/discord-members/"
        )
        self.assertEqual(resp.status_code, 200)
        self._assert_touched(mock_touch)

    @patch("discordbot.services.users.touch_org_activity")
    def test_search_non_staff_does_not_touch(self, mock_touch) -> None:
        regular = CustomUser.objects.create_user(username="regular", password="x")
        self.client.force_authenticate(user=regular)
        resp = self.client.get(
            "/api/discord/search-discord-members/",
            {"q": "john", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 403)
        mock_touch.assert_not_called()
