"""Tests for enhanced search_users endpoint."""

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization
from league.models import LeagueUser
from org.models import OrgUser


class SearchUsersTest(TestCase):
    def setUp(self):
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
            username="leagueuser", password="test", nickname="LeagueJohn"
        )
        org_user = OrgUser.objects.create(user=self.league_user, organization=self.org)
        LeagueUser.objects.create(
            user=self.league_user, org_user=org_user, league=self.league
        )

        # User in org only
        self.org_only_user = CustomUser.objects.create_user(
            username="orgonlyuser", password="test", nickname="OrgJohn"
        )
        OrgUser.objects.create(user=self.org_only_user, organization=self.org)

        # User in a different org
        self.other_org = Organization.objects.create(name="Other Org")
        self.other_org_user = CustomUser.objects.create_user(
            username="otherorguser", password="test", nickname="OtherJohn"
        )
        OrgUser.objects.create(user=self.other_org_user, organization=self.other_org)

        # Global user (no org)
        self.global_user = CustomUser.objects.create_user(
            username="globaluser", password="test", nickname="GlobalJohn"
        )

        # User with steam ID
        self.steam_user = CustomUser.objects.create_user(
            username="steamjohn",
            password="test",
            steamid=76561198000000001,
            steam_account_id=39735273,
        )

    def test_search_by_steamid(self):
        resp = self.client.get("/api/users/search/", {"q": "76561198000000001"})
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
                username=f"bulkuser{i}", password="test", nickname=f"Bulk{i}"
            )
        resp = self.client.get("/api/users/search/", {"q": "bulk"})
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(resp.data), 20)
