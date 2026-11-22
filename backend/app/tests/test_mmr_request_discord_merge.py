from django.test import TestCase
from django.utils import timezone

from app.discord_accounts import merge_discord_accounts
from app.models import CustomUser
from league.models import League, LeagueUser
from org.models import MmrChangeRequest, Organization, OrgUser
from org.tests.mmr_request_mixin import MmrRequestTestMixin


class MmrRequestDiscordMergeTests(MmrRequestTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.staff = CustomUser.objects.create(username="dm_staff")
        self.keep = CustomUser.objects.create(
            username="dm_keep", discordId="950000000000000001"
        )
        self.drop = CustomUser.objects.create(username="dm_drop")
        self.org = Organization.objects.create(
            name="Discord Merge Org", owner=self.staff
        )
        self.league = League.objects.create(
            name="Discord Merge League", organization=self.org, steam_league_id=779001
        )
        self.keep_ou = OrgUser.objects.create(user=self.keep, organization=self.org)
        self.drop_ou = OrgUser.objects.create(user=self.drop, organization=self.org)

    def reload(self, req: MmrChangeRequest) -> MmrChangeRequest:
        return MmrChangeRequest.objects.get(pk=req.pk)

    def test_pending_org_request_repoints_to_keeper(self) -> None:
        req = self.make_request(org_user=self.drop_ou)

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        req = self.reload(req)
        self.assertEqual(req.status, MmrChangeRequest.Status.PENDING)
        self.assertEqual(req.org_user_id, self.keep_ou.pk)
        self.assertEqual(req.subject_user_id, self.keep.pk)
        self.assertEqual(req.requester_id, self.keep.pk)

    def test_pending_on_both_sides_supersedes_drop(self) -> None:
        drop_req = self.make_request(org_user=self.drop_ou)
        keep_req = self.make_request(org_user=self.keep_ou)

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        drop_req = self.reload(drop_req)
        self.assertEqual(drop_req.status, MmrChangeRequest.Status.SUPERSEDED)
        self.assertEqual(drop_req.org_user_id, self.keep_ou.pk)
        self.assertEqual(self.reload(keep_req).status, MmrChangeRequest.Status.PENDING)

    def test_decided_rows_keep_audit_linkage(self) -> None:
        req = self.make_request(
            org_user=self.drop_ou,
            status=MmrChangeRequest.Status.APPROVED,
            reviewed_by=self.staff,
            approved_mmr=4000,
        )

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        req = self.reload(req)
        self.assertEqual(req.status, MmrChangeRequest.Status.APPROVED)
        self.assertEqual(req.org_user_id, self.keep_ou.pk)
        self.assertEqual(req.subject_user_id, self.keep.pk)
        self.assertEqual(req.reviewed_by_id, self.staff.pk)

    def test_drop_verified_league_value_survives(self) -> None:
        drop_lu = LeagueUser.objects.create(
            user=self.drop,
            org_user=self.drop_ou,
            league=self.league,
            mmr=6000,
            mmr_verified_at=timezone.now(),
            mmr_verified_by=self.staff,
        )
        keep_lu = LeagueUser.objects.create(
            user=self.keep, org_user=self.keep_ou, league=self.league, mmr=3000
        )
        req = self.make_request(org_user=self.drop_ou, league_user=drop_lu)

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        row = LeagueUser.objects.nocache().get(pk=keep_lu.pk)
        self.assertEqual(row.mmr, 6000)
        self.assertEqual(row.mmr_verified_by_id, self.staff.pk)
        req = self.reload(req)
        self.assertEqual(req.status, MmrChangeRequest.Status.PENDING)
        self.assertEqual(req.league_user_id, keep_lu.pk)
        self.assertEqual(req.org_user_id, self.keep_ou.pk)

    def test_drop_league_user_moves_when_keeper_has_none(self) -> None:
        drop_lu = LeagueUser.objects.create(
            user=self.drop, org_user=self.drop_ou, league=self.league, mmr=4400
        )

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        row = LeagueUser.objects.nocache().get(pk=drop_lu.pk)
        self.assertEqual(row.user_id, self.keep.pk)
        self.assertEqual(row.org_user_id, self.keep_ou.pk)
        self.assertEqual(row.mmr, 4400)

    def test_no_file_deleted(self) -> None:
        drop_lu = LeagueUser.objects.create(
            user=self.drop, org_user=self.drop_ou, league=self.league
        )
        LeagueUser.objects.create(
            user=self.keep, org_user=self.keep_ou, league=self.league
        )
        self.make_request(org_user=self.drop_ou)
        self.make_request(org_user=self.keep_ou)
        self.make_request(org_user=self.drop_ou, league_user=drop_lu)
        files_before = self.media_files()

        with self.captureOnCommitCallbacks(execute=True):
            merge_discord_accounts(keep=self.keep, drop=self.drop)

        self.assertEqual(MmrChangeRequest.objects.count(), 3)
        self.assertEqual(self.media_files(), files_before)
