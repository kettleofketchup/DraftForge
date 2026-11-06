from cacheops import invalidate_all
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization, ProfileClaimRequest
from steam.functions.league_summary import get_league_summary
from steam.tests.league_summary_fixtures import make_player, record_series

STEAM_LEAGUE = 90001


class ClaimMergeLeagueSummaryTests(TransactionTestCase):
    def setUp(self) -> None:
        invalidate_all()
        self.admin = CustomUser.objects.create_superuser(
            username="claim_admin", password="testpass"
        )
        self.org = Organization.objects.create(name="Claim Org")
        League.objects.create(
            name="Claim League",
            steam_league_id=STEAM_LEAGUE,
            organization=self.org,
        )
        self.target = make_player("claim_target", 76561198000200001)
        record_series(self.target, "WWL", league_id=STEAM_LEAGUE, first_match_id=700)
        self.claimer = make_player("claim_claimer", 76561198000200002)
        record_series(self.claimer, "WL", league_id=STEAM_LEAGUE, first_match_id=800)
        self.claim = ProfileClaimRequest.objects.create(
            claimer=self.claimer,
            target_user=self.target,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_approve_claim_refreshes_league_summary(self) -> None:
        target_pk = self.target.pk
        warm = get_league_summary(STEAM_LEAGUE, 5)["players"]
        self.assertEqual(warm[str(target_pk)]["games"], 3)
        self.assertEqual(warm[str(self.claimer.pk)]["games"], 2)

        response = self.client.post(f"/api/claim-requests/{self.claim.pk}/approve/")
        self.assertEqual(response.status_code, 200, response.content)

        players = get_league_summary(STEAM_LEAGUE, 5)["players"]
        self.assertEqual(players[str(self.claimer.pk)]["games"], 5)
        self.assertNotIn(str(target_pk), players)
