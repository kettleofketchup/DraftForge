"""Tests for enhanced search_users endpoint."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization
from league.models import LeagueUser
from org.models import OrgUser

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test_search_users",
    }
}


@override_settings(CACHES=LOCMEM)
class SearchUsersTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.staff = CustomUser.objects.create_user(
            username="staffuser", password="test123"
        )
        self.client.force_authenticate(user=self.staff)

        # Create org and league
        self.org = Organization.objects.create(name="Test Org")
        self.league = League.objects.create(
            name="Test League", steam_league_id=1, organization=self.org
        )

        # Give staff user org staff access (required by has_org_staff_access)
        self.org.staff.add(self.staff)

        # User in the league (implies org membership)
        self.league_user = CustomUser.objects.create_user(
            username="leagueuser", password="test", discordNickname="LeagueJohn"
        )
        org_user = OrgUser.objects.create(user=self.league_user, organization=self.org)
        LeagueUser.objects.create(
            user=self.league_user, org_user=org_user, league=self.league
        )

        # User in org only
        self.org_only_user = CustomUser.objects.create_user(
            username="orgonlyuser", password="test", discordNickname="OrgJohn"
        )
        OrgUser.objects.create(user=self.org_only_user, organization=self.org)

        # User in a different org
        self.other_org = Organization.objects.create(name="Other Org")
        self.other_org_user = CustomUser.objects.create_user(
            username="otherorguser", password="test", discordNickname="OtherJohn"
        )
        OrgUser.objects.create(user=self.other_org_user, organization=self.other_org)

        # Global user (no org)
        self.global_user = CustomUser.objects.create_user(
            username="globaluser", password="test", discordNickname="GlobalJohn"
        )

        # User with steam ID. CustomUser.save() syncs steamid <-> steam_account_id
        # via STEAM_ID_64_BASE (76561197960265728), so we set steam_account_id and
        # let save() derive the canonical 64-bit value. Setting both to inconsistent
        # values previously slipped past a dead save() override; T1.5 resurrected
        # the sync, so the derived steamid is now authoritative.
        self.steam_user = CustomUser.objects.create_user(
            username="steamjohn",
            password="test",
            steam_account_id=39735273,
        )
        self.steam_user.refresh_from_db()  # pick up save()'s derived steamid

    def test_search_by_steamid(self):
        resp = self.client.get(
            "/api/users/search/", {"q": str(self.steam_user.steamid)}
        )
        self.assertEqual(resp.status_code, 200)
        pks = [u["pk"] for u in resp.data]
        self.assertIn(self.steam_user.pk, pks)

    def test_search_by_steam_account_id(self):
        resp = self.client.get("/api/users/search/", {"q": "39735273"})
        self.assertEqual(resp.status_code, 200)
        pks = [u["pk"] for u in resp.data]
        self.assertIn(self.steam_user.pk, pks)

    def test_membership_annotation_league(self):
        resp = self.client.get(
            "/api/users/search/",
            {"q": "leagueuser", "org_id": self.org.pk, "league_id": self.league.pk},
        )
        self.assertEqual(resp.status_code, 200)
        user_data = resp.data[0]
        self.assertEqual(user_data["membership"], "league")
        self.assertEqual(user_data["membership_label"], "Test League")

    def test_membership_annotation_org(self):
        resp = self.client.get(
            "/api/users/search/",
            {"q": "orgonlyuser", "org_id": self.org.pk, "league_id": self.league.pk},
        )
        self.assertEqual(resp.status_code, 200)
        user_data = resp.data[0]
        self.assertEqual(user_data["membership"], "org")
        self.assertEqual(user_data["membership_label"], "Test Org")

    def test_membership_annotation_other_org(self):
        resp = self.client.get(
            "/api/users/search/",
            {"q": "otherorguser", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 200)
        user_data = resp.data[0]
        self.assertEqual(user_data["membership"], "other_org")
        self.assertEqual(user_data["membership_label"], "Other Org")

    def test_membership_annotation_global(self):
        resp = self.client.get(
            "/api/users/search/",
            {"q": "globaluser", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 200)
        user_data = resp.data[0]
        self.assertIsNone(user_data["membership"])

    def test_no_context_params_still_works(self):
        resp = self.client.get("/api/users/search/", {"q": "leagueuser"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertNotIn("membership", resp.data[0])

    def test_unauthenticated_returns_401(self):
        self.client.logout()
        resp = self.client.get("/api/users/search/", {"q": "test"})
        self.assertIn(resp.status_code, [401, 403])

    def test_non_staff_cannot_use_org_context(self):
        """Any authenticated user can search, but org_id requires org staff access."""
        regular = CustomUser.objects.create_user(username="regular", password="test123")
        self.client.force_authenticate(user=regular)
        # Search without org_id — should work
        resp = self.client.get("/api/users/search/", {"q": "leagueuser"})
        self.assertEqual(resp.status_code, 200)
        # Search with org_id — should be denied (no org staff access)
        resp = self.client.get(
            "/api/users/search/",
            {"q": "leagueuser", "org_id": self.org.pk},
        )
        self.assertEqual(resp.status_code, 403)

    def test_short_query_returns_400(self):
        resp = self.client.get("/api/users/search/", {"q": "ab"})
        self.assertEqual(resp.status_code, 400)

    def test_max_20_results(self):
        for i in range(25):
            CustomUser.objects.create_user(
                username=f"bulkuser{i}", password="test", discordNickname=f"Bulk{i}"
            )
        resp = self.client.get("/api/users/search/", {"q": "bulk"})
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(resp.data), 20)

    def test_org_search_matches_that_orgs_guild_nickname(self):
        dragon = CustomUser.objects.create_user(
            username="dc_account", password="test", discordNickname="Gwaihir"
        )
        OrgUser.objects.create(
            user=dragon, organization=self.org, guild_nickname="DragonClaw"
        )
        resp = self.client.get(
            "/api/users/search/", {"q": "dragon", "org_id": self.org.pk}
        )
        self.assertEqual(resp.status_code, 200)
        rows = {u["pk"]: u for u in resp.data}
        self.assertIn(dragon.pk, rows)
        self.assertEqual(rows[dragon.pk]["guildNickname"], "DragonClaw")

    def test_org_search_guild_nickname_null_for_non_members(self):
        resp = self.client.get(
            "/api/users/search/", {"q": "globaluser", "org_id": self.org.pk}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data[0]["guildNickname"])

    def test_other_orgs_guild_nickname_not_matched(self):
        OrgUser.objects.filter(user=self.other_org_user).update(
            guild_nickname="Featherfall"
        )
        resp = self.client.get(
            "/api/users/search/", {"q": "featherfall", "org_id": self.org.pk}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])

    def test_global_search_matches_discord_global_name(self):
        self.global_user.discordNickname = "Windlord"
        self.global_user.save()
        resp = self.client.get("/api/users/search/", {"q": "windlord"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([u["pk"] for u in resp.data], [self.global_user.pk])

    def test_site_nickname_is_not_searched(self):
        resp = self.client.get("/api/users/search/", {"q": "siteonly"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])

    def test_non_numeric_org_id_falls_back_to_global(self):
        resp = self.client.get(
            "/api/users/search/", {"q": "globaluser", "org_id": "abc"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([u["pk"] for u in resp.data], [self.global_user.pk])

    def test_plain_query_works(self):
        resp = self.client.get("/api/users/search/", {"q": "abc"})
        self.assertEqual(resp.status_code, 200)

    def test_non_staff_org_search_is_forbidden(self):
        regular = CustomUser.objects.create_user(username="regular2", password="x")
        self.client.force_authenticate(user=regular)
        resp = self.client.get(
            "/api/users/search/", {"q": "leagueuser", "org_id": self.org.pk}
        )
        self.assertEqual(resp.status_code, 403)

    def test_org_members_ranked_before_slice(self):
        for i in range(21):
            CustomUser.objects.create_user(username=f"aaarank{i:02d}", password="test")
        member = CustomUser.objects.create_user(username="zzzrank", password="test")
        OrgUser.objects.create(user=member, organization=self.org)
        resp = self.client.get(
            "/api/users/search/", {"q": "rank", "org_id": self.org.pk}
        )
        self.assertEqual(resp.status_code, 200)
        pks = [u["pk"] for u in resp.data]
        self.assertEqual(len(pks), 20)
        self.assertEqual(pks[0], member.pk)
