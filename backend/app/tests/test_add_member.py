"""Tests for add member endpoints (org, league, tournament)."""

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization, OrgLog, Tournament
from league.models import LeagueUser
from org.models import OrgUser

LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


class AddOrgMemberTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org")
        self.admin = CustomUser.objects.create_user(
            username="admin", password="test123"
        )
        self.org.admins.add(self.admin)
        OrgUser.objects.create(user=self.admin, organization=self.org)
        self.client.force_authenticate(user=self.admin)

        self.target_user = CustomUser.objects.create_user(
            username="newmember", password="test"
        )

    def test_add_org_member(self):
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            OrgUser.objects.filter(
                user=self.target_user, organization=self.org
            ).exists()
        )

    def test_add_org_member_duplicate(self):
        OrgUser.objects.create(user=self.target_user, organization=self.org)
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_add_org_member_from_discord_id(self):
        """Backend looks up Discord data from its own cache, not client payload."""
        from django.core.cache import cache

        # Pre-populate Discord member cache for this org
        self.org.discord_server_id = "999888777"
        self.org.save()
        cache_key = "discord_members_search_999888777"
        cache.set(
            cache_key,
            [
                {
                    "user": {
                        "id": "12345",
                        "username": "discorduser",
                        "global_name": "Discord User",
                        "avatar": "abc123",
                    },
                    "nick": "DiscordNick",
                }
            ],
            timeout=3600,
        )

        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"discord_id": "12345"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        new_user = CustomUser.objects.get(discordId="12345")
        self.assertTrue(
            OrgUser.objects.filter(user=new_user, organization=self.org).exists()
        )
        # Verify user was created with correct data from cache
        self.assertEqual(new_user.discordUsername, "discorduser")
        self.assertEqual(new_user.nickname, "DiscordNick")

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_add_org_member_discord_id_not_in_cache(self):
        """Reject discord_id if member not found in org's Discord cache."""
        from django.core.cache import cache

        cache.clear()  # Ensure cache is empty
        self.org.discord_server_id = "999888777"
        self.org.save()
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"discord_id": "nonexistent"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_add_org_member_non_staff_returns_403(self):
        regular = CustomUser.objects.create_user(username="regular", password="test123")
        self.client.force_authenticate(user=regular)
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_add_org_member_creates_audit_log(self):
        self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertTrue(
            OrgLog.objects.filter(
                organization=self.org,
                actor=self.admin,
                action="add_member",
            ).exists()
        )


class AddLeagueMemberTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org")
        self.league = League.objects.create(
            name="Test League", steam_league_id=1, organization=self.org
        )
        self.admin = CustomUser.objects.create_user(
            username="admin", password="test123"
        )
        self.org.admins.add(self.admin)
        OrgUser.objects.create(user=self.admin, organization=self.org)
        self.client.force_authenticate(user=self.admin)

        self.target_user = CustomUser.objects.create_user(
            username="newmember", password="test"
        )

    def test_add_league_member_creates_org_user_too(self):
        resp = self.client.post(
            f"/api/leagues/{self.league.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        # Should create both OrgUser and LeagueUser
        self.assertTrue(
            OrgUser.objects.filter(
                user=self.target_user, organization=self.org
            ).exists()
        )
        self.assertTrue(
            LeagueUser.objects.filter(
                user=self.target_user, league=self.league
            ).exists()
        )

    def test_add_league_member_existing_org_user(self):
        # Already in org, just add to league
        org_user = OrgUser.objects.create(user=self.target_user, organization=self.org)
        resp = self.client.post(
            f"/api/leagues/{self.league.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            LeagueUser.objects.filter(
                user=self.target_user, league=self.league, org_user=org_user
            ).exists()
        )


class AddTournamentMemberTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org")
        self.league = League.objects.create(
            name="Test League", steam_league_id=1, organization=self.org
        )
        self.admin = CustomUser.objects.create_user(
            username="admin", password="test123", is_staff=True
        )
        self.org.admins.add(self.admin)
        OrgUser.objects.create(user=self.admin, organization=self.org)
        self.client.force_authenticate(user=self.admin)

        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=timezone.now(),
            league=self.league,
        )
        self.target_user = CustomUser.objects.create_user(
            username="newplayer", password="test"
        )

    def test_add_tournament_member(self):
        resp = self.client.post(
            f"/api/tournaments/{self.tournament.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.target_user, self.tournament.users.all())

    def test_add_tournament_member_duplicate(self):
        self.tournament.users.add(self.target_user)
        resp = self.client.post(
            f"/api/tournaments/{self.tournament.pk}/members/",
            {"user_id": self.target_user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
