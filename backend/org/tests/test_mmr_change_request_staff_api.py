from typing import Any
from unittest.mock import patch

from django.db import IntegrityError, connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient, APITestCase

from app.models import CustomUser, GameType
from events.constants import SignupStatus
from events.models import Event, EventSignup
from league.models import League, LeagueLog, LeagueUser
from org.mmr import LEAGUE_GAME, set_org_mmr
from org.mmr_requests.permissions import can_review_mmr_request
from org.mmr_requests.services import staff_set_mmr
from org.models import MmrChangeRequest, Organization, OrgLog, OrgUser, OrgUserGameMmr
from org.tests.mmr_request_mixin import MmrRequestTestMixin
from user.tests.test_cacheops_integration import _redis_reachable

DOTA = GameType.DOTA2
DL = GameType.DEADLOCK
S = MmrChangeRequest.Status


def org_mmr(org_user: OrgUser, game_type: int) -> OrgUserGameMmr | None:
    return (
        OrgUserGameMmr.objects.nocache()
        .filter(org_user=org_user, game_type=game_type)
        .first()
    )


def fresh(req: MmrChangeRequest) -> MmrChangeRequest:
    return MmrChangeRequest.objects.get(pk=req.pk)


class StaffApiFixture(MmrRequestTestMixin):
    def build(self) -> None:
        def user(name: str, **kw: Any) -> CustomUser:
            return CustomUser.objects.create(username=f"msa_{name}", **kw)

        self.owner = user("owner")
        self.admin = user("admin")
        self.staff = user("staff")
        self.member = user("member")
        self.other = user("other")
        self.league_staff = user("lstaff")
        self.foreign_staff = user("fstaff")
        self.superuser = user("super", is_superuser=True)

        self.org = Organization.objects.create(name="MSA Org", owner=self.owner)
        self.org.admins.add(self.admin)
        self.org.staff.add(self.staff)
        self.foreign_org = Organization.objects.create(name="MSA Foreign")
        self.foreign_org.staff.add(self.foreign_staff)

        self.league = League.objects.create(name="MSA League", organization=self.org)
        self.league.staff.add(self.league_staff)
        self.orgless = League.objects.create(name="MSA Orgless")
        self.orgless.staff.add(self.league_staff)
        self.foreign_league = League.objects.create(
            name="MSA Foreign League", organization=self.foreign_org
        )

        self.ou = OrgUser.objects.create(user=self.member, organization=self.org)
        self.other_ou = OrgUser.objects.create(user=self.other, organization=self.org)
        self.lu = LeagueUser.objects.create(
            user=self.member, org_user=self.ou, league=self.league, mmr=3100
        )
        self.orgless_lu = LeagueUser.objects.create(
            user=self.member, org_user=self.ou, league=self.orgless, mmr=2000
        )

    def as_(self, user: CustomUser | None) -> APIClient:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def org_request(self, **kw: Any) -> MmrChangeRequest:
        kw.setdefault("game_type", DOTA)
        return self.make_request(org_user=self.ou, **kw)

    def league_request(self, **kw: Any) -> MmrChangeRequest:
        return self.make_request(org_user=self.ou, league_user=self.lu, **kw)

    def approve(self, user: CustomUser, req: MmrChangeRequest, **body: Any) -> Any:
        return self.as_(user).post(
            f"/api/mmr-requests/{req.pk}/approve/", body, format="json"
        )

    def reject(self, user: CustomUser, req: MmrChangeRequest, reason: Any) -> Any:
        return self.as_(user).post(
            f"/api/mmr-requests/{req.pk}/reject/", {"reason": reason}, format="json"
        )

    def staff_set(
        self, user: CustomUser, data: dict[str, Any], *, league: League | None = None
    ) -> Any:
        url = (
            f"/api/leagues/{league.pk}/mmr-requests/staff-set/"
            if league is not None
            else f"/api/organizations/{self.org.pk}/mmr-requests/staff-set/"
        )
        return self.as_(user).post(url, data, format="multipart")


