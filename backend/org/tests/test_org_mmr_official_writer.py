from typing import Any
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, GameType
from events.constants import SignupStatus
from events.models import Event, EventSignup
from league.mmr import set_league_mmr
from league.models import League, LeagueUser
from org.mmr import set_org_mmr
from org.mmr_official import apply_official_org_mmr
from org.mmr_requests.permissions import may_verify_league_mmr, may_verify_org_mmr
from org.models import MmrChangeRequest, Organization, OrgLog, OrgUser, OrgUserGameMmr
from org.tests.mmr_request_mixin import MmrRequestTestMixin

DOTA = GameType.DOTA2
DL = GameType.DEADLOCK
PENDING = MmrChangeRequest.Status.PENDING
SUPERSEDED = MmrChangeRequest.Status.SUPERSEDED


def row(org_user: OrgUser, game_type: int) -> OrgUserGameMmr | None:
    return (
        OrgUserGameMmr.objects.nocache()
        .filter(org_user=org_user, game_type=game_type)
        .first()
    )


def fresh(req: MmrChangeRequest) -> MmrChangeRequest:
    return MmrChangeRequest.objects.get(pk=req.pk)


class WriterBase(MmrRequestTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = CustomUser.objects.create(username="ow_owner")
        self.staff = CustomUser.objects.create(username="ow_staff")
        self.member = CustomUser.objects.create(username="ow_member")
        self.org = Organization.objects.create(name="Writer Org", owner=self.owner)
        self.org.staff.add(self.staff)
        self.ou = OrgUser.objects.create(user=self.member, organization=self.org)

    def fresh_ou(self) -> OrgUser:
        return OrgUser.objects.nocache().get(pk=self.ou.pk)

    def set_mmr_logs(self) -> list[OrgLog]:
        return list(OrgLog.objects.filter(organization=self.org, action="set_mmr"))


class ApplyOfficialOrgMmrTests(WriterBase):
    def test_apply_sets_verified_marker_and_logs(self) -> None:
        set_org_mmr(self.ou, DL, 2000, mark_verified=False)

        result = apply_official_org_mmr(
            self.ou, DL, 3000, actor=self.staff, source="org_user_patch"
        )

        self.assertEqual(
            (result.value, result.previous, result.verified, result.changed),
            (3000, 2000, True, True),
        )
        r = row(self.ou, DL)
        assert r is not None
        self.assertEqual(r.mmr, 3000)
        self.assertEqual(r.verified_by, self.staff)
        self.assertIsNotNone(r.verified_at)
        [entry] = self.set_mmr_logs()
        self.assertEqual(entry.actor, self.staff)
        self.assertEqual(entry.target_user, self.member)
        self.assertEqual(
            entry.details,
            {
                "game_type": DL,
                "mmr": 3000,
                "source": "org_user_patch",
                "previous_mmr": 2000,
                "verified": True,
            },
        )

    def test_apply_self_writes_unverified(self) -> None:
        pending = self.make_request(org_user=self.ou)

        result = apply_official_org_mmr(
            self.ou, DOTA, 5000, actor=self.member, source="org_user_patch"
        )

        self.assertFalse(result.verified)
        self.assertEqual(result.superseded_ids, [])
        r = row(self.ou, DOTA)
        assert r is not None
        self.assertEqual(r.mmr, 5000)
        self.assertIsNone(r.verified_at)
        self.assertIsNone(r.verified_by)
        self.assertFalse(self.fresh_ou().has_active_dota_mmr)
        self.assertEqual(fresh(pending).status, PENDING)
        [entry] = self.set_mmr_logs()
        self.assertFalse(entry.details["verified"])

    def test_apply_unchanged_value_stamps_marker_without_log(self) -> None:
        set_org_mmr(self.ou, DOTA, 4000, mark_verified=False)

        result = apply_official_org_mmr(
            self.ou, DOTA, 4000, actor=self.staff, source="org_user_patch"
        )

        self.assertFalse(result.changed)
        self.assertTrue(result.verified)
        r = row(self.ou, DOTA)
        assert r is not None
        self.assertEqual(r.verified_by, self.staff)
        self.assertIsNotNone(r.verified_at)
        ou = self.fresh_ou()
        self.assertTrue(ou.has_active_dota_mmr)
        self.assertIsNotNone(ou.dota_mmr_last_verified)
        self.assertEqual(self.set_mmr_logs(), [])

    def test_apply_unchanged_with_log_unchanged_logs(self) -> None:
        set_org_mmr(self.ou, DL, 2500, mark_verified=False)

        apply_official_org_mmr(
            self.ou,
            DL,
            2500,
            actor=self.staff,
            source="event_approve",
            extra_log={"event_id": 77},
            log_unchanged=True,
        )

        [entry] = self.set_mmr_logs()
        self.assertEqual(
            entry.details,
            {
                "game_type": DL,
                "mmr": 2500,
                "source": "event_approve",
                "previous_mmr": 2500,
                "verified": True,
                "event_id": 77,
            },
        )

    def test_apply_with_request_logs_request_id(self) -> None:
        req = self.make_request(org_user=self.ou, game_type=DL)

        apply_official_org_mmr(
            self.ou, DL, 0, actor=self.staff, source="mmr_request", request=req
        )

        [entry] = self.set_mmr_logs()
        self.assertEqual(entry.details["request_id"], req.pk)
        self.assertEqual(fresh(req).status, PENDING)

    def test_apply_zero_dota_deletes_row_and_sets_flags(self) -> None:
        set_org_mmr(self.ou, DOTA, 4000, mark_verified=False)

        result = apply_official_org_mmr(
            self.ou, DOTA, 0, actor=self.staff, source="org_user_patch"
        )

        self.assertTrue(result.changed)
        self.assertIsNone(row(self.ou, DOTA))
        ou = self.fresh_ou()
        self.assertTrue(ou.has_active_dota_mmr)
        self.assertIsNotNone(ou.dota_mmr_last_verified)
        self.assertEqual(len(self.set_mmr_logs()), 1)

    def test_apply_zero_dota_missing_row_sets_flags(self) -> None:
        result = apply_official_org_mmr(
            self.ou, DOTA, 0, actor=self.staff, source="org_user_patch"
        )

        self.assertFalse(result.changed)
        self.assertIsNone(row(self.ou, DOTA))
        ou = self.fresh_ou()
        self.assertTrue(ou.has_active_dota_mmr)
        self.assertIsNotNone(ou.dota_mmr_last_verified)
        self.assertEqual(self.set_mmr_logs(), [])

    def test_apply_zero_deadlock_missing_row_noop(self) -> None:
        result = apply_official_org_mmr(
            self.ou, DL, 0, actor=self.staff, source="org_user_patch"
        )

        self.assertFalse(result.changed)
        self.assertIsNone(row(self.ou, DL))
        ou = self.fresh_ou()
        self.assertFalse(ou.has_active_dota_mmr)
        self.assertIsNone(ou.dota_mmr_last_verified)
        self.assertEqual(self.set_mmr_logs(), [])

    def test_apply_supersedes_pending_same_target_only(self) -> None:
        league = League.objects.create(name="Writer League", organization=self.org)
        lu = LeagueUser.objects.create(
            user=self.member, org_user=self.ou, league=league
        )
        dota_req = self.make_request(org_user=self.ou)
        dl_req = self.make_request(org_user=self.ou, game_type=DL)
        league_req = self.make_request(org_user=self.ou, league_user=lu)

        result = apply_official_org_mmr(
            self.ou, DOTA, 4200, actor=self.staff, source="org_user_patch"
        )

        self.assertEqual(result.superseded_ids, [dota_req.pk])
        superseded = fresh(dota_req)
        self.assertEqual(superseded.status, SUPERSEDED)
        self.assertEqual(superseded.approved_mmr, 4200)
        self.assertEqual(superseded.reviewed_by, self.staff)
        self.assertIsNotNone(superseded.reviewed_at)
        self.assertEqual(fresh(dl_req).status, PENDING)
        self.assertEqual(fresh(league_req).status, PENDING)
        gate = MmrChangeRequest.objects.filter(pk=dota_req.pk, status=PENDING).update(
            status=MmrChangeRequest.Status.APPROVED
        )
        self.assertEqual(gate, 0)

    def test_apply_excludes_passed_request_from_supersede(self) -> None:
        req = self.make_request(org_user=self.ou)

        result = apply_official_org_mmr(
            self.ou, DOTA, 4000, actor=self.staff, source="mmr_request", request=req
        )

        self.assertEqual(result.superseded_ids, [])
        self.assertEqual(fresh(req).status, PENDING)

    def test_apply_refreshes_unmet_requirements(self) -> None:
        with patch("org.mmr_official.refresh_unmet_requirements") as refresh:
            apply_official_org_mmr(
                self.ou, DOTA, 4100, actor=self.staff, source="org_user_patch"
            )

        refresh.assert_called_once()
        self.assertEqual(refresh.call_args.args[0].pk, self.ou.pk)

    def test_apply_invalidates_league_users_after_commit(self) -> None:
        league = League.objects.create(name="Inv League", organization=self.org)
        lu = LeagueUser.objects.create(
            user=self.member, org_user=self.ou, league=league
        )

        with patch("org.mmr_official.invalidate_after_commit") as inv:
            apply_official_org_mmr(
                self.ou, DOTA, 4100, actor=self.staff, source="org_user_patch"
            )

        objs: list[Any] = [obj for call in inv.call_args_list for obj in call.args]
        self.assertIn(lu, objs)
        self.assertIn(league, objs)
        self.assertIn(self.org, objs)
        self.assertTrue(
            any(isinstance(o, OrgUser) and o.pk == self.ou.pk for o in objs)
        )


class PatchThroughWriterTests(WriterBase):
    def setUp(self) -> None:
        super().setUp()
        set_org_mmr(self.ou, DOTA, 4000, mark_verified=False)
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def patch(self, body: dict[str, Any]) -> Any:
        return self.client.patch(
            f"/api/organizations/{self.org.pk}/users/{self.ou.pk}/",
            body,
            format="json",
        )

    def test_patch_sets_verified_by(self) -> None:
        response = self.patch({"game_mmrs": {"1": 4400}})

        self.assertEqual(response.status_code, 200, response.content)
        r = row(self.ou, DOTA)
        assert r is not None
        self.assertEqual(r.mmr, 4400)
        self.assertEqual(r.verified_by, self.staff)

    def test_patch_unchanged_value_supersedes_pending_and_stamps(self) -> None:
        pending = self.make_request(org_user=self.ou, requested_mmr=5000)

        response = self.patch({"game_mmrs": {"1": 4000}})

        self.assertEqual(response.status_code, 200, response.content)
        r = row(self.ou, DOTA)
        assert r is not None
        self.assertEqual(r.mmr, 4000)
        self.assertEqual(r.verified_by, self.staff)
        superseded = fresh(pending)
        self.assertEqual(superseded.status, SUPERSEDED)
        self.assertEqual(superseded.approved_mmr, 4000)
        self.assertEqual(self.set_mmr_logs(), [])

    def test_patch_own_row_writes_unverified(self) -> None:
        staff_ou = OrgUser.objects.create(user=self.staff, organization=self.org)

        response = self.client.patch(
            f"/api/organizations/{self.org.pk}/users/{staff_ou.pk}/",
            {"game_mmrs": {"2": 3000}},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        r = row(staff_ou, DL)
        assert r is not None
        self.assertEqual(r.mmr, 3000)
        self.assertIsNone(r.verified_at)
        [entry] = self.set_mmr_logs()
        self.assertFalse(entry.details["verified"])

    def test_patch_staff_colleague_by_plain_staff_writes_unverified(self) -> None:
        colleague = CustomUser.objects.create(username="ow_colleague")
        self.org.staff.add(colleague)
        colleague_ou = OrgUser.objects.create(user=colleague, organization=self.org)
        pending = self.make_request(org_user=colleague_ou, requested_mmr=6000)

        response = self.client.patch(
            f"/api/organizations/{self.org.pk}/users/{colleague_ou.pk}/",
            {"game_mmrs": {"1": 7000}},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        r = row(colleague_ou, DOTA)
        assert r is not None
        self.assertEqual(r.mmr, 7000)
        self.assertIsNone(r.verified_at)
        self.assertIsNone(r.verified_by)
        self.assertEqual(fresh(pending).status, PENDING)
        [entry] = self.set_mmr_logs()
        self.assertFalse(entry.details["verified"])

    def test_patch_staff_colleague_by_owner_verifies(self) -> None:
        colleague = CustomUser.objects.create(username="ow_colleague2")
        self.org.staff.add(colleague)
        colleague_ou = OrgUser.objects.create(user=colleague, organization=self.org)
        pending = self.make_request(org_user=colleague_ou, requested_mmr=6000)
        self.client.force_authenticate(self.owner)

        response = self.client.patch(
            f"/api/organizations/{self.org.pk}/users/{colleague_ou.pk}/",
            {"game_mmrs": {"1": 7000}},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        r = row(colleague_ou, DOTA)
        assert r is not None
        self.assertEqual(r.verified_by, self.owner)
        self.assertEqual(fresh(pending).status, SUPERSEDED)

    def test_patch_logs_once(self) -> None:
        response = self.patch({"game_mmrs": {"1": 4100, "2": 2000}})

        self.assertEqual(response.status_code, 200, response.content)
        logs = self.set_mmr_logs()
        self.assertEqual(sorted(e.details["game_type"] for e in logs), [DOTA, DL])


class EventApproveThroughWriterTests(WriterBase):
    def setUp(self) -> None:
        super().setUp()
        self.event = Event.objects.create(
            organization=self.org,
            name="Writer Event",
            scheduled_at="2030-01-01T00:00:00Z",
            timezone="UTC",
            created_by=self.owner,
            game_type=DOTA,
        )

    def approve(self, actor: CustomUser, subject: CustomUser, mmr: int) -> Any:
        signup = EventSignup.objects.create(
            event=self.event, user=subject, status=SignupStatus.RSVP
        )
        client = APIClient()
        client.force_authenticate(actor)
        return client.post(
            f"/api/events/signups/{signup.pk}/approve/", {"mmr": mmr}, format="json"
        )

    def test_event_approve_with_override_passes_actor_and_verifies(self) -> None:
        response = self.approve(self.owner, self.member, 4300)

        self.assertEqual(response.status_code, 200, response.content)
        r = row(self.ou, DOTA)
        assert r is not None
        self.assertEqual(r.mmr, 4300)
        self.assertEqual(r.verified_by, self.owner)
        [entry] = self.set_mmr_logs()
        self.assertEqual(entry.actor, self.owner)
        self.assertEqual(entry.details["source"], "event_approve")
        self.assertEqual(entry.details["event_id"], self.event.pk)
        self.assertTrue(entry.details["verified"])

    def test_event_approve_self_override_unverified(self) -> None:
        response = self.approve(self.owner, self.owner, 4300)

        self.assertEqual(response.status_code, 200, response.content)
        owner_ou = OrgUser.objects.nocache().get(user=self.owner, organization=self.org)
        r = row(owner_ou, DOTA)
        assert r is not None
        self.assertEqual(r.mmr, 4300)
        self.assertIsNone(r.verified_at)
        self.assertFalse(owner_ou.has_active_dota_mmr)
        [entry] = self.set_mmr_logs()
        self.assertFalse(entry.details["verified"])

    def test_event_approve_supersedes_pending(self) -> None:
        pending = self.make_request(org_user=self.ou, requested_mmr=5000)

        response = self.approve(self.owner, self.member, 4300)

        self.assertEqual(response.status_code, 200, response.content)
        superseded = fresh(pending)
        self.assertEqual(superseded.status, SUPERSEDED)
        self.assertEqual(superseded.approved_mmr, 4300)
        self.assertEqual(superseded.reviewed_by, self.owner)

    def test_event_approve_staff_colleague_by_plain_staff_unverified(self) -> None:
        colleague = CustomUser.objects.create(username="ow_ev_colleague")
        self.org.staff.add(colleague)
        colleague_ou = OrgUser.objects.create(user=colleague, organization=self.org)
        pending = self.make_request(org_user=colleague_ou, requested_mmr=6000)

        response = self.approve(self.staff, colleague, 7000)

        self.assertEqual(response.status_code, 200, response.content)
        r = row(colleague_ou, DOTA)
        assert r is not None
        self.assertEqual(r.mmr, 7000)
        self.assertIsNone(r.verified_at)
        self.assertEqual(fresh(pending).status, PENDING)
        [entry] = self.set_mmr_logs()
        self.assertFalse(entry.details["verified"])


class MayVerifyTests(WriterBase):
    def setUp(self) -> None:
        super().setUp()
        self.admin = CustomUser.objects.create(username="ow_admin")
        self.org.admins.add(self.admin)
        self.staff_ou = OrgUser.objects.create(user=self.staff, organization=self.org)
        self.admin_ou = OrgUser.objects.create(user=self.admin, organization=self.org)
        self.league = League.objects.create(name="Verify League", organization=self.org)
        self.league_staff = CustomUser.objects.create(username="ow_league_staff")
        self.league.staff.add(self.league_staff)
        lstaff_ou = OrgUser.objects.create(
            user=self.league_staff, organization=self.org
        )
        self.member_lu = LeagueUser.objects.create(
            user=self.member, org_user=self.ou, league=self.league
        )
        self.lstaff_lu = LeagueUser.objects.create(
            user=self.league_staff, org_user=lstaff_ou, league=self.league
        )

    def test_org_rules(self) -> None:
        self.assertTrue(may_verify_org_mmr(None, self.staff_ou))
        self.assertTrue(may_verify_org_mmr(self.staff, self.ou))
        self.assertFalse(may_verify_org_mmr(self.staff, self.staff_ou))
        self.assertFalse(may_verify_org_mmr(self.staff, self.admin_ou))
        self.assertTrue(may_verify_org_mmr(self.admin, self.staff_ou))
        self.assertTrue(may_verify_org_mmr(self.owner, self.admin_ou))

    def test_league_rules(self) -> None:
        self.assertTrue(may_verify_league_mmr(self.league_staff, self.member_lu))
        self.assertFalse(may_verify_league_mmr(self.staff, self.lstaff_lu))
        self.assertTrue(may_verify_league_mmr(self.admin, self.lstaff_lu))

    def test_set_league_mmr_by_plain_staff_on_staff_subject_unverified(self) -> None:
        result = set_league_mmr(
            self.lstaff_lu, 3000, actor=self.staff, verified=True, source="test"
        )

        self.assertFalse(result.verified)
        lu = LeagueUser.objects.nocache().get(pk=self.lstaff_lu.pk)
        self.assertEqual(lu.mmr, 3000)
        self.assertIsNone(lu.mmr_verified_at)
