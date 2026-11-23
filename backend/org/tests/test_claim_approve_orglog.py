from django.test import TransactionTestCase
from rest_framework.test import APIClient

from app.models import CustomUser, ProfileClaimRequest
from org.models import Organization, OrgLog
from steam.tests.league_summary_fixtures import make_player
from tests.cache import flush_run_cache


class ClaimApproveOrgLogTests(TransactionTestCase):
    def setUp(self) -> None:
        flush_run_cache()
        self.admin = CustomUser.objects.create_superuser(
            username="orglog_admin", password="testpass"
        )
        self.org = Organization.objects.create(name="OrgLog Claim Org")
        self.target = make_player("orglog_target", 76561198000300001)
        self.claimer = make_player("orglog_claimer", 76561198000300002)
        self.claim = ProfileClaimRequest.objects.create(
            claimer=self.claimer,
            target_user=self.target,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_approve_claim_orglog_keeps_merged_profile_ids(self) -> None:
        target_pk = self.target.pk

        response = self.client.post(f"/api/claim-requests/{self.claim.pk}/approve/")
        self.assertEqual(response.status_code, 200, response.content)

        entry = OrgLog.objects.nocache().get(
            organization=self.org, action="approve_claim"
        )
        self.assertEqual(entry.target_user_id, self.claimer.pk)
        self.assertEqual(
            entry.details,
            {"merged_profile_id": target_pk, "merged_steamid": 76561198000300001},
        )
