import re

from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import TestCase

from app.models import CustomUser, GameType
from league.models import League, LeagueUser
from org.mmr_requests.permissions import (
    can_review_mmr_request,
    may_self_verify,
    org_queue_filter,
)
from org.models import MmrChangeRequest, Organization, OrgUser
from org.models_mmr_requests import mmr_screenshot_path
from org.tests.mmr_request_mixin import MmrRequestTestMixin

DL = GameType.DEADLOCK
PENDING = MmrChangeRequest.Status.PENDING


def fresh(req: MmrChangeRequest) -> MmrChangeRequest:
    return MmrChangeRequest.objects.get(pk=req.pk)


class MmrChangeRequestBase(MmrRequestTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.org = Organization.objects.create(name="MMR Req Org")
        self.league = League.objects.create(
            name="MMR Req League", organization=self.org
        )
        self.member = CustomUser.objects.create(username="mmrreq_member")
        self.ou = OrgUser.objects.create(user=self.member, organization=self.org)
        self.lu = LeagueUser.objects.create(
            user=self.member, org_user=self.ou, league=self.league
        )


class ConstraintTests(MmrChangeRequestBase):
    def test_second_pending_org_request_blocked(self) -> None:
        self.make_request(org_user=self.ou)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_request(org_user=self.ou)

    def test_pending_coexists_with_decided(self) -> None:
        self.make_request(org_user=self.ou, status=MmrChangeRequest.Status.REJECTED)
        self.make_request(org_user=self.ou, status=MmrChangeRequest.Status.APPROVED)
        self.make_request(org_user=self.ou)
        self.make_request(org_user=self.ou, game_type=DL)
        self.assertEqual(MmrChangeRequest.objects.count(), 4)

    def test_second_pending_league_request_blocked(self) -> None:
        self.make_request(org_user=self.ou, league_user=self.lu)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_request(org_user=self.ou, league_user=self.lu)

    def test_org_and_league_pending_coexist_for_same_org_user(self) -> None:
        self.make_request(org_user=self.ou)
        self.make_request(org_user=self.ou, league_user=self.lu)
        self.assertEqual(MmrChangeRequest.objects.filter(status=PENDING).count(), 2)

    def test_target_shape_org_with_league_rejected(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_request(
                org_user=self.ou,
                target=MmrChangeRequest.Target.ORG,
                league=self.league,
            )

    def test_league_target_requires_league(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_request(
                org_user=self.ou, target=MmrChangeRequest.Target.LEAGUE, league=None
            )

    def test_member_pending_requires_screenshot(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_request(org_user=self.ou, with_screenshot=False)

    def test_cancelled_may_have_empty_screenshot(self) -> None:
        req = self.make_request(
            org_user=self.ou,
            with_screenshot=False,
            status=MmrChangeRequest.Status.CANCELLED,
        )
        self.assertEqual(fresh(req).screenshot.name, "")

    def test_staff_source_may_omit_screenshot(self) -> None:
        req = self.make_request(
            org_user=self.ou,
            with_screenshot=False,
            source=MmrChangeRequest.Source.STAFF,
            status=MmrChangeRequest.Status.APPROVED,
        )
        self.assertEqual(fresh(req).source, MmrChangeRequest.Source.STAFF)

    def test_pending_requires_membership(self) -> None:
        org_req = self.make_request(org_user=self.ou)
        league_req = self.make_request(org_user=self.ou, league_user=self.lu)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MmrChangeRequest.objects.filter(pk=org_req.pk).update(org_user=None)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MmrChangeRequest.objects.filter(pk=league_req.pk).update(league_user=None)
        MmrChangeRequest.objects.filter(pk=org_req.pk).update(
            status=MmrChangeRequest.Status.REJECTED, org_user=None
        )


class MembershipDeleteTests(MmrChangeRequestBase):
    def test_orguser_delete_keeps_decided_row_set_null(self) -> None:
        req = self.make_request(
            org_user=self.ou, status=MmrChangeRequest.Status.APPROVED
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.ou.delete()
        row = fresh(req)
        self.assertIsNone(row.org_user_id)
        self.assertEqual(row.status, MmrChangeRequest.Status.APPROVED)

    def test_orguser_delete_cancels_pending_and_removes_file(self) -> None:
        org_req = self.make_request(org_user=self.ou)
        league_req = self.make_request(org_user=self.ou, league_user=self.lu)
        self.assertEqual(len(self.media_files()), 2)
        with self.captureOnCommitCallbacks(execute=True):
            self.ou.delete()
        for req in (org_req, league_req):
            row = fresh(req)
            self.assertEqual(row.status, MmrChangeRequest.Status.CANCELLED)
            self.assertEqual(row.screenshot.name, "")
            self.assertIsNone(row.org_user_id)
            self.assertIsNone(row.league_user_id)
        self.assertEqual(self.media_files(), [])

    def test_leagueuser_delete_cancels_pending_league_request(self) -> None:
        org_req = self.make_request(org_user=self.ou)
        league_req = self.make_request(org_user=self.ou, league_user=self.lu)
        with self.captureOnCommitCallbacks(execute=True):
            self.lu.delete()
        league_row = fresh(league_req)
        self.assertEqual(league_row.status, MmrChangeRequest.Status.CANCELLED)
        self.assertIsNone(league_row.league_user_id)
        self.assertEqual(league_row.org_user_id, self.ou.pk)
        self.assertEqual(fresh(org_req).status, PENDING)
        self.assertEqual(len(self.media_files()), 1)

    def test_user_delete_removes_requests_and_files(self) -> None:
        self.make_request(org_user=self.ou)
        self.make_request(org_user=self.ou, league_user=self.lu)
        with self.captureOnCommitCallbacks(execute=True):
            self.member.delete()
        self.assertFalse(MmrChangeRequest.objects.exists())
        self.assertEqual(self.media_files(), [])


class FileTests(MmrChangeRequestBase):
    def test_delete_removes_file_on_commit(self) -> None:
        req = self.make_request(org_user=self.ou)
        self.assertEqual(len(self.media_files()), 1)
        with self.captureOnCommitCallbacks(execute=True):
            req.delete()
        self.assertEqual(self.media_files(), [])

    def test_screenshot_url_raises(self) -> None:
        req = self.make_request(org_user=self.ou)
        with self.assertRaises(NotImplementedError):
            _ = req.screenshot.url

    def test_upload_path_random_and_extension_from_format(self) -> None:
        first = self.make_request(org_user=self.ou)
        second = self.make_request(org_user=self.ou, league_user=self.lu)
        pattern = re.compile(r"^mmr_requests/\d{4}/\d{2}/([0-9a-f]{32})\.png$")
        names = []
        for req in (first, second):
            match = pattern.match(req.screenshot.name)
            self.assertIsNotNone(match, req.screenshot.name)
            assert match is not None
            names.append(match.group(1))
        self.assertNotEqual(names[0], names[1])

    def test_upload_path_rejects_unknown_extension(self) -> None:
        with self.assertRaises(ValueError):
            mmr_screenshot_path(MmrChangeRequest(), "evil.html")

    def test_model_not_cacheops_cached(self) -> None:
        self.assertNotIn("org.mmrchangerequest", settings.CACHEOPS)


class MaySelfVerifyTests(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create(username="selfverify_user")
        self.other = CustomUser.objects.create(username="selfverify_other")
        self.superuser = CustomUser.objects.create(
            username="selfverify_super", is_superuser=True
        )

    def test_may_self_verify_none_actor(self) -> None:
        self.assertTrue(may_self_verify(None, self.user.pk))

    def test_may_self_verify_superuser(self) -> None:
        self.assertTrue(may_self_verify(self.superuser, self.superuser.pk))

    def test_may_self_verify_self(self) -> None:
        self.assertFalse(may_self_verify(self.user, self.user.pk))

    def test_may_self_verify_other(self) -> None:
        self.assertTrue(may_self_verify(self.other, self.user.pk))


class ReviewPermissionTests(MmrChangeRequestBase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = CustomUser.objects.create(username="perm_owner")
        self.org.owner = self.owner
        self.org.save()
        self.org_admin = CustomUser.objects.create(username="perm_org_admin")
        self.org.admins.add(self.org_admin)
        self.org_staff = CustomUser.objects.create(username="perm_org_staff")
        self.org_staff2 = CustomUser.objects.create(username="perm_org_staff2")
        self.org.staff.add(self.org_staff, self.org_staff2)
        self.league_staff = CustomUser.objects.create(username="perm_league_staff")
        self.league.staff.add(self.league_staff)
        other_org = Organization.objects.create(name="Other MMR Org")
        self.other_staff = CustomUser.objects.create(username="perm_other_staff")
        other_org.staff.add(self.other_staff)
        self.superuser = CustomUser.objects.create(
            username="perm_super", is_superuser=True
        )
        self.org_req = self.make_request(org_user=self.ou)
        self.league_req = self.make_request(org_user=self.ou, league_user=self.lu)

        staff_ou = OrgUser.objects.create(user=self.org_staff, organization=self.org)
        self.staff_subject_req = self.make_request(org_user=staff_ou)
        super_ou = OrgUser.objects.create(user=self.superuser, organization=self.org)
        self.super_self_req = self.make_request(org_user=super_ou)

    def _check(self, user: CustomUser, req: MmrChangeRequest) -> bool:
        return can_review_mmr_request(CustomUser.objects.get(pk=user.pk), fresh(req))

    def test_can_review_mmr_request_matrix(self) -> None:
        cases = [
            ("org staff on org target", self.org_staff, self.org_req, True),
            ("league staff on org target", self.league_staff, self.org_req, False),
            ("league staff on league target", self.league_staff, self.league_req, True),
            ("org staff on league target", self.org_staff, self.league_req, True),
            ("staff of other org", self.other_staff, self.org_req, False),
            ("staff of other org league", self.other_staff, self.league_req, False),
            ("self", self.member, self.org_req, False),
            (
                "staff subject, staff reviewer",
                self.org_staff2,
                self.staff_subject_req,
                False,
            ),
            (
                "staff subject, admin reviewer",
                self.org_admin,
                self.staff_subject_req,
                True,
            ),
            ("staff subject, self", self.org_staff, self.staff_subject_req, False),
            ("owner", self.owner, self.org_req, True),
            ("owner on staff subject", self.owner, self.staff_subject_req, True),
            ("superuser self", self.superuser, self.super_self_req, True),
        ]
        for label, user, req, expected in cases:
            with self.subTest(label):
                self.assertEqual(self._check(user, req), expected)

    def test_org_queue_filter(self) -> None:
        other_org = Organization.objects.create(name="Queue Other Org")
        foreign_league = League.objects.create(name="Foreign", organization=other_org)
        foreign_lu = LeagueUser.objects.create(
            user=self.member, org_user=self.ou, league=foreign_league
        )
        foreign_req = self.make_request(org_user=self.ou, league_user=foreign_lu)
        ids = set(
            MmrChangeRequest.objects.filter(org_queue_filter(self.org.pk)).values_list(
                "pk", flat=True
            )
        )
        self.assertIn(self.org_req.pk, ids)
        self.assertIn(self.league_req.pk, ids)
        self.assertNotIn(foreign_req.pk, ids)
