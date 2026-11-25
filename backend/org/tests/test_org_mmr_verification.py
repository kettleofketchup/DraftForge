from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, GameType
from org.mmr import (
    bulk_set_org_mmrs,
    mark_org_mmr_verified,
    merge_org_mmrs,
    set_org_mmr,
)
from org.models import Organization, OrgUser, OrgUserGameMmr

DOTA = GameType.DOTA2
DL = GameType.DEADLOCK


def row(org_user: OrgUser, game_type: int) -> OrgUserGameMmr | None:
    return (
        OrgUserGameMmr.objects.nocache()
        .filter(org_user=org_user, game_type=game_type)
        .first()
    )


class OrgMmrVerificationBase(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Verify Org")
        self.staff = CustomUser.objects.create(username="verify_staff")
        self.user = CustomUser.objects.create(username="verify_member")
        self.ou = OrgUser.objects.create(user=self.user, organization=self.org)

    def fresh_ou(self) -> OrgUser:
        return OrgUser.objects.nocache().get(pk=self.ou.pk)


class SetOrgMmrVerificationTest(OrgMmrVerificationBase):
    def test_set_org_mmr_mark_verified_sets_marker(self) -> None:
        set_org_mmr(self.ou, DL, 3000, mark_verified=True, verified_by=self.staff)
        r = row(self.ou, DL)
        assert r is not None
        self.assertEqual(r.mmr, 3000)
        self.assertEqual(r.verified_by, self.staff)
        self.assertIsNotNone(r.verified_at)

    def test_set_org_mmr_unverified_change_clears_marker(self) -> None:
        set_org_mmr(self.ou, DL, 3000, mark_verified=True, verified_by=self.staff)
        set_org_mmr(self.ou, DL, 3500, mark_verified=False)
        r = row(self.ou, DL)
        assert r is not None
        self.assertEqual(r.mmr, 3500)
        self.assertIsNone(r.verified_at)
        self.assertIsNone(r.verified_by)

    def test_set_org_mmr_unverified_same_value_keeps_marker(self) -> None:
        set_org_mmr(self.ou, DL, 3000, mark_verified=True, verified_by=self.staff)
        set_org_mmr(self.ou, DL, 3000, mark_verified=False)
        r = row(self.ou, DL)
        assert r is not None
        self.assertIsNotNone(r.verified_at)
        self.assertEqual(r.verified_by, self.staff)

    def test_set_org_mmr_zero_deletes_row_and_marker(self) -> None:
        set_org_mmr(self.ou, DL, 3000, mark_verified=True, verified_by=self.staff)
        set_org_mmr(self.ou, DL, 0, mark_verified=False)
        self.assertIsNone(row(self.ou, DL))

    def test_set_org_mmr_zero_verified_dota_sets_legacy_flags(self) -> None:
        set_org_mmr(self.ou, DOTA, 4000, mark_verified=False)
        set_org_mmr(self.ou, DOTA, 0, mark_verified=True, verified_by=self.staff)
        self.assertIsNone(row(self.ou, DOTA))
        ou = self.fresh_ou()
        self.assertTrue(ou.has_active_dota_mmr)
        self.assertIsNotNone(ou.dota_mmr_last_verified)


class MarkOrgMmrVerifiedTest(OrgMmrVerificationBase):
    def test_mark_org_mmr_verified_stamps_marker_and_dota_flags(self) -> None:
        set_org_mmr(self.ou, DOTA, 4000, mark_verified=False)
        mark_org_mmr_verified(self.ou, DOTA, self.staff)
        r = row(self.ou, DOTA)
        assert r is not None
        self.assertEqual(r.mmr, 4000)
        self.assertEqual(r.verified_by, self.staff)
        self.assertIsNotNone(r.verified_at)
        ou = self.fresh_ou()
        self.assertTrue(ou.has_active_dota_mmr)
        self.assertIsNotNone(ou.dota_mmr_last_verified)

    def test_mark_org_mmr_verified_missing_row_still_sets_dota_flags(self) -> None:
        mark_org_mmr_verified(self.ou, DOTA, self.staff)
        self.assertIsNone(row(self.ou, DOTA))
        ou = self.fresh_ou()
        self.assertTrue(ou.has_active_dota_mmr)
        self.assertIsNotNone(ou.dota_mmr_last_verified)

    def test_mark_org_mmr_verified_non_dota_leaves_dota_flags(self) -> None:
        set_org_mmr(self.ou, DL, 2500, mark_verified=False)
        mark_org_mmr_verified(self.ou, DL, self.staff)
        r = row(self.ou, DL)
        assert r is not None
        self.assertEqual(r.verified_by, self.staff)
        self.assertFalse(self.fresh_ou().has_active_dota_mmr)


class BulkSetVerificationTest(OrgMmrVerificationBase):
    def test_bulk_set_clears_marker(self) -> None:
        set_org_mmr(self.ou, DOTA, 4000, mark_verified=True, verified_by=self.staff)
        bulk_set_org_mmrs(self.org.pk, DOTA, {self.user.pk: 4200})
        r = row(self.ou, DOTA)
        assert r is not None
        self.assertEqual(r.mmr, 4200)
        self.assertIsNone(r.verified_at)
        self.assertIsNone(r.verified_by)


class MergeVerificationTest(OrgMmrVerificationBase):
    def setUp(self) -> None:
        super().setUp()
        self.loser_user = CustomUser.objects.create(username="verify_loser")
        self.loser = OrgUser.objects.create(user=self.loser_user, organization=self.org)
        self.other_staff = CustomUser.objects.create(username="verify_staff_2")

    def test_merge_prefers_verified_lower_over_unverified_higher(self) -> None:
        set_org_mmr(self.ou, DOTA, 3000, mark_verified=True, verified_by=self.staff)
        set_org_mmr(self.loser, DOTA, 5000, mark_verified=False)
        merge_org_mmrs(self.loser, self.ou)
        r = row(self.ou, DOTA)
        assert r is not None
        self.assertEqual(r.mmr, 3000)
        self.assertEqual(r.verified_by, self.staff)
        self.assertIsNotNone(r.verified_at)

    def test_merge_prefers_verified_loser_over_unverified_keeper(self) -> None:
        set_org_mmr(self.ou, DL, 5000, mark_verified=False)
        set_org_mmr(self.loser, DL, 3000, mark_verified=True, verified_by=self.staff)
        merge_org_mmrs(self.loser, self.ou)
        r = row(self.ou, DL)
        assert r is not None
        self.assertEqual(r.mmr, 3000)
        self.assertEqual(r.verified_by, self.staff)
        self.assertIsNotNone(r.verified_at)

    def test_merge_neither_verified_keeps_higher_without_marker(self) -> None:
        set_org_mmr(self.ou, DL, 3000, mark_verified=False)
        set_org_mmr(self.loser, DL, 5000, mark_verified=False)
        merge_org_mmrs(self.loser, self.ou)
        r = row(self.ou, DL)
        assert r is not None
        self.assertEqual(r.mmr, 5000)
        self.assertIsNone(r.verified_at)
        self.assertIsNone(r.verified_by)

    def test_merge_both_verified_keeps_higher_with_its_marker(self) -> None:
        set_org_mmr(self.ou, DL, 3000, mark_verified=True, verified_by=self.staff)
        set_org_mmr(
            self.loser, DL, 5000, mark_verified=True, verified_by=self.other_staff
        )
        loser_at = row(self.loser, DL).verified_at  # type: ignore[union-attr]
        OrgUserGameMmr.objects.filter(org_user=self.ou, game_type=DL).update(
            verified_at=timezone.now() - timedelta(days=3)
        )
        merge_org_mmrs(self.loser, self.ou)
        r = row(self.ou, DL)
        assert r is not None
        self.assertEqual(r.mmr, 5000)
        self.assertEqual(r.verified_by, self.other_staff)
        self.assertEqual(r.verified_at, loser_at)
