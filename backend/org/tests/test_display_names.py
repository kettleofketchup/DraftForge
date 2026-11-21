from django.test import TestCase

from app.models import CustomUser
from org.display_names import guild_nicknames, org_display_name, org_nicknames_public
from org.models import Organization, OrgUser


class GuildNicknamesTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Display Names Org")
        self.u1 = CustomUser.objects.create(username="dn_u1", discordNickname="Gwaihir")
        self.u2 = CustomUser.objects.create(username="dn_u2")
        self.outsider = CustomUser.objects.create(username="dn_outsider")
        OrgUser.objects.create(
            user=self.u1, organization=self.org, guild_nickname="DragonClaw"
        )
        OrgUser.objects.create(user=self.u2, organization=self.org)

    def test_one_query_members_only(self) -> None:
        with self.assertNumQueries(1):
            result = guild_nicknames(
                self.org.pk, [self.u1.pk, self.u2.pk, self.outsider.pk]
            )
        self.assertEqual(result, {self.u1.pk: "DragonClaw", self.u2.pk: None})

    def test_no_org_no_query(self) -> None:
        with self.assertNumQueries(0):
            self.assertEqual(guild_nicknames(None, [self.u1.pk]), {})

    def test_no_ids_no_query(self) -> None:
        with self.assertNumQueries(0):
            self.assertEqual(guild_nicknames(self.org.pk, []), {})

    def test_org_display_name(self) -> None:
        self.assertEqual(org_display_name(self.u1, self.org.pk), "DragonClaw")
        self.assertEqual(org_display_name(self.u1, None), "Gwaihir")
        self.assertEqual(org_display_name(self.outsider, self.org.pk), "dn_outsider")

    def test_org_display_name_without_org_no_query(self) -> None:
        with self.assertNumQueries(0):
            self.assertEqual(org_display_name(self.u2, None), "dn_u2")


class OrgNicknamesPublicTest(TestCase):
    def test_public_org(self) -> None:
        org = Organization.objects.create(name="Public Org")
        self.assertTrue(org_nicknames_public(org.pk))

    def test_private_org(self) -> None:
        org = Organization.objects.create(name="Private Org", members_private=True)
        self.assertFalse(org_nicknames_public(org.pk))

    def test_none(self) -> None:
        with self.assertNumQueries(0):
            self.assertFalse(org_nicknames_public(None))

    def test_deleted_org(self) -> None:
        org = Organization.objects.create(name="Gone Org")
        pk = org.pk
        org.delete()
        self.assertFalse(org_nicknames_public(pk))
