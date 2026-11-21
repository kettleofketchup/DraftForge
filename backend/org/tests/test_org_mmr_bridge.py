from django.test import TestCase

from app.models import CustomUser, GameType
from org.mmr import bulk_set_org_mmrs, merge_org_mmrs, set_org_mmr
from org.models import Organization, OrgUser, OrgUserGameMmr

DOTA = GameType.DOTA2
DL = GameType.DEADLOCK


def rows(org_user: OrgUser) -> dict[int, int]:
    return dict(
        OrgUserGameMmr.objects.filter(org_user=org_user).values_list("game_type", "mmr")
    )


def column(org_user: OrgUser) -> int:
    return OrgUser.objects.values_list("mmr", flat=True).get(pk=org_user.pk)


class OrgMmrBridgeTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Bridge Org")
        self.user = CustomUser.objects.create(username="bridge_u")

    def test_create_with_mmr_writes_dota_row(self) -> None:
        ou = OrgUser.objects.create(user=self.user, organization=self.org, mmr=3000)
        self.assertEqual(rows(ou), {DOTA: 3000})

    def test_create_without_mmr_writes_nothing(self) -> None:
        ou = OrgUser.objects.create(user=self.user, organization=self.org)
        self.assertEqual(rows(ou), {})

    def test_full_save_with_changed_mmr_syncs_row(self) -> None:
        ou = OrgUser.objects.create(user=self.user, organization=self.org, mmr=3000)
        ou.mmr = 3500
        ou.save()
        self.assertEqual(rows(ou), {DOTA: 3500})
        ou.mmr = 0
        ou.save()
        self.assertEqual(rows(ou), {})

    def test_update_fields_mmr_syncs_row(self) -> None:
        ou = OrgUser.objects.create(user=self.user, organization=self.org, mmr=3000)
        loaded = OrgUser.objects.get(pk=ou.pk)
        loaded.mmr = 4100
        loaded.save(update_fields=["mmr"])
        self.assertEqual(rows(ou), {DOTA: 4100})

    def test_set_org_mmr_dota_mirrors_column(self) -> None:
        ou = OrgUser.objects.create(user=self.user, organization=self.org, mmr=3000)
        set_org_mmr(ou, DOTA, 4200, mark_verified=False)
        self.assertEqual(column(ou), 4200)
        self.assertEqual(ou.mmr, 4200)
        set_org_mmr(ou, DOTA, None, mark_verified=False)
        self.assertEqual(column(ou), 0)
        self.assertEqual(rows(ou), {})

    def test_deadlock_writes_never_touch_column(self) -> None:
        ou = OrgUser.objects.create(user=self.user, organization=self.org, mmr=3000)
        set_org_mmr(ou, DL, 2500, mark_verified=True)
        self.assertEqual(column(ou), 3000)
        self.assertEqual(ou.mmr, 3000)
        self.assertEqual(rows(ou), {DOTA: 3000, DL: 2500})

    def test_full_save_after_set_does_not_revert_row(self) -> None:
        ou = OrgUser.objects.create(user=self.user, organization=self.org, mmr=3000)
        stale = OrgUser.objects.get(pk=ou.pk)
        set_org_mmr(ou, DOTA, 4200, mark_verified=True)
        ou.save()
        self.assertEqual(rows(ou), {DOTA: 4200})
        self.assertEqual(column(ou), 4200)
        stale.guild_nickname = "renamed"
        stale.save()
        self.assertEqual(rows(ou), {DOTA: 4200})

    def test_bulk_set_dota_mirrors_column(self) -> None:
        ou = OrgUser.objects.create(user=self.user, organization=self.org, mmr=3000)
        other = OrgUser.objects.create(
            user=CustomUser.objects.create(username="bridge_v"),
            organization=self.org,
            mmr=1500,
        )
        bulk_set_org_mmrs(self.org.id, DOTA, {self.user.id: 3100, other.user_id: None})
        OrgUser.objects.get(pk=ou.pk).save()
        self.assertEqual(rows(ou), {DOTA: 3100})
        self.assertEqual(column(ou), 3100)
        self.assertEqual(rows(other), {})
        self.assertEqual(column(other), 0)

    def test_bulk_set_deadlock_leaves_column(self) -> None:
        ou = OrgUser.objects.create(user=self.user, organization=self.org, mmr=3000)
        bulk_set_org_mmrs(self.org.id, DL, {self.user.id: 2000})
        self.assertEqual(column(ou), 3000)

    def test_merge_mirrors_keeper_dota_column(self) -> None:
        keeper = OrgUser.objects.create(user=self.user, organization=self.org, mmr=3000)
        loser = OrgUser.objects.create(
            user=CustomUser.objects.create(username="bridge_loser"),
            organization=self.org,
            mmr=5000,
        )
        merge_org_mmrs(loser, keeper)
        self.assertEqual(column(keeper), 5000)
        self.assertEqual(keeper.mmr, 5000)
        keeper.save()
        self.assertEqual(rows(keeper), {DOTA: 5000})
