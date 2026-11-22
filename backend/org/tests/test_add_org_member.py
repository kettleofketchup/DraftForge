"""Tests for the org add-member and org-user update endpoints.

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
from rest_framework.test import APIClient

from app.models import CustomUser
from league.models import League, LeagueUser
from org.models import Organization, OrgLog, OrgUser

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
        self.assertEqual(new_user.discordNickname, "Discord User")

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_discord_id_not_in_cache_returns_404(self):
        cache.clear()
        self.org.discord_server_id = "999888777"
        self.org.save()
        self.client.force_authenticate(user=self.orgadmin)
        resp = self.client.post(
            self._url(), {"discord_id": "nonexistent"}, format="json"
        )
        self.assertEqual(resp.status_code, 404)


NICK_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test_add_org_member_guild_nick",
    }
}
GUILD = "999888777"
DISCORD_ID = "424242"


def _member(discord_id: str = DISCORD_ID, nick: str | None = "DragonClaw") -> dict:
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
class OrgAddMemberGuildNicknameTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.admin = CustomUser.objects.create_user(username="gn_admin", password="x")
        self.org = Organization.objects.create(name="Nick Org", discord_server_id=GUILD)
        self.org.admins.add(self.admin)
        self.client.force_authenticate(user=self.admin)

    def _warm(self, *members: dict) -> None:
        cache.set(f"discord_members_search_{GUILD}", list(members), timeout=3600)

    def _existing(self) -> CustomUser:
        return CustomUser.objects.create_user(
            username="dc_existing", password="x", discordId=DISCORD_ID
        )

    def _org_nick(self, user: CustomUser) -> str | None:
        return OrgUser.objects.get(user=user, organization=self.org).guild_nickname

    def test_org_add_new_user_seeds_nickname(self) -> None:
        self._warm(_member())
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"discord_id": DISCORD_ID},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        user = CustomUser.objects.get(discordId=DISCORD_ID)
        self.assertEqual(self._org_nick(user), "DragonClaw")

    def test_org_add_existing_user_by_discord_id_seeds_nickname(self) -> None:
        user = self._existing()
        self._warm(_member())
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"discord_id": DISCORD_ID},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._org_nick(user), "DragonClaw")

    def test_org_add_existing_user_by_user_id_seeds_nickname(self) -> None:
        user = self._existing()
        self._warm(_member())
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"user_id": user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._org_nick(user), "DragonClaw")

    def test_org_add_whitespace_nick_is_none(self) -> None:
        user = self._existing()
        self._warm(_member(nick="   "))
        self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"user_id": user.pk},
            format="json",
        )
        self.assertIsNone(self._org_nick(user))

    def test_org_add_cold_cache_leaves_none_without_fetch(self) -> None:
        user = self._existing()
        with mock.patch(
            "discordbot.services.discord_members.get_discord_members_data"
        ) as fetch:
            resp = self.client.post(
                f"/api/organizations/{self.org.pk}/members/",
                {"user_id": user.pk},
                format="json",
            )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self._org_nick(user))
        fetch.assert_not_called()

    def test_org_add_already_member_400_no_write(self) -> None:
        user = self._existing()
        OrgUser.objects.create(user=user, organization=self.org)
        self._warm(_member())
        resp = self.client.post(
            f"/api/organizations/{self.org.pk}/members/",
            {"user_id": user.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(self._org_nick(user))

    def test_org_add_invalidates_user_after_commit(self) -> None:
        user = self._existing()
        self._warm(_member())
        with mock.patch("org.views_admin_team.invalidate_after_commit") as spy:
            self.client.post(
                f"/api/organizations/{self.org.pk}/members/",
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


class UpdateOrgUserGuildNicknameTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.admin = CustomUser.objects.create_user(username="uo_admin", password="x")
        self.org = Organization.objects.create(name="Update Org")
        self.org.admins.add(self.admin)
        self.user = CustomUser.objects.create_user(username="uo_target", password="x")
        self.org_user = OrgUser.objects.create(
            user=self.user, organization=self.org, guild_nickname="Synced"
        )
        self.client.force_authenticate(user=self.admin)

    def test_guild_nickname_key_is_ignored(self) -> None:
        resp = self.client.patch(
            f"/api/organizations/{self.org.pk}/users/{self.org_user.pk}/",
            {"guildNickname": "Manual"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.org_user.refresh_from_db()
        self.assertEqual(self.org_user.guild_nickname, "Synced")
        self.assertIsNone(
            CustomUser.objects.nocache().get(pk=self.user.pk).guildNickname
        )