class StaffApiBase(StaffApiFixture, APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.build()


class QueueTests(StaffApiBase):
    def org_url(self, suffix: str = "") -> str:
        return f"/api/organizations/{self.org.pk}/mmr-requests/{suffix}"

    def league_url(self, league: League, suffix: str = "") -> str:
        return f"/api/leagues/{league.pk}/mmr-requests/{suffix}"

    def test_org_scope_access_matrix(self) -> None:
        self.org_request()
        self.league_request()
        cases: list[tuple[str, CustomUser | None, int]] = [
            ("anon", None, 403),
            ("member", self.member, 403),
            ("other", self.other, 403),
            ("league_staff", self.league_staff, 403),
            ("foreign_staff", self.foreign_staff, 403),
            ("staff", self.staff, 200),
            ("admin", self.admin, 200),
            ("owner", self.owner, 200),
            ("superuser", self.superuser, 200),
        ]
        for label, user, code in cases:
            with self.subTest(label):
                client = self.as_(user)
                listed = client.get(self.org_url())
                counted = client.get(self.org_url("pending-count/"))
                self.assertEqual(listed.status_code, code, listed.content)
                self.assertEqual(counted.status_code, code, counted.content)
                if code == 200:
                    self.assertEqual(len(listed.json()), 2)
                    self.assertEqual(counted.json(), {"count": 2})

    def test_league_scope_access_matrix(self) -> None:
        self.org_request()
        self.league_request()
        cases: list[tuple[str, CustomUser | None, int]] = [
            ("anon", None, 403),
            ("member", self.member, 403),
            ("other", self.other, 403),
            ("foreign_staff", self.foreign_staff, 403),
            ("league_staff", self.league_staff, 200),
            ("staff", self.staff, 200),
            ("admin", self.admin, 200),
            ("owner", self.owner, 200),
            ("superuser", self.superuser, 200),
        ]
        for label, user, code in cases:
            with self.subTest(label):
                client = self.as_(user)
                listed = client.get(self.league_url(self.league))
                counted = client.get(self.league_url(self.league, "pending-count/"))
                self.assertEqual(listed.status_code, code, listed.content)
                self.assertEqual(counted.status_code, code, counted.content)
                if code == 200:
                    [row] = listed.json()
                    self.assertEqual(row["target"], "league")
                    self.assertEqual(counted.json(), {"count": 1})

    def test_status_filter(self) -> None:
        pending = self.org_request()
        rejected = self.org_request(game_type=DL, status=S.REJECTED)
        client = self.as_(self.staff)
        self.assertEqual(
            [r["id"] for r in client.get(self.org_url()).json()], [pending.pk]
        )
        self.assertEqual(
            [r["id"] for r in client.get(self.org_url() + "?status=rejected").json()],
            [rejected.pk],
        )
        self.assertEqual(len(client.get(self.org_url() + "?status=all").json()), 2)
        self.assertEqual(client.get(self.org_url() + "?status=bogus").status_code, 400)

    def test_league_filter(self) -> None:
        self.org_request()
        league_req = self.league_request()
        response = self.as_(self.staff).get(
            self.org_url() + f"?league={self.league.pk}"
        )
        self.assertEqual([r["id"] for r in response.json()], [league_req.pk])

    def test_org_scope_excludes_orgless_and_other_org_leagues(self) -> None:
        orgless_req = self.make_request(org_user=self.ou, league_user=self.orgless_lu)
        foreign_ou = OrgUser.objects.create(
            user=self.member, organization=self.foreign_org
        )
        foreign_lu = LeagueUser.objects.create(
            user=self.member, org_user=foreign_ou, league=self.foreign_league
        )
        self.make_request(org_user=foreign_ou, league_user=foreign_lu)
        org_req = self.org_request()

        response = self.as_(self.owner).get(self.org_url())

        ids = [r["id"] for r in response.json()]
        self.assertEqual(ids, [org_req.pk])
        self.assertNotIn(orgless_req.pk, ids)

    def test_league_scope_includes_orgless_league_requests(self) -> None:
        req = self.make_request(org_user=self.ou, league_user=self.orgless_lu)
        response = self.as_(self.league_staff).get(self.league_url(self.orgless))
        self.assertEqual([r["id"] for r in response.json()], [req.pk])
        count = self.as_(self.league_staff).get(
            self.league_url(self.orgless, "pending-count/")
        )
        self.assertEqual(count.json(), {"count": 1})

    def test_league_unlinked_after_create_moves_out_of_org_queue(self) -> None:
        req = self.league_request()
        self.league.organization = None
        self.league.save()

        org_rows = self.as_(self.owner).get(self.org_url()).json()
        league_rows = self.as_(self.league_staff).get(self.league_url(self.league))
        approved = self.approve(self.league_staff, req)

        self.assertEqual(org_rows, [])
        self.assertEqual([r["id"] for r in league_rows.json()], [req.pk])
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(LeagueUser.objects.nocache().get(pk=self.lu.pk).mmr, 4000)

    def test_list_query_count_scale_invariant(self) -> None:
        self.org_request()
        self.league_request()

        def count_queries() -> int:
            client = self.as_(self.staff)
            client.get(self.org_url())
            with CaptureQueriesContext(connection) as ctx:
                response = client.get(self.org_url() + "?status=all")
            self.assertEqual(response.status_code, 200)
            return len(ctx.captured_queries)

        small = count_queries()
        extra_users = [
            CustomUser.objects.create(username=f"msa_scale{i}") for i in range(2)
        ]
        extra_ous = [
            OrgUser.objects.create(user=u, organization=self.org) for u in extra_users
        ]
        self.org.staff.add(extra_users[0])
        self.org_request(game_type=DL)
        for ou in extra_ous:
            LeagueUser.objects.create(user=ou.user, org_user=ou, league=self.league)
            self.make_request(org_user=ou, game_type=DOTA)
        self.make_request(org_user=extra_ous[0], game_type=DL, status=S.REJECTED)
        self.assertEqual(MmrChangeRequest.objects.count(), 6)

        self.assertEqual(count_queries(), small)

    def test_no_payload_contains_media_path(self) -> None:
        req = self.org_request()
        client = self.as_(self.staff)
        responses = [
            client.get(self.org_url() + "?status=all"),
            client.get(self.league_url(self.league)),
            self.approve(self.staff, req),
            self.staff_set(
                self.staff,
                {
                    "target": "league",
                    "league_user": self.lu.pk,
                    "mmr": 4200,
                    "screenshot": self.png_upload(),
                },
            ),
        ]
        for response in responses:
            self.assertLess(response.status_code, 300, response.content)
            self.assertNotIn(b"mmr_requests/", response.content)


class ApproveTests(StaffApiBase):
    def test_approve_plain_writes_official(self) -> None:
        req = self.org_request(requested_mmr=4500)

        response = self.approve(self.staff, req)

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["status"], "approved")
        self.assertEqual(body["approved_mmr"], 4500)
        self.assertEqual(body["reviewed_by_username"], self.staff.username)
        self.assertTrue(body["current_verified"])
        row = org_mmr(self.ou, DOTA)
        assert row is not None
        self.assertEqual(row.mmr, 4500)
        self.assertEqual(row.verified_by, self.staff)
        req = fresh(req)
        self.assertEqual(req.status, S.APPROVED)
        self.assertEqual(req.reviewed_by, self.staff)
        self.assertIsNotNone(req.reviewed_at)
        [entry] = OrgLog.objects.filter(organization=self.org, action="set_mmr")
        self.assertEqual(entry.details["source"], "mmr_request")
        self.assertEqual(entry.details["request_id"], req.pk)
        self.assertEqual(entry.actor, self.staff)

    def test_approve_adjusted_value(self) -> None:
        req = self.org_request(requested_mmr=4500)

        response = self.approve(self.staff, req, mmr=4400)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(fresh(req).approved_mmr, 4400)
        row = org_mmr(self.ou, DOTA)
        assert row is not None
        self.assertEqual(row.mmr, 4400)

    def test_approve_adjusted_zero_400(self) -> None:
        req = self.org_request()
        for value in (0, 20001, "abc"):
            with self.subTest(value=value):
                response = self.approve(self.staff, req, mmr=value)
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(fresh(req).status, S.PENDING)
        self.assertIsNone(org_mmr(self.ou, DOTA))

    def test_approve_league_target_uses_set_league_mmr(self) -> None:
        req = self.league_request(requested_mmr=4700)

        response = self.approve(self.league_staff, req)

        self.assertEqual(response.status_code, 200, response.content)
        lu = LeagueUser.objects.nocache().get(pk=self.lu.pk)
        self.assertEqual(lu.mmr, 4700)
        self.assertEqual(lu.mmr_verified_by, self.league_staff)
        [entry] = LeagueLog.objects.filter(league=self.league, action="set_mmr")
        self.assertEqual(entry.details["request_id"], req.pk)
        self.assertEqual(entry.details["source"], "mmr_request")

    def test_second_approve_409(self) -> None:
        req = self.org_request()
        self.assertEqual(self.approve(self.staff, req).status_code, 200)

        response = self.approve(self.admin, req, mmr=4100)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(), {"error": "not_pending", "status": "approved"}
        )
        row = org_mmr(self.ou, DOTA)
        assert row is not None
        self.assertEqual(row.mmr, 4000)

    def test_approve_after_cancel_409(self) -> None:
        req = self.org_request()
        self.as_(self.member).post(f"/api/mmr-requests/{req.pk}/cancel/")

        response = self.approve(self.staff, req)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "cancelled")

    def test_approve_superseded_409(self) -> None:
        req = self.org_request(status=S.SUPERSEDED)
        response = self.approve(self.staff, req)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "superseded")

    def test_approve_missing_404(self) -> None:
        self.assertEqual(
            self.as_(self.staff)
            .post("/api/mmr-requests/999999/approve/", {}, format="json")
            .status_code,
            404,
        )

    def test_approve_by_non_reviewer_403(self) -> None:
        req = self.org_request()
        for user in (self.other, self.foreign_staff, self.league_staff):
            with self.subTest(user=user.username):
                self.assertEqual(self.approve(user, req).status_code, 403)
        self.assertEqual(
            self.as_(None)
            .post(f"/api/mmr-requests/{req.pk}/approve/", {}, format="json")
            .status_code,
            403,
        )
        self.assertEqual(fresh(req).status, S.PENDING)

    def test_orguser_orm_delete_with_pending_then_approve_409(self) -> None:
        req = self.org_request()
        with self.captureOnCommitCallbacks(execute=True):
            OrgUser.objects.get(pk=self.ou.pk).delete()
        req = fresh(req)
        self.assertEqual(req.status, S.CANCELLED)
        self.assertEqual(self.media_files(), [])

        response = self.approve(self.staff, req)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "cancelled")
        self.assertFalse(OrgUserGameMmr.objects.nocache().exists())

    def test_subject_user_delete_removes_requests_and_files(self) -> None:
        self.org_request()
        self.league_request()
        self.assertEqual(len(self.media_files()), 2)

        with self.captureOnCommitCallbacks(execute=True):
            CustomUser.objects.get(pk=self.member.pk).delete()

        self.assertFalse(MmrChangeRequest.objects.exists())
        self.assertEqual(self.media_files(), [])

    def test_patch_supersede_then_approve_409(self) -> None:
        set_org_mmr(self.ou, DOTA, 3500, mark_verified=False)
        req = self.org_request(requested_mmr=4500)
        patched = self.as_(self.staff).patch(
            f"/api/organizations/{self.org.pk}/users/{self.ou.pk}/",
            {"game_mmrs": {str(int(DOTA)): 3900}},
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.content)

        response = self.approve(self.admin, req)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "superseded")
        row = org_mmr(self.ou, DOTA)
        assert row is not None
        self.assertEqual(row.mmr, 3900)

    def test_event_approve_supersede_then_approve_409(self) -> None:
        req = self.org_request(requested_mmr=4500)
        event = Event.objects.create(
            organization=self.org,
            name="MSA Event",
            scheduled_at="2030-01-01T00:00:00Z",
            timezone="UTC",
            created_by=self.owner,
            game_type=DOTA,
        )
        signup = EventSignup.objects.create(
            event=event, user=self.member, status=SignupStatus.RSVP
        )
        approved = self.as_(self.owner).post(
            f"/api/events/signups/{signup.pk}/approve/", {"mmr": 4300}, format="json"
        )
        self.assertEqual(approved.status_code, 200, approved.content)

        response = self.approve(self.staff, req)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "superseded")
        row = org_mmr(self.ou, DOTA)
        assert row is not None
        self.assertEqual(row.mmr, 4300)

    def test_approve_refreshes_unmet_and_invalidates_league_rows(self) -> None:
        req = self.org_request()
        with (
            patch("org.mmr_official.refresh_unmet_requirements") as refresh,
            patch("org.mmr_official.invalidate_after_commit") as invalidate,
        ):
            response = self.approve(self.staff, req)

        self.assertEqual(response.status_code, 200, response.content)
        refresh.assert_called_once()
        self.assertEqual(refresh.call_args.args[0].pk, self.ou.pk)
        invalidated = invalidate.call_args.args
        self.assertIn(self.lu, invalidated)
        self.assertIn(self.orgless_lu, invalidated)
        self.assertIn(self.league, invalidated)


