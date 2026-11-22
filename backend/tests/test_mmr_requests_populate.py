from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from app.models import CustomUser
from common.game import GameType
from league.models import League, LeagueUser
from org.mmr import LEAGUE_GAME
from org.models import MmrChangeRequest, Organization, OrgUser, OrgUserGameMmr
from org.tests.mmr_request_mixin import MmrRequestTestMixin
from tests.data.mmr_requests import (
    LEAGUE_STAFF_PK,
    MEMBER_APPROVE_PK,
    MEMBER_REJECT_PK,
    MEMBER_STAFFSET_PK,
    MMR_REQ_BASE_MMR,
    MMR_REQ_LEAGUE_PK,
    MMR_REQ_ORG_PK,
    ORG_STAFF_PK,
    OUTSIDER_PK,
)
from tests.populate.mmr_requests import populate_mmr_requests_data, reset_mmr_requests
from tests.test_mmr_requests import mmr_requests_data, mmr_requests_reset

MEMBER_PKS = (MEMBER_APPROVE_PK, MEMBER_REJECT_PK, MEMBER_STAFFSET_PK)


def _org_user(pk: int) -> OrgUser:
    return OrgUser.objects.nocache().get(organization_id=MMR_REQ_ORG_PK, user_id=pk)


def _league_user(pk: int) -> LeagueUser:
    return LeagueUser.objects.nocache().get(league_id=MMR_REQ_LEAGUE_PK, user_id=pk)


def _dota_row(pk: int) -> OrgUserGameMmr:
    return OrgUserGameMmr.objects.nocache().get(
        org_user__organization_id=MMR_REQ_ORG_PK,
        org_user__user_id=pk,
        game_type=GameType.DOTA2,
    )


