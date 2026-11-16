from django.test import TestCase

from app.models import CustomUser, Organization
from app.tests.raw_site_nickname import set_raw_site_nickname
from org.models import OrgUser
from org.user_search import user_name_q


class UserNameQTest(TestCase):
    def setUp(self) -> None:
        self.org_a = Organization.objects.create(name="Search Org A")
        self.org_b = Organization.objects.create(name="Search Org B")
        self.dragon = CustomUser.objects.create_user(
            username="dc_account",
            password="x",
            discordUsername="dragon_dc_handle",
            discordNickname="GwaihirTheWindlord",
        )
        set_raw_site_nickname(self.dragon.pk, "SiteDragon")
        self.other = CustomUser.objects.create_user(username="bystander", password="x")
        OrgUser.objects.create(
            user=self.dragon, organization=self.org_a, guild_nickname="DragonClaw"
        )
        OrgUser.objects.create(
            user=self.other, organization=self.org_b, guild_nickname="BeeOnlyNick"
        )

    def _pks(self, term: str, org_id: int | None = None) -> list[int]:
        return list(
            CustomUser.objects.filter(user_name_q(term, org_id=org_id)).values_list(
                "pk", flat=True
            )
        )

    def test_matches_username(self) -> None:
        self.assertEqual(self._pks("DC_ACC"), [self.dragon.pk])

    def test_ignores_site_nickname(self) -> None:
        self.assertEqual(self._pks("sitedrag"), [])

    def test_matches_discord_username(self) -> None:
        self.assertEqual(self._pks("DC_HANDLE"), [self.dragon.pk])

    def test_matches_global_name(self) -> None:
        self.assertEqual(self._pks("windlord"), [self.dragon.pk])

    def test_org_scope_matches_that_orgs_guild_nickname(self) -> None:
        self.assertEqual(
            self._pks("dragonclaw", org_id=self.org_a.pk), [self.dragon.pk]
        )

    def test_org_scope_ignores_other_orgs_guild_nickname(self) -> None:
        self.assertEqual(self._pks("dragonclaw", org_id=self.org_b.pk), [])
        self.assertEqual(self._pks("beeonly", org_id=self.org_a.pk), [])

    def test_without_org_never_matches_guild_nickname(self) -> None:
        self.assertEqual(self._pks("dragonclaw"), [])

    def test_prefix_on_org_user_queryset(self) -> None:
        rows = list(
            OrgUser.objects.filter(
                user_name_q("dragonclaw", org_id=self.org_a.pk, prefix="user__")
            ).values_list("user_id", flat=True)
        )
        self.assertEqual(rows, [self.dragon.pk])
        rows = list(
            OrgUser.objects.filter(
                user_name_q("windlord", prefix="user__")
            ).values_list("user_id", flat=True)
        )
        self.assertEqual(rows, [self.dragon.pk])

    def test_non_ascii_exact_case_only(self) -> None:
        omega = CustomUser.objects.create_user(
            username="omega_user", password="x", discordNickname="Ωmega"
        )
        self.assertEqual(self._pks("Ωmega"), [omega.pk])
        self.assertEqual(self._pks("ωmega"), [])

    def test_user_with_two_memberships_appears_once(self) -> None:
        OrgUser.objects.create(
            user=self.dragon, organization=self.org_b, guild_nickname="DragonB"
        )
        self.assertEqual(self._pks("drag", org_id=self.org_a.pk), [self.dragon.pk])
        self.assertEqual(self._pks("drag", org_id=self.org_b.pk), [self.dragon.pk])
