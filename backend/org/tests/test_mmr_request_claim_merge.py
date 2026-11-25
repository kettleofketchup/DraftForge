from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from league.models import League, LeagueUser
from org.mmr import LEAGUE_GAME
from org.models import MmrChangeRequest, Organization, OrgUser, OrgUserGameMmr
from org.tests.mmr_request_mixin import MmrRequestTestMixin
from user.models import PositionsModel, ProfileClaimRequest


def _user(name: str, **kwargs: object) -> CustomUser:
    return CustomUser.objects.create(
        username=name, positions=PositionsModel.objects.create(), **kwargs
    )


class MmrRequestClaimMergeTests(MmrRequestTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.admin = CustomUser.objects.create_superuser(
            username="mcm_admin", password="x"
        )
        self.claimer = _user("mcm_claimer", discordId="940000000000000001")
        self.target = _user("mcm_target", steamid=76561198000400001)
        self.org = Organization.objects.create(name="Merge Paired Org")
        self.moved_org = Organization.objects.create(name="Merge Moved Org")
        self.league = League.objects.create(
            name="Merge League", organization=self.org, steam_league_id=778001
        )
        self.keeper_ou = OrgUser.objects.create(
            user=self.claimer, organization=self.org
        )
        self.loser_ou = OrgUser.objects.create(user=self.target, organization=self.org)
        self.moved_ou = OrgUser.objects.create(
            user=self.target, organization=self.moved_org
        )
        self.claim = ProfileClaimRequest.objects.create(
            claimer=self.claimer,
            target_user=self.target,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )

    def approve(self) -> None:
        client = APIClient()
        client.force_authenticate(self.admin)
        resp = client.post(f"/api/claim-requests/{self.claim.pk}/approve/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(CustomUser.objects.filter(pk=self.target.pk).exists())

    def reload(self, req: MmrChangeRequest) -> MmrChangeRequest:
        return MmrChangeRequest.objects.get(pk=req.pk)

    def test_moved_org_user_keeps_rows_with_users_repointed(self) -> None:
        req = self.make_request(org_user=self.moved_ou)

        self.approve()

        req = self.reload(req)
        self.assertEqual(req.status, MmrChangeRequest.Status.PENDING)
        self.assertEqual(req.org_user_id, self.moved_ou.pk)
        self.assertEqual(req.subject_user_id, self.claimer.pk)
        self.assertEqual(req.requester_id, self.claimer.pk)

    def test_paired_org_user_requests_repoint_to_keeper(self) -> None:
        pending = self.make_request(org_user=self.loser_ou)
        decided = self.make_request(
            org_user=self.loser_ou,
            status=MmrChangeRequest.Status.REJECTED,
            reviewed_by=self.target,
        )

        self.approve()

        pending = self.reload(pending)
        decided = self.reload(decided)
        self.assertEqual(pending.status, MmrChangeRequest.Status.PENDING)
        self.assertEqual(pending.org_user_id, self.keeper_ou.pk)
        self.assertEqual(decided.status, MmrChangeRequest.Status.REJECTED)
        self.assertEqual(decided.org_user_id, self.keeper_ou.pk)
        self.assertEqual(decided.reviewed_by_id, self.claimer.pk)

    def test_pending_on_both_sides_supersedes_loser(self) -> None:
        loser_req = self.make_request(org_user=self.loser_ou)
        keeper_req = self.make_request(org_user=self.keeper_ou)

        self.approve()

        loser_req = self.reload(loser_req)
        keeper_req = self.reload(keeper_req)
        self.assertEqual(loser_req.status, MmrChangeRequest.Status.SUPERSEDED)
        self.assertIsNotNone(loser_req.reviewed_at)
        self.assertEqual(loser_req.org_user_id, self.keeper_ou.pk)
        self.assertEqual(keeper_req.status, MmrChangeRequest.Status.PENDING)

    def test_paired_league_users_repoint_league_user(self) -> None:
        loser_lu = LeagueUser.objects.create(
            user=self.target, org_user=self.loser_ou, league=self.league, mmr=3000
        )
        keeper_lu = LeagueUser.objects.create(
            user=self.claimer, org_user=self.keeper_ou, league=self.league, mmr=2000
        )
        req = self.make_request(org_user=self.loser_ou, league_user=loser_lu)

        self.approve()

        req = self.reload(req)
        self.assertEqual(req.status, MmrChangeRequest.Status.PENDING)
        self.assertEqual(req.league_user_id, keeper_lu.pk)
        self.assertEqual(req.org_user_id, self.keeper_ou.pk)
        self.assertFalse(LeagueUser.objects.filter(pk=loser_lu.pk).exists())
        self.assertEqual(LeagueUser.objects.nocache().get(pk=keeper_lu.pk).mmr, 3000)

    def test_pending_league_on_both_sides_supersedes_loser(self) -> None:
        loser_lu = LeagueUser.objects.create(
            user=self.target, org_user=self.loser_ou, league=self.league
        )
        keeper_lu = LeagueUser.objects.create(
            user=self.claimer, org_user=self.keeper_ou, league=self.league
        )
        loser_req = self.make_request(org_user=self.loser_ou, league_user=loser_lu)
        keeper_req = self.make_request(org_user=self.keeper_ou, league_user=keeper_lu)

        self.approve()

        self.assertEqual(
            self.reload(loser_req).status, MmrChangeRequest.Status.SUPERSEDED
        )
        self.assertEqual(
            self.reload(keeper_req).status, MmrChangeRequest.Status.PENDING
        )

    def test_unpaired_league_user_moves_to_keeper_org_user(self) -> None:
        loser_lu = LeagueUser.objects.create(
            user=self.target,
            org_user=self.loser_ou,
            league=self.league,
            mmr=4100,
            mmr_verified_at=timezone.now(),
            mmr_verified_by=self.admin,
        )
        req = self.make_request(org_user=self.loser_ou, league_user=loser_lu)

        self.approve()

        moved = LeagueUser.objects.nocache().get(pk=loser_lu.pk)
        self.assertEqual(moved.user_id, self.claimer.pk)
        self.assertEqual(moved.org_user_id, self.keeper_ou.pk)
        self.assertEqual(moved.mmr, 4100)
        self.assertIsNotNone(moved.mmr_verified_at)
        req = self.reload(req)
        self.assertEqual(req.status, MmrChangeRequest.Status.PENDING)
        self.assertEqual(req.league_user_id, loser_lu.pk)

    def test_claim_merge_league_prefers_verified(self) -> None:
        LeagueUser.objects.create(
            user=self.target,
            org_user=self.loser_ou,
            league=self.league,
            mmr=3000,
            mmr_verified_at=timezone.now(),
            mmr_verified_by=self.admin,
        )
        keeper_lu = LeagueUser.objects.create(
            user=self.claimer, org_user=self.keeper_ou, league=self.league, mmr=5000
        )

        self.approve()

        row = LeagueUser.objects.nocache().get(pk=keeper_lu.pk)
        self.assertEqual(row.mmr, 3000)
        self.assertEqual(row.mmr_verified_by_id, self.admin.pk)

    def test_target_deletion_leaves_rows_and_files(self) -> None:
        loser_lu = LeagueUser.objects.create(
            user=self.target, org_user=self.loser_ou, league=self.league
        )
        LeagueUser.objects.create(
            user=self.claimer, org_user=self.keeper_ou, league=self.league
        )
        reqs = [
            self.make_request(org_user=self.moved_ou),
            self.make_request(org_user=self.loser_ou),
            self.make_request(org_user=self.keeper_ou),
            self.make_request(org_user=self.loser_ou, league_user=loser_lu),
        ]
        files_before = self.media_files()
        self.assertEqual(len(files_before), 4)

        with self.captureOnCommitCallbacks(execute=True):
            self.approve()

        self.assertEqual(
            MmrChangeRequest.objects.filter(pk__in=[r.pk for r in reqs]).count(), 4
        )
        self.assertFalse(
            MmrChangeRequest.objects.filter(
                status=MmrChangeRequest.Status.CANCELLED
            ).exists()
        )
        self.assertEqual(self.media_files(), files_before)

    def test_verifier_repointed_when_target_verified(self) -> None:
        member = _user("mcm_member")
        member_ou = OrgUser.objects.create(user=member, organization=self.org)
        game_mmr = OrgUserGameMmr.objects.create(
            org_user=member_ou,
            game_type=LEAGUE_GAME,
            mmr=4200,
            verified_at=timezone.now(),
            verified_by=self.target,
        )
        member_lu = LeagueUser.objects.create(
            user=member,
            org_user=member_ou,
            league=self.league,
            mmr=4300,
            mmr_verified_at=timezone.now(),
            mmr_verified_by=self.target,
        )

        self.approve()

        game_mmr = OrgUserGameMmr.objects.nocache().get(pk=game_mmr.pk)
        self.assertEqual(game_mmr.verified_by_id, self.claimer.pk)
        self.assertIsNotNone(game_mmr.verified_at)
        member_lu = LeagueUser.objects.nocache().get(pk=member_lu.pk)
        self.assertEqual(member_lu.mmr_verified_by_id, self.claimer.pk)