class RejectTests(StaffApiBase):
    def test_reject_requires_reason_400(self) -> None:
        req = self.org_request()
        for reason in ("", "   "):
            with self.subTest(reason=reason):
                response = self.reject(self.staff, req, reason)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("reason", response.json())
        self.assertEqual(fresh(req).status, S.PENDING)

    def test_reject_reason_501_400(self) -> None:
        req = self.org_request()
        self.assertEqual(self.reject(self.staff, req, "x" * 501).status_code, 400)
        self.assertEqual(self.reject(self.staff, req, "x" * 500).status_code, 200)

    def test_reject_sets_reason_and_reviewer(self) -> None:
        req = self.org_request()

        response = self.reject(self.staff, req, "Blurry screenshot")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["rejection_reason"], "Blurry screenshot")
        req = fresh(req)
        self.assertEqual(req.status, S.REJECTED)
        self.assertEqual(req.reviewed_by, self.staff)
        self.assertIsNotNone(req.reviewed_at)
        self.assertIsNone(org_mmr(self.ou, DOTA))

    def test_reject_not_pending_409(self) -> None:
        req = self.org_request(status=S.APPROVED)
        response = self.reject(self.staff, req, "no")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(), {"error": "not_pending", "status": "approved"}
        )


class SelfReviewTests(StaffApiBase):
    def test_subject_cannot_approve_reject_or_staff_set_self(self) -> None:
        for reviewer in (self.staff, self.admin, self.owner):
            with self.subTest(reviewer=reviewer.username):
                MmrChangeRequest.objects.all().delete()
                own_ou, _ = OrgUser.objects.get_or_create(
                    user=reviewer, organization=self.org
                )
                req = self.make_request(org_user=own_ou, game_type=DOTA)

                approve = self.approve(reviewer, req)
                reject = self.reject(reviewer, req, "nope")
                staff_set = self.staff_set(
                    reviewer,
                    {
                        "target": "org",
                        "org_user": own_ou.pk,
                        "game_type": int(DOTA),
                        "mmr": 5000,
                    },
                )

                for response in (approve, reject, staff_set):
                    self.assertEqual(response.status_code, 403, response.content)
                    self.assertEqual(response.json(), {"error": "self_review"})
                self.assertEqual(fresh(req).status, S.PENDING)
                self.assertIsNone(org_mmr(own_ou, DOTA))

    def test_superuser_may_review_self(self) -> None:
        own_ou = OrgUser.objects.create(user=self.superuser, organization=self.org)
        req = self.make_request(org_user=own_ou, game_type=DOTA)
        self.assertEqual(self.approve(self.superuser, req).status_code, 200)

    def test_staff_subject_needs_admin_reviewer(self) -> None:
        colleague = CustomUser.objects.create(username="msa_colleague")
        self.org.staff.add(colleague)
        staff_ou = OrgUser.objects.create(user=colleague, organization=self.org)
        req = self.make_request(org_user=staff_ou, game_type=DOTA)

        denied = self.approve(self.staff, req)
        allowed = self.approve(self.admin, req)

        self.assertEqual(denied.status_code, 403, denied.content)
        self.assertNotEqual(denied.json(), {"error": "self_review"})
        self.assertEqual(allowed.status_code, 200, allowed.content)

    def test_owner_counts_as_admin_for_staff_subject(self) -> None:
        staff_ou = OrgUser.objects.create(user=self.staff, organization=self.org)
        req = self.make_request(org_user=staff_ou, game_type=DOTA)
        self.assertEqual(self.approve(self.owner, req).status_code, 200)

    def test_can_review_flag_matches_permission(self) -> None:
        colleague = CustomUser.objects.create(username="msa_colleague2")
        self.org.staff.add(colleague)
        staff_ou = OrgUser.objects.create(user=colleague, organization=self.org)
        LeagueUser.objects.create(user=colleague, org_user=staff_ou, league=self.league)
        rows = [
            self.org_request(),
            self.league_request(),
            self.make_request(org_user=staff_ou, game_type=DOTA),
            self.make_request(org_user=self.ou, league_user=self.orgless_lu),
        ]
        viewers = [
            self.staff,
            self.admin,
            self.owner,
            self.league_staff,
            colleague,
            self.superuser,
            self.member,
        ]
        for viewer in viewers:
            with self.subTest(viewer=viewer.username):
                listed = self.as_(viewer).get("/api/mmr-requests/mine/")
                self.assertEqual(listed.status_code, 200)
                payload: dict[int, bool] = {}
                for scope in (
                    f"/api/organizations/{self.org.pk}/mmr-requests/?status=all",
                    f"/api/leagues/{self.league.pk}/mmr-requests/?status=all",
                    f"/api/leagues/{self.orgless.pk}/mmr-requests/?status=all",
                ):
                    response = self.as_(viewer).get(scope)
                    if response.status_code == 200:
                        payload.update(
                            {r["id"]: r["can_review"] for r in response.json()}
                        )
                for row in rows:
                    if row.pk not in payload:
                        continue
                    expected = can_review_mmr_request(viewer, fresh(row))
                    self.assertEqual(payload[row.pk], expected, (viewer, row.pk))
                own = {r["id"]: r["can_review"] for r in listed.json()}
                for pk, flag in own.items():
                    self.assertEqual(
                        flag,
                        can_review_mmr_request(
                            viewer, MmrChangeRequest.objects.get(pk=pk)
                        ),
                    )


