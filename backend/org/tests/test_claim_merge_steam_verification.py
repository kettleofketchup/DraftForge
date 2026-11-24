import itertools
from typing import Any

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, PositionsModel, ProfileClaimRequest
from org.models import Organization, OrgUser
from user.steam_accounts import mark_steam_account_verified

_discord_ids = itertools.count(940_000_000_000_000_000)
STUB_STEAMID = 76561198000400001
STUB_ID = STUB_STEAMID - CustomUser.STEAM_ID_64_BASE


def _make_user(name: str, **kwargs: Any) -> CustomUser:
    return CustomUser.objects.create(
        username=name, positions=PositionsModel.objects.create(), **kwargs
    )


def _reload(user: CustomUser) -> CustomUser:
    return CustomUser.objects.get(pk=user.pk)


class ClaimMergeSteamVerificationTests(TestCase):
    def setUp(self) -> None:
        self.superuser = CustomUser.objects.create_superuser(
            username="cv_super", password="x"
        )
        self.org = Organization.objects.create(name="Claim Verify Org")
        self.org_staff = _make_user("cv_org_staff")
        self.org.staff.add(self.org_staff)
        self.claimer = _make_user("cv_claimer", discordId=str(next(_discord_ids)))
        self.stub = _make_user("cv_stub", steamid=STUB_STEAMID)
        OrgUser.objects.create(user=self.claimer, organization=self.org)
        OrgUser.objects.create(user=self.stub, organization=self.org)
        self.client = APIClient()

    def _claim(self) -> ProfileClaimRequest:
        return ProfileClaimRequest.objects.create(
            claimer=self.claimer,
            target_user=self.stub,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )

    def _approve(self, approver: CustomUser) -> None:
        claim = self._claim()
        self.client.force_authenticate(approver)
        resp = self.client.post(f"/api/claim-requests/{claim.pk}/approve/")
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_transfer_verified_by_trusted_approver(self) -> None:
        self._approve(self.superuser)
        claimer = _reload(self.claimer)
        self.assertEqual(claimer.steam_account_id, STUB_ID)
        self.assertEqual(claimer.steamid, STUB_STEAMID)
        self.assertTrue(claimer.steam_account_verified)
        self.assertEqual(claimer.steam_account_verified_by_id, self.superuser.pk)
        self.assertIsNone(claimer.steam_account_verified_org_id)
        self.assertIsNone(claimer.steam_account_exists_checked_at)

    def test_untrusted_approver_transfer_unverified(self) -> None:
        self._approve(self.org_staff)
        claimer = _reload(self.claimer)
        self.assertEqual(claimer.steam_account_id, STUB_ID)
        self.assertFalse(claimer.steam_account_verified)

    def test_stub_without_id_keeps_claimer_id_and_verification(self) -> None:
        self.stub.steam_account_id = None
        self.stub.save()
        self.claimer.steam_account_id = 616161
        self.claimer.save()
        self.assertTrue(
            mark_steam_account_verified(self.claimer, self.superuser, org_id=None)
        )
        self.claimer = _reload(self.claimer)
        self.stub = _reload(self.stub)
        self._approve(self.org_staff)
        claimer = _reload(self.claimer)
        self.assertEqual(claimer.steam_account_id, 616161)
        self.assertTrue(claimer.steam_account_verified)
        self.assertEqual(claimer.steam_account_verified_by_id, self.superuser.pk)

    def test_stub_verified_by_claimer_not_copied(self) -> None:
        self.assertTrue(
            mark_steam_account_verified(self.stub, self.claimer, org_id=self.org.pk)
        )
        self.stub = _reload(self.stub)
        self._approve(self.org_staff)
        claimer = _reload(self.claimer)
        self.assertEqual(claimer.steam_account_id, STUB_ID)
        self.assertFalse(claimer.steam_account_verified)
        self.assertIsNone(claimer.steam_account_verified_by_id)
        self.assertIsNone(claimer.steam_account_verified_org_id)

    def test_approver_is_claimer_unverified(self) -> None:
        self.claimer.is_superuser = True
        self.claimer.is_staff = True
        self.claimer.save()
        self.claimer = _reload(self.claimer)
        self._approve(self.claimer)
        claimer = _reload(self.claimer)
        self.assertEqual(claimer.steam_account_id, STUB_ID)
        self.assertFalse(claimer.steam_account_verified)
