import itertools
from contextlib import AbstractContextManager
from typing import Any
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser
from org.models import Organization, OrgLog
from org.views import ClaimRequestViewSet
from user.models import PositionsModel, ProfileClaimRequest

_discord_ids = itertools.count(940_000_000_000_000_000)
_steam_ids = itertools.count(76561198000400001)


def _make_user(name: str, **kwargs: Any) -> CustomUser:
    return CustomUser.objects.create(
        username=name, positions=PositionsModel.objects.create(), **kwargs
    )


class ClaimRequestReviewTests(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_superuser(
            username="cr_admin", password="testpass"
        )
        self.org = Organization.objects.create(name="Claim Review Org")
        self.target = _make_user("cr_target", steamid=next(_steam_ids))
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _claim(self, name: str) -> ProfileClaimRequest:
        claimer = _make_user(name, discordId=str(next(_discord_ids)))
        return ProfileClaimRequest.objects.create(
            claimer=claimer,
            target_user=self.target,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )

    def _post(self, claim: ProfileClaimRequest, verb: str) -> Any:
        return self.client.post(f"/api/claim-requests/{claim.pk}/{verb}/")

    def _status(self, claim: ProfileClaimRequest) -> str:
        return ProfileClaimRequest.objects.get(pk=claim.pk).status

    def test_approve_logs_merged_target_ids(self) -> None:
        claim = self._claim("cr_claimer")
        target_pk = self.target.pk
        target_steamid = self.target.steamid

        self.assertEqual(self._post(claim, "approve").status_code, 200)

        details = OrgLog.objects.get(action="approve_claim").details
        self.assertEqual(details["merged_profile_id"], target_pk)
        self.assertEqual(details["merged_steamid"], target_steamid)

    def test_sibling_claim_can_be_rejected_after_target_merged(self) -> None:
        first = self._claim("cr_first")
        second = self._claim("cr_second")
        self.assertEqual(self._post(first, "approve").status_code, 200)

        response = self._post(second, "reject")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._status(second), ProfileClaimRequest.Status.REJECTED)
        log_row = OrgLog.objects.get(action="reject_claim")
        self.assertIsNone(log_row.details["target_profile_id"])

    def test_sibling_claim_approve_after_target_merged_rejects_it(self) -> None:
        first = self._claim("cr_first")
        second = self._claim("cr_second")
        self.assertEqual(self._post(first, "approve").status_code, 200)

        response = self._post(second, "approve")

        self.assertEqual(response.status_code, 400, response.content)
        row = ProfileClaimRequest.objects.get(pk=second.pk)
        self.assertEqual(row.status, ProfileClaimRequest.Status.REJECTED)
        self.assertEqual(row.reviewed_by_id, self.admin.pk)
        self.assertTrue(row.rejection_reason)

    def _stale_get_object(
        self, new_status: ProfileClaimRequest.Status
    ) -> AbstractContextManager[Any]:
        original = ClaimRequestViewSet.get_object

        def stale(view: ClaimRequestViewSet) -> ProfileClaimRequest:
            obj = original(view)
            ProfileClaimRequest.objects.filter(pk=obj.pk).update(status=new_status)
            return obj

        return mock.patch.object(ClaimRequestViewSet, "get_object", stale)

    def test_concurrent_approve_does_not_merge_twice(self) -> None:
        claim = self._claim("cr_claimer")

        with self._stale_get_object(ProfileClaimRequest.Status.APPROVED):
            response = self._post(claim, "approve")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertTrue(CustomUser.objects.filter(pk=self.target.pk).exists())
        self.assertFalse(OrgLog.objects.filter(action="approve_claim").exists())
        self.assertEqual(self._status(claim), ProfileClaimRequest.Status.APPROVED)

    def test_concurrent_reject_does_not_overwrite_approval(self) -> None:
        claim = self._claim("cr_claimer")

        with self._stale_get_object(ProfileClaimRequest.Status.APPROVED):
            response = self._post(claim, "reject")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(OrgLog.objects.filter(action="reject_claim").exists())
        self.assertEqual(self._status(claim), ProfileClaimRequest.Status.APPROVED)

    def test_str_survives_missing_target(self) -> None:
        claim = self._claim("cr_str")
        self.target.delete()
        claim.refresh_from_db()

        self.assertEqual(str(claim), "cr_str -> (deleted profile) (pending)")
