"""Tests for add member endpoints (league, tournament).

Uses distinct role-based test users to verify the permission matrix:
- orgadmin:      in org.admins M2M
- orgstaff:      in org.staff M2M
- league_admin:  in league.admins M2M (NOT org admin/staff)
- league_user:   regular LeagueUser member (no admin/staff roles)
- regular:       authenticated user with no roles
"""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser, Tournament
from league.models import League, LeagueLog, LeagueUser
from org.models import Organization, OrgUser


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

    def test_league_admin_can_add_tournament_member(self):
        """League admins are league staff and can add tournament members."""
        resp = self._post(self.league_admin)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.target_user, self.tournament.users.all())

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


NICK_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test_add_member_guild_nick",
    }
}
GUILD = "999888777"
DISCORD_ID = "424242"


def _discord_member(
    discord_id: str = DISCORD_ID, nick: str | None = "DragonClaw"
) -> dict:
    return {
        "user": {
            "id": discord_id,
            "username": "dragonclaw_dc",
            "global_name": "GwaihirTheWindlord",
            "avatar": None,
        },
        "nick": nick,
    }


@override_settings(CACHES=NICK_CACHE)
class AddMemberGuildNicknameTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.admin = CustomUser.objects.create_user(username="gn_admin", password="x")
        self.org = Organization.objects.create(name="Nick Org", discord_server_id=GUILD)
        self.org.admins.add(self.admin)
        self.league = League.objects.create(
            name="Nick League", steam_league_id=77, organization=self.org
        )
        self.tournament = Tournament.objects.create(
            name="Nick Tournament", date_played=timezone.now(), league=self.league
        )
        self.client.force_authenticate(user=self.admin)

    def _warm(self, *members: dict) -> None:
        cache.set(f"discord_members_search_{GUILD}", list(members), timeout=3600)

    def _existing(self) -> CustomUser:
        return CustomUser.objects.create_user(
            username="dc_existing", password="x", discordId=DISCORD_ID
        )

    def _org_nick(self, user: CustomUser) -> str | None:
        return OrgUser.objects.get(user=user, organization=self.org).guild_nickname

    def test_league_add_by_user_id_seeds_nickname(self) -> None:
        user = self._existing()
        self._warm(_discord_member())
        resp = self.client.post(
            f"/api/leagues/{self.league.pk}/members/",
            {"user_id": user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            LeagueUser.objects.filter(user=user, league=self.league).exists()
        )
        self.assertEqual(self._org_nick(user), "DragonClaw")

    def test_league_add_by_discord_id_seeds_nickname(self) -> None:
        self._warm(_discord_member())
        resp = self.client.post(
            f"/api/leagues/{self.league.pk}/members/",
            {"discord_id": DISCORD_ID},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        user = CustomUser.objects.get(discordId=DISCORD_ID)
        self.assertTrue(
            LeagueUser.objects.filter(user=user, league=self.league).exists()
        )
        self.assertEqual(self._org_nick(user), "DragonClaw")

    def test_league_add_keeps_existing_org_nickname(self) -> None:
        user = self._existing()
        OrgUser.objects.create(
            user=user, organization=self.org, guild_nickname="Synced"
        )
        self._warm(_discord_member())
        resp = self.client.post(
            f"/api/leagues/{self.league.pk}/members/",
            {"user_id": user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._org_nick(user), "Synced")

    def test_league_add_invalidates_user_after_commit(self) -> None:
        user = self._existing()
        self._warm(_discord_member())
        with mock.patch("league.views_admin_team.invalidate_after_commit") as spy:
            self.client.post(
                f"/api/leagues/{self.league.pk}/members/",
                {"user_id": user.pk},
                format="json",
            )
        spy.assert_called()
        self.assertTrue(
            any(
                isinstance(a, CustomUser) and a.pk == user.pk
                for call in spy.call_args_list
                for a in call.args
            )
        )

    def test_tournament_add_by_user_id(self) -> None:
        user = self._existing()
        resp = self.client.post(
            f"/api/tournaments/{self.tournament.pk}/members/",
            {"user_id": user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(user, self.tournament.users.all())

    def test_tournament_add_by_discord_id(self) -> None:
        self._warm(_discord_member())
        resp = self.client.post(
            f"/api/tournaments/{self.tournament.pk}/members/",
            {"discord_id": DISCORD_ID},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        user = CustomUser.objects.get(discordId=DISCORD_ID)
        self.assertIn(user, self.tournament.users.all())
