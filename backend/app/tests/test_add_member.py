"""Tests for add member endpoints (org, league, tournament).

Uses distinct role-based test users to verify the permission matrix:
- orgadmin:      in org.admins M2M
- orgstaff:      in org.staff M2M
- league_admin:  in league.admins M2M (NOT org admin/staff)
- league_user:   regular LeagueUser member (no admin/staff roles)
- regular:       authenticated user with no roles
"""

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, League, LeagueLog, Organization, OrgLog, Tournament
from league.models import LeagueUser
from org.models import OrgUser

LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


class AddOrgMemberTest(TestCase):
    """Test adding members to an organization.

    Permission: has_org_staff_access (owner, org admin, org staff).
    """

    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org")
        self.league = League.objects.create(
            name="Test League", steam_league_id=1, organization=self.org
        )

        # Role-based test users
        self.orgadmin = CustomUser.objects.create_user(
            username="orgadmin", password="test"
        )
        self.orgstaff = CustomUser.objects.create_user(
            username="orgstaff", password="test"
        )
        self.league_admin = CustomUser.objects.create_user(
            username="leagueadmin", password="test"
        )
        self.league_user = CustomUser.objects.create_user(
            username="leagueuser", password="test"
        )
        self.regular = CustomUser.objects.create_user(
            username="regular", password="test"
        )

        # Assign org roles
        self.org.admins.add(self.orgadmin)
        self.org.staff.add(self.orgstaff)

        # Assign league roles (league_admin is NOT an org admin/staff)
        self.league.admins.add(self.league_admin)

        # Create OrgUser memberships (needed for league membership)
        OrgUser.objects.create(user=self.orgadmin, organization=self.org)
        OrgUser.objects.create(user=self.orgstaff, organization=self.org)
        la_org_user = OrgUser.objects.create(
            user=self.league_admin, organization=self.org
        )
        lu_org_user = OrgUser.objects.create(
            user=self.league_user, organization=self.org
        )

        # Create LeagueUser memberships
        LeagueUser.objects.create(
            user=self.league_admin, org_user=la_org_user, league=self.league
        )
        LeagueUser.objects.create(
            user=self.league_user, org_user=lu_org_user, league=self.league
        )

        # Target user to be added
        self.target_user = CustomUser.objects.create_user(
            username="targetuser", password="test"
        )

    def _url(self):
        return f"/api/organizations/{self.org.pk}/members/"

    def _post(self, user, target=None):
        self.client.force_authenticate(user=user)
        target = target or self.target_user
        return self.client.post(self._url(), {"user_id": target.pk}, format="json")

    # --- Permission tests ---

    def test_orgadmin_can_add_org_member(self):
        resp = self._post(self.orgadmin)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            OrgUser.objects.filter(
                user=self.target_user, organization=self.org
            ).exists()
        )

    def test_orgstaff_can_add_org_member(self):
        resp = self._post(self.orgstaff)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            OrgUser.objects.filter(
                user=self.target_user, organization=self.org
            ).exists()
        )

    def test_league_admin_cannot_add_org_member(self):
        """League admin without org admin/staff role gets 403."""
        resp = self._post(self.league_admin)
        self.assertEqual(resp.status_code, 403)

    def test_league_user_cannot_add_org_member(self):
        """Regular league member gets 403."""
        resp = self._post(self.league_user)
        self.assertEqual(resp.status_code, 403)

    def test_regular_user_cannot_add_org_member(self):
        """User with no roles gets 403."""
        resp = self._post(self.regular)
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_cannot_add_org_member(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post(
            self._url(), {"user_id": self.target_user.pk}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    # --- Functional tests ---

    def test_duplicate_returns_400(self):
        OrgUser.objects.create(user=self.target_user, organization=self.org)
        resp = self._post(self.orgadmin)
        self.assertEqual(resp.status_code, 400)

    def test_creates_audit_log(self):
        self._post(self.orgadmin)
        self.assertTrue(
            OrgLog.objects.filter(
                organization=self.org,
                actor=self.orgadmin,
                action="add_member",
                target_user=self.target_user,
            ).exists()
        )

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_discord_auto_create(self):
        """Backend looks up Discord data from its own cache, not client payload."""
        from django.core.cache import cache

        self.org.discord_server_id = "999888777"
        self.org.save()
        cache.set(
            "discord_members_search_999888777",
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

        self.client.force_authenticate(user=self.orgadmin)
        resp = self.client.post(self._url(), {"discord_id": "12345"}, format="json")
        self.assertEqual(resp.status_code, 200)
        new_user = CustomUser.objects.get(discordId="12345")
        self.assertTrue(
            OrgUser.objects.filter(user=new_user, organization=self.org).exists()
        )
        self.assertEqual(new_user.discordUsername, "discorduser")
        self.assertEqual(new_user.nickname, "DiscordNick")

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_discord_id_not_in_cache_returns_404(self):
        from django.core.cache import cache

        cache.clear()
        self.org.discord_server_id = "999888777"
        self.org.save()
        self.client.force_authenticate(user=self.orgadmin)
        resp = self.client.post(
            self._url(), {"discord_id": "nonexistent"}, format="json"
        )
        self.assertEqual(resp.status_code, 404)


class AddLeagueMemberTest(TestCase):
    """Test adding members to a league.

    Permission: has_league_admin_access (league admin, org admin, superuser).
    Org staff alone is NOT sufficient.
    """

    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org")
        self.league = League.objects.create(
            name="Test League", steam_league_id=1, organization=self.org
        )

        # Role-based test users
        self.orgadmin = CustomUser.objects.create_user(
            username="orgadmin", password="test"
        )
        self.orgstaff = CustomUser.objects.create_user(
            username="orgstaff", password="test"
        )
        self.league_admin = CustomUser.objects.create_user(
            username="leagueadmin", password="test"
        )
        self.league_user = CustomUser.objects.create_user(
            username="leagueuser", password="test"
        )
        self.regular = CustomUser.objects.create_user(
            username="regular", password="test"
        )

        # Assign org roles
        self.org.admins.add(self.orgadmin)
        self.org.staff.add(self.orgstaff)

        # Assign league roles
        self.league.admins.add(self.league_admin)

        # Create OrgUser memberships
        OrgUser.objects.create(user=self.orgadmin, organization=self.org)
        OrgUser.objects.create(user=self.orgstaff, organization=self.org)
        la_org_user = OrgUser.objects.create(
            user=self.league_admin, organization=self.org
        )
        lu_org_user = OrgUser.objects.create(
            user=self.league_user, organization=self.org
        )

        # Create LeagueUser memberships
        LeagueUser.objects.create(
            user=self.league_admin, org_user=la_org_user, league=self.league
        )
        LeagueUser.objects.create(
            user=self.league_user, org_user=lu_org_user, league=self.league
        )

        # Target user to be added
        self.target_user = CustomUser.objects.create_user(
            username="targetuser", password="test"
        )

    def _url(self):
        return f"/api/leagues/{self.league.pk}/members/"

    def _post(self, user, target=None):
        self.client.force_authenticate(user=user)
        target = target or self.target_user
        return self.client.post(self._url(), {"user_id": target.pk}, format="json")

    # --- Permission tests ---

    def test_orgadmin_can_add_league_member(self):
        resp = self._post(self.orgadmin)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            LeagueUser.objects.filter(
                user=self.target_user, league=self.league
            ).exists()
        )

    def test_league_admin_can_add_league_member(self):
        """League-specific admin can add members to their league."""
        resp = self._post(self.league_admin)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            LeagueUser.objects.filter(
                user=self.target_user, league=self.league
            ).exists()
        )

    def test_orgstaff_cannot_add_league_member(self):
        """Org staff (without org admin or league admin) gets 403."""
        resp = self._post(self.orgstaff)
        self.assertEqual(resp.status_code, 403)

    def test_league_user_cannot_add_league_member(self):
        """Regular league member gets 403."""
        resp = self._post(self.league_user)
        self.assertEqual(resp.status_code, 403)

    def test_regular_user_cannot_add_league_member(self):
        resp = self._post(self.regular)
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_cannot_add_league_member(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post(
            self._url(), {"user_id": self.target_user.pk}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    # --- Functional tests ---

    def test_creates_org_user_and_league_user(self):
        """Adding to league auto-creates OrgUser if user isn't in the org."""
        resp = self._post(self.orgadmin)
        self.assertEqual(resp.status_code, 200)
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

    def test_existing_org_user_only_creates_league_user(self):
        """If user is already in org, only create LeagueUser."""
        org_user = OrgUser.objects.create(user=self.target_user, organization=self.org)
        resp = self._post(self.orgadmin)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            LeagueUser.objects.filter(
                user=self.target_user, league=self.league, org_user=org_user
            ).exists()
        )

    def test_duplicate_returns_400(self):
        """Adding same user twice returns 400."""
        self._post(self.orgadmin)
        # Create a fresh target for the second attempt
        resp = self._post(self.orgadmin, target=self.target_user)
        self.assertEqual(resp.status_code, 400)

    def test_creates_audit_log(self):
        self._post(self.orgadmin)
        self.assertTrue(
            LeagueLog.objects.filter(
                league=self.league,
                actor=self.orgadmin,
                action="add_member",
                target_user=self.target_user,
            ).exists()
        )


class AddTournamentMemberTest(TestCase):
    """Test adding members to a tournament.

    Permission: has_org_staff_access (owner, org admin, org staff).
    """

    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org")
        self.league = League.objects.create(
            name="Test League", steam_league_id=1, organization=self.org
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=timezone.now(),
            league=self.league,
        )

        # Role-based test users
        self.orgadmin = CustomUser.objects.create_user(
            username="orgadmin", password="test"
        )
        self.orgstaff = CustomUser.objects.create_user(
            username="orgstaff", password="test"
        )
        self.league_admin = CustomUser.objects.create_user(
            username="leagueadmin", password="test"
        )
        self.league_user = CustomUser.objects.create_user(
            username="leagueuser", password="test"
        )
        self.regular = CustomUser.objects.create_user(
            username="regular", password="test"
        )

        # Assign org roles
        self.org.admins.add(self.orgadmin)
        self.org.staff.add(self.orgstaff)

        # Assign league roles
        self.league.admins.add(self.league_admin)

        # Create OrgUser memberships
        OrgUser.objects.create(user=self.orgadmin, organization=self.org)
        OrgUser.objects.create(user=self.orgstaff, organization=self.org)
        la_org_user = OrgUser.objects.create(
            user=self.league_admin, organization=self.org
        )
        lu_org_user = OrgUser.objects.create(
            user=self.league_user, organization=self.org
        )

        # Create LeagueUser memberships
        LeagueUser.objects.create(
            user=self.league_admin, org_user=la_org_user, league=self.league
        )
        LeagueUser.objects.create(
            user=self.league_user, org_user=lu_org_user, league=self.league
        )

        # Target user to be added
        self.target_user = CustomUser.objects.create_user(
            username="targetuser", password="test"
        )

    def _url(self):
        return f"/api/tournaments/{self.tournament.pk}/members/"

    def _post(self, user, target=None):
        self.client.force_authenticate(user=user)
        target = target or self.target_user
        return self.client.post(self._url(), {"user_id": target.pk}, format="json")

    # --- Permission tests ---

    def test_orgadmin_can_add_tournament_member(self):
        resp = self._post(self.orgadmin)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.target_user, self.tournament.users.all())

    def test_orgstaff_can_add_tournament_member(self):
        resp = self._post(self.orgstaff)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.target_user, self.tournament.users.all())

    def test_league_admin_cannot_add_tournament_member(self):
        """League admin without org staff role gets 403."""
        resp = self._post(self.league_admin)
        self.assertEqual(resp.status_code, 403)

    def test_league_user_cannot_add_tournament_member(self):
        resp = self._post(self.league_user)
        self.assertEqual(resp.status_code, 403)

    def test_regular_user_cannot_add_tournament_member(self):
        resp = self._post(self.regular)
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_cannot_add_tournament_member(self):
        self.client.force_authenticate(user=None)
        resp = self.client.post(
            self._url(), {"user_id": self.target_user.pk}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    # --- Functional tests ---

    def test_duplicate_returns_400(self):
        self.tournament.users.add(self.target_user)
        resp = self._post(self.orgadmin)
        self.assertEqual(resp.status_code, 400)