class MmrRequestsPopulateTest(MmrRequestTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        populate_mmr_requests_data(False)

    def assert_baseline(self, pk: int) -> None:
        row = _dota_row(pk)
        self.assertEqual(row.mmr, MMR_REQ_BASE_MMR)
        self.assertIsNone(row.verified_at)
        self.assertIsNone(row.verified_by_id)
        org_user = _org_user(pk)
        self.assertFalse(org_user.has_active_dota_mmr)
        self.assertIsNone(org_user.dota_mmr_last_verified)
        self.assertEqual(
            OrgUserGameMmr.objects.nocache().filter(org_user=org_user).count(), 1
        )
        league_user = _league_user(pk)
        self.assertEqual(league_user.mmr, MMR_REQ_BASE_MMR)
        self.assertIsNone(league_user.mmr_verified_at)
        self.assertIsNone(league_user.mmr_verified_by_id)

    def test_populate_mmr_requests(self) -> None:
        org = Organization.objects.nocache().get(pk=MMR_REQ_ORG_PK)
        league = League.objects.nocache().get(pk=MMR_REQ_LEAGUE_PK)
        self.assertEqual(league.organization_id, org.pk)
        self.assertFalse(org.members_private)
        self.assertEqual(
            set(
                OrgUser.objects.nocache()
                .filter(organization=org)
                .values_list("user_id", flat=True)
            ),
            set(MEMBER_PKS),
        )
        for pk in MEMBER_PKS:
            self.assert_baseline(pk)
        self.assertTrue(org.staff.filter(pk=ORG_STAFF_PK).exists())
        self.assertTrue(league.staff.filter(pk=LEAGUE_STAFF_PK).exists())
        self.assertTrue(CustomUser.objects.filter(pk=OUTSIDER_PK).exists())
        self.assertFalse(OrgUser.objects.filter(user_id=OUTSIDER_PK).exists())

        counts = (
            CustomUser.objects.count(),
            OrgUser.objects.count(),
            LeagueUser.objects.count(),
            OrgUserGameMmr.objects.count(),
        )
        populate_mmr_requests_data(True)
        populate_mmr_requests_data(False)
        self.assertEqual(
            counts,
            (
                CustomUser.objects.count(),
                OrgUser.objects.count(),
                LeagueUser.objects.count(),
                OrgUserGameMmr.objects.count(),
            ),
        )

    def _dirty(self, pk: int) -> None:
        staff = CustomUser.objects.get(pk=ORG_STAFF_PK)
        org_user = _org_user(pk)
        league_user = _league_user(pk)
        self.make_request(org_user=org_user)
        self.make_request(
            org_user=org_user,
            league_user=league_user,
            status=MmrChangeRequest.Status.APPROVED,
            approved_mmr=5000,
        )
        OrgUserGameMmr.objects.filter(pk=_dota_row(pk).pk).update(
            mmr=5000, verified_at=timezone.now(), verified_by=staff
        )
        OrgUserGameMmr.objects.create(
            org_user=org_user, game_type=GameType.DEADLOCK, mmr=1500
        )
        OrgUser.objects.filter(pk=org_user.pk).update(
            has_active_dota_mmr=True, dota_mmr_last_verified=timezone.now()
        )
        LeagueUser.objects.filter(pk=league_user.pk).update(
            mmr=5100, mmr_verified_at=timezone.now(), mmr_verified_by=staff
        )

    def test_reset_one_user_restores_state_and_removes_files(self) -> None:
        self._dirty(MEMBER_APPROVE_PK)
        self._dirty(MEMBER_REJECT_PK)
        Organization.objects.filter(pk=MMR_REQ_ORG_PK).update(members_private=True)
        self.assertEqual(len(self.media_files()), 4)

        with self.captureOnCommitCallbacks(execute=True):
            reset_mmr_requests(MEMBER_APPROVE_PK)

        self.assert_baseline(MEMBER_APPROVE_PK)
        self.assertFalse(
            MmrChangeRequest.objects.filter(subject_user_id=MEMBER_APPROVE_PK).exists()
        )
        self.assertEqual(
            MmrChangeRequest.objects.filter(subject_user_id=MEMBER_REJECT_PK).count(),
            2,
        )
        self.assertEqual(_dota_row(MEMBER_REJECT_PK).mmr, 5000)
        self.assertEqual(len(self.media_files()), 2)
        self.assertFalse(
            Organization.objects.nocache().get(pk=MMR_REQ_ORG_PK).members_private
        )

    def test_reset_all_and_members_private(self) -> None:
        for pk in MEMBER_PKS:
            self._dirty(pk)
        with self.captureOnCommitCallbacks(execute=True):
            reset_mmr_requests(members_private=True)
        for pk in MEMBER_PKS:
            self.assert_baseline(pk)
        self.assertFalse(MmrChangeRequest.objects.exists())
        self.assertEqual(self.media_files(), [])
        self.assertTrue(
            Organization.objects.nocache().get(pk=MMR_REQ_ORG_PK).members_private
        )


class MmrRequestsEndpointTest(MmrRequestTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        populate_mmr_requests_data(False)
        self.factory = APIRequestFactory()

    def test_data_endpoint(self) -> None:
        with patch("tests.test_mmr_requests.isTestEnvironment", return_value=True):
            resp = mmr_requests_data(self.factory.get("/x/"))
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.data
        self.assertEqual(body["org"]["pk"], MMR_REQ_ORG_PK)
        self.assertEqual(body["league"]["pk"], MMR_REQ_LEAGUE_PK)
        self.assertEqual(body["base_mmr"], MMR_REQ_BASE_MMR)
        self.assertEqual(body["game_types"]["dota2"], GameType.DOTA2)
        self.assertEqual(body["game_types"]["league"], LEAGUE_GAME)
        users = body["users"]
        self.assertEqual(users["member_approve"]["pk"], MEMBER_APPROVE_PK)
        self.assertEqual(users["member_reject"]["pk"], MEMBER_REJECT_PK)
        self.assertEqual(users["member_staffset"]["pk"], MEMBER_STAFFSET_PK)
        self.assertEqual(users["org_staff"]["pk"], ORG_STAFF_PK)
        self.assertEqual(users["league_staff"]["pk"], LEAGUE_STAFF_PK)
        self.assertEqual(users["outsider"]["pk"], OUTSIDER_PK)
        self.assertEqual(
            users["member_approve"]["org_user_pk"], _org_user(MEMBER_APPROVE_PK).pk
        )
        self.assertEqual(
            users["member_approve"]["league_user_pk"],
            _league_user(MEMBER_APPROVE_PK).pk,
        )
        self.assertIsNone(users["outsider"]["org_user_pk"])

    def test_reset_endpoint(self) -> None:
        self._dirty_one()
        with (
            patch("tests.test_mmr_requests.isTestEnvironment", return_value=True),
            self.captureOnCommitCallbacks(execute=True),
        ):
            resp = mmr_requests_reset(
                self.factory.post(f"/x/?user={MEMBER_APPROVE_PK}&members_private=1")
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["org"]["pk"], MMR_REQ_ORG_PK)
        self.assertFalse(MmrChangeRequest.objects.exists())
        self.assertEqual(self.media_files(), [])
        self.assertTrue(
            Organization.objects.nocache().get(pk=MMR_REQ_ORG_PK).members_private
        )

    def test_reset_endpoint_rejects_bad_user(self) -> None:
        with patch("tests.test_mmr_requests.isTestEnvironment", return_value=True):
            bad = mmr_requests_reset(self.factory.post("/x/?user=abc"))
            unknown = mmr_requests_reset(self.factory.post(f"/x/?user={OUTSIDER_PK}"))
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(unknown.status_code, 400)

    def test_endpoints_hidden_outside_test_env(self) -> None:
        with patch("tests.test_mmr_requests.isTestEnvironment", return_value=False):
            self.assertEqual(
                mmr_requests_data(self.factory.get("/x/")).status_code, 404
            )
            self.assertEqual(
                mmr_requests_reset(self.factory.post("/x/")).status_code, 404
            )

    def _dirty_one(self) -> None:
        self.make_request(org_user=_org_user(MEMBER_APPROVE_PK))