class StaffSetTests(StaffApiBase):
    def test_staff_set_org_without_screenshot_201_official(self) -> None:
        response = self.staff_set(
            self.staff,
            {
                "target": "org",
                "org_user": self.ou.pk,
                "game_type": int(DL),
                "mmr": 2100,
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], "approved")
        self.assertEqual(body["source"], "staff")
        self.assertFalse(body["has_screenshot"])
        req = MmrChangeRequest.objects.get()
        self.assertEqual(req.requester, self.staff)
        self.assertEqual(req.subject_user, self.member)
        self.assertEqual(req.approved_mmr, 2100)
        self.assertEqual(req.reviewed_by, self.staff)
        row = org_mmr(self.ou, DL)
        assert row is not None
        self.assertEqual(row.mmr, 2100)
        self.assertEqual(row.verified_by, self.staff)
        [entry] = OrgLog.objects.filter(organization=self.org, action="set_mmr")
        self.assertEqual(entry.details["request_id"], req.pk)

    def test_staff_set_league_with_screenshot(self) -> None:
        response = self.staff_set(
            self.league_staff,
            {
                "target": "league",
                "league_user": self.lu.pk,
                "mmr": 5200,
                "screenshot": self.png_upload(),
                "note": "verified in lobby",
            },
            league=self.league,
        )

        self.assertEqual(response.status_code, 201, response.content)
        req = MmrChangeRequest.objects.get()
        self.assertEqual(req.target, "league")
        self.assertEqual(req.game_type, LEAGUE_GAME)
        self.assertEqual(req.previous_mmr, 3100)
        self.assertEqual(req.note, "verified in lobby")
        self.assertTrue(req.screenshot.name)
        self.assertEqual(len(self.media_files()), 1)
        lu = LeagueUser.objects.nocache().get(pk=self.lu.pk)
        self.assertEqual(lu.mmr, 5200)
        self.assertIsNotNone(lu.mmr_verified_at)

    def test_staff_set_zero_400(self) -> None:
        response = self.staff_set(
            self.staff,
            {"target": "org", "org_user": self.ou.pk, "game_type": int(DOTA), "mmr": 0},
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("mmr", response.json())
        self.assertFalse(MmrChangeRequest.objects.exists())

    def test_staff_set_supersedes_pending_then_approve_409(self) -> None:
        req = self.org_request(requested_mmr=4500)
        response = self.staff_set(
            self.admin,
            {
                "target": "org",
                "org_user": self.ou.pk,
                "game_type": int(DOTA),
                "mmr": 4200,
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(fresh(req).status, S.SUPERSEDED)

        approve = self.approve(self.staff, req)

        self.assertEqual(approve.status_code, 409)
        row = org_mmr(self.ou, DOTA)
        assert row is not None
        self.assertEqual(row.mmr, 4200)

    def test_staff_set_integrity_failure_leaves_no_file(self) -> None:
        with (
            patch(
                "org.mmr_requests.services.apply_official_org_mmr",
                side_effect=IntegrityError("boom"),
            ),
            self.assertRaises(IntegrityError),
        ):
            staff_set_mmr(
                actor=self.staff,
                target="org",
                org_user=self.ou,
                league_user=None,
                game_type=DOTA,
                mmr=4000,
                screenshot=self.png_upload(),
                note="",
            )
        self.assertEqual(self.media_files(), [])
        self.assertFalse(MmrChangeRequest.objects.exists())

    def test_staff_set_league_staff_cannot_set_org_target_403(self) -> None:
        data = {
            "target": "org",
            "org_user": self.ou.pk,
            "game_type": int(DOTA),
            "mmr": 4000,
        }
        org_scope = self.staff_set(self.league_staff, data)
        league_scope = self.staff_set(self.league_staff, data, league=self.league)

        self.assertEqual(org_scope.status_code, 403, org_scope.content)
        self.assertEqual(league_scope.status_code, 400, league_scope.content)
        self.assertFalse(MmrChangeRequest.objects.exists())
        self.assertIsNone(org_mmr(self.ou, DOTA))

    def test_staff_set_out_of_scope_membership_400(self) -> None:
        foreign_ou = OrgUser.objects.create(
            user=self.other, organization=self.foreign_org
        )
        foreign_lu = LeagueUser.objects.create(
            user=self.other, org_user=foreign_ou, league=self.foreign_league
        )
        org_target = self.staff_set(
            self.staff,
            {"target": "org", "org_user": foreign_ou.pk, "game_type": 1, "mmr": 4000},
        )
        league_target = self.staff_set(
            self.staff,
            {"target": "league", "league_user": foreign_lu.pk, "mmr": 4000},
        )
        self.assertEqual(org_target.status_code, 400, org_target.content)
        self.assertEqual(league_target.status_code, 400, league_target.content)
        self.assertFalse(MmrChangeRequest.objects.exists())

    def test_staff_set_anonymous_403(self) -> None:
        response = self.staff_set(
            None,  # type: ignore[arg-type]
            {"target": "org", "org_user": self.ou.pk, "game_type": 1, "mmr": 4000},
        )
        self.assertEqual(response.status_code, 403)


class ApproveRealCacheopsTests(StaffApiFixture, TransactionTestCase):
    def setUp(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")
        super().setUp()
        self.build()

    def test_approve_real_cacheops_read_after_write(self) -> None:
        set_org_mmr(self.ou, DOTA, 3000, mark_verified=False)
        org_req = self.org_request(requested_mmr=4400)
        league_req = self.league_request(requested_mmr=4900)
        self.assertEqual(
            OrgUserGameMmr.objects.get(org_user=self.ou, game_type=DOTA).mmr, 3000
        )
        self.assertIsNone(
            OrgUserGameMmr.objects.get(org_user=self.ou, game_type=DOTA).verified_at
        )
        self.assertEqual(LeagueUser.objects.get(pk=self.lu.pk).mmr, 3100)
        list(OrgUser.objects.filter(pk=self.ou.pk))

        self.assertEqual(self.approve(self.staff, org_req).status_code, 200)
        self.assertEqual(self.approve(self.staff, league_req).status_code, 200)

        cached_org = OrgUserGameMmr.objects.get(org_user=self.ou, game_type=DOTA)
        self.assertEqual(cached_org.mmr, 4400)
        self.assertIsNotNone(cached_org.verified_at)
        cached_league = LeagueUser.objects.get(pk=self.lu.pk)
        self.assertEqual(cached_league.mmr, 4900)
        self.assertIsNotNone(cached_league.mmr_verified_at)
