import json
from datetime import timedelta
from typing import Any

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from app.models import CustomUser, GameType
from league.models import League, LeagueUser
from org.mmr import set_org_mmr
from org.models import MmrChangeRequest, Organization, OrgUser
from org.tests.mmr_request_mixin import MmrRequestTestMixin

S = MmrChangeRequest.Status


class SummaryFixture(MmrRequestTestMixin):
    def build(self) -> None:
        def user(name: str, **kw: Any) -> CustomUser:
            return CustomUser.objects.create(username=f"mps_{name}", **kw)

        self.subject = user("subject")
        self.owner = user("owner")
        self.org_staff = user("ostaff")
        self.member = user("member")
        self.nonmember = user("nonmember")
        self.league_staff = user("lstaff")
        self.league_mate = user("lmate")
        self.superuser = user("super", is_superuser=True)

        self.org = Organization.objects.create(name="MPS Org", owner=self.owner)
        self.org.staff.add(self.org_staff)
        self.league = League.objects.create(name="MPS League", organization=self.org)
        self.league.staff.add(self.league_staff)

        self.ou = OrgUser.objects.create(user=self.subject, organization=self.org)
        set_org_mmr(self.ou, GameType.DOTA2, 4200, mark_verified=False)
        self.lu = LeagueUser.objects.create(
            user=self.subject, org_user=self.ou, league=self.league, mmr=4300
        )
        OrgUser.objects.create(user=self.member, organization=self.org)
        mate_ou = OrgUser.objects.create(user=self.league_mate, organization=self.org)
        LeagueUser.objects.create(
            user=self.league_mate, org_user=mate_ou, league=self.league, mmr=1
        )

    def url(self, user: CustomUser | None = None) -> str:
        return f"/api/users/{(user or self.subject).pk}/mmrs/"

    def get(self, viewer: CustomUser | None, subject: CustomUser | None = None) -> Any:
        client = APIClient()
        if viewer is not None:
            client.force_authenticate(viewer)
        resp = client.get(self.url(subject))
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def set_private(self, private: bool) -> None:
        self.org.members_private = private
        self.org.save()


class PublicSummaryVisibilityTest(SummaryFixture, APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.build()

    def test_visibility_matrix(self) -> None:
        # viewer -> (org entry when public, org when private, league public, league private)
        cases: dict[str, tuple[CustomUser | None, bool, bool, bool, bool]] = {
            "anon": (None, False, False, False, False),
            "self": (self.subject, True, True, True, True),
            "member": (self.member, True, False, True, False),
            "nonmember": (self.nonmember, False, False, False, False),
            "org_staff": (self.org_staff, True, True, True, True),
            "league_staff": (self.league_staff, True, True, True, True),
            "league_mate": (self.league_mate, True, False, True, True),
            "superuser": (self.superuser, True, True, True, True),
        }
        for private in (False, True):
            self.set_private(private)
            for name, (viewer, org_pub, org_priv, lg_pub, lg_priv) in cases.items():
                with self.subTest(viewer=name, private=private):
                    data = self.get(viewer)
                    want_org = org_priv if private else org_pub
                    want_league = lg_priv if private else lg_pub
                    self.assertEqual(len(data["orgs"]), int(want_org))
                    self.assertEqual(len(data["leagues"]), int(want_league))
                    self.assertEqual(data["user_pk"], self.subject.pk)

    def test_anon_and_nonmember_of_public_org_see_no_org_entries(self) -> None:
        self.set_private(False)
        for viewer in (None, self.nonmember):
            with self.subTest(viewer=getattr(viewer, "username", "anon")):
                data = self.get(viewer)
                self.assertEqual(data["orgs"], [])
                self.assertEqual(data["leagues"], [])

    def test_self_only_fields_hidden_from_others(self) -> None:
        pending = self.make_request(org_user=self.ou, game_type=GameType.DOTA2)
        self.make_request(org_user=self.ou, league_user=self.lu, requested_mmr=4500)
        data = self.get(self.member)
        org = data["orgs"][0]
        self.assertIsNone(org["org_user_pk"])
        for game in org["game_mmrs"]:
            self.assertIsNone(game["pending_request"])
            self.assertIsNone(game["last_decision"])
        league = data["leagues"][0]
        self.assertIsNone(league["league_user_pk"])
        self.assertIsNone(league["pending_request"])
        self.assertIsNone(league["last_decision"])

        for viewer in (self.subject, self.org_staff):
            with self.subTest(viewer=viewer.username):
                data = self.get(viewer)
                org = data["orgs"][0]
                self.assertEqual(org["org_user_pk"], self.ou.pk)
                dota = next(
                    g for g in org["game_mmrs"] if g["game_type"] == GameType.DOTA2
                )
                self.assertEqual(dota["pending_request"]["id"], pending.pk)
                league = data["leagues"][0]
                self.assertEqual(league["league_user_pk"], self.lu.pk)
                self.assertEqual(league["pending_request"]["requested_mmr"], 4500)

    def test_league_staff_sees_league_fields_not_org_fields(self) -> None:
        self.make_request(org_user=self.ou, game_type=GameType.DOTA2)
        data = self.get(self.league_staff)
        self.assertIsNone(data["orgs"][0]["org_user_pk"])
        self.assertEqual(data["leagues"][0]["league_user_pk"], self.lu.pk)

    def test_fellow_league_member_of_private_org_sees_league_without_org(self) -> None:
        self.set_private(True)
        client = APIClient()
        client.force_authenticate(self.league_mate)
        resp = client.get(self.url())
        data = resp.json()
        self.assertEqual(data["orgs"], [])
        self.assertEqual(len(data["leagues"]), 1)
        self.assertIsNone(data["leagues"][0]["organization_pk"])
        self.assertNotIn(self.org.name, resp.content.decode())

    def test_organization_pk_present_when_org_visible(self) -> None:
        data = self.get(self.member)
        self.assertEqual(data["leagues"][0]["organization_pk"], self.org.pk)

    def test_orgless_league_visible_to_league_staff_and_members(self) -> None:
        orgless = League.objects.create(name="MPS Orgless")
        orgless.staff.add(self.nonmember)
        orgless_lu = LeagueUser.objects.create(
            user=self.subject, org_user=self.ou, league=orgless, mmr=10
        )
        self.set_private(True)
        data = self.get(self.nonmember)
        self.assertEqual([lg["league"]["pk"] for lg in data["leagues"]], [orgless.pk])
        self.assertIsNone(data["leagues"][0]["organization_pk"])
        self.assertEqual(data["leagues"][0]["league_user_pk"], orgless_lu.pk)

    def test_unknown_user_404(self) -> None:
        resp = APIClient().get("/api/users/999999/mmrs/")
        self.assertEqual(resp.status_code, 404)


class PublicSummaryContentTest(SummaryFixture, APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.build()

    def test_unset_games_listed_with_zero(self) -> None:
        data = self.get(self.subject)
        games = {g["game_type"]: g for g in data["orgs"][0]["game_mmrs"]}
        self.assertEqual(set(games), {int(g) for g in GameType})
        self.assertEqual(games[GameType.DOTA2]["mmr"], 4200)
        deadlock = games[GameType.DEADLOCK]
        self.assertEqual(deadlock["mmr"], 0)
        self.assertFalse(deadlock["verified"])
        self.assertIsNone(deadlock["verified_at"])
        self.assertIsNone(deadlock["verified_by"])

    def test_verified_and_legacy_flags(self) -> None:
        set_org_mmr(
            self.ou,
            GameType.DOTA2,
            4400,
            mark_verified=True,
            verified_by=self.org_staff,
        )
        dota = self.get(self.subject)["orgs"][0]["game_mmrs"][0]
        self.assertTrue(dota["verified"])
        self.assertFalse(dota["legacy_verified"])
        self.assertEqual(
            dota["verified_by"],
            {"pk": self.org_staff.pk, "username": self.org_staff.username},
        )
        self.ou.game_mmrs.update(verified_by=None)
        dota = self.get(self.subject)["orgs"][0]["game_mmrs"][0]
        self.assertTrue(dota["verified"])
        self.assertTrue(dota["legacy_verified"])

    def test_league_verified_fields(self) -> None:
        now = timezone.now()
        LeagueUser.objects.filter(pk=self.lu.pk).update(
            mmr_verified_at=now, mmr_verified_by=self.league_staff
        )
        league = self.get(self.subject)["leagues"][0]
        self.assertTrue(league["verified"])
        self.assertEqual(league["mmr"], 4300)
        self.assertEqual(league["verified_by"]["pk"], self.league_staff.pk)

    def test_last_decision_superseded_with_decided_mmr_ignores_cancelled(self) -> None:
        now = timezone.now()
        self.make_request(
            org_user=self.ou,
            game_type=GameType.DOTA2,
            status=S.REJECTED,
            rejection_reason="Blurry",
            reviewed_at=now - timedelta(days=2),
        )
        superseded = self.make_request(
            org_user=self.ou,
            game_type=GameType.DOTA2,
            status=S.SUPERSEDED,
            approved_mmr=4800,
            reviewed_by=self.org_staff,
            reviewed_at=now - timedelta(days=1),
        )
        self.make_request(
            org_user=self.ou,
            game_type=GameType.DOTA2,
            status=S.CANCELLED,
            with_screenshot=False,
        )
        rejected_league = self.make_request(
            org_user=self.ou,
            league_user=self.lu,
            status=S.REJECTED,
            rejection_reason="No proof",
            reviewed_at=now,
        )
        data = self.get(self.subject)
        dota = next(
            g for g in data["orgs"][0]["game_mmrs"] if g["game_type"] == GameType.DOTA2
        )
        self.assertEqual(dota["last_decision"]["id"], superseded.pk)
        self.assertEqual(dota["last_decision"]["status"], "superseded")
        self.assertEqual(dota["last_decision"]["decided_mmr"], 4800)
        deadlock = next(
            g
            for g in data["orgs"][0]["game_mmrs"]
            if g["game_type"] == GameType.DEADLOCK
        )
        self.assertIsNone(deadlock["last_decision"])
        league = data["leagues"][0]["last_decision"]
        self.assertEqual(league["id"], rejected_league.pk)
        self.assertEqual(league["status"], "rejected")
        self.assertIsNone(league["decided_mmr"])
        self.assertEqual(league["rejection_reason"], "No proof")

    def test_approve_visible_immediately(self) -> None:
        self.get(self.subject)
        req = self.make_request(org_user=self.ou, game_type=GameType.DOTA2)
        client = APIClient()
        client.force_authenticate(self.org_staff)
        resp = client.post(
            f"/api/mmr-requests/{req.pk}/approve/", {"mmr": 5100}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        dota = self.get(self.subject)["orgs"][0]["game_mmrs"][0]
        self.assertEqual(dota["mmr"], 5100)
        self.assertTrue(dota["verified"])
        self.assertIsNone(dota["pending_request"])
        self.assertEqual(dota["last_decision"]["status"], "approved")
        self.assertEqual(dota["last_decision"]["decided_mmr"], 5100)

    def test_no_screenshot_path_in_payload(self) -> None:
        req = self.make_request(org_user=self.ou, game_type=GameType.DOTA2)
        client = APIClient()
        client.force_authenticate(self.subject)
        resp = client.get(self.url())
        body = resp.content.decode()
        self.assertNotIn("screenshot", body)
        self.assertNotIn(req.screenshot.name, body)
        self.assertNotIn("mmr_requests/", body)
        self.assertEqual(resp["Cache-Control"], "private, no-store")
        json.loads(body)


class PublicSummaryQueryCountTest(SummaryFixture, APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.build()

    def add_memberships(self, orgs: int, leagues: int) -> None:
        for i in range(orgs):
            org = Organization.objects.create(name=f"MPS Extra {i}")
            org.staff.add(self.org_staff)
            ou = OrgUser.objects.create(user=self.subject, organization=org)
            set_org_mmr(ou, GameType.DOTA2, 3000 + i, mark_verified=False)
            self.make_request(org_user=ou, game_type=GameType.DOTA2)
            for j in range(leagues):
                league = League.objects.create(name=f"MPS L {i}-{j}", organization=org)
                lu = LeagueUser.objects.create(
                    user=self.subject, org_user=ou, league=league, mmr=10
                )
                self.make_request(
                    org_user=ou,
                    league_user=lu,
                    status=S.REJECTED,
                    rejection_reason="x",
                    reviewed_at=timezone.now(),
                )

    def count(self, viewer: CustomUser) -> int:
        client = APIClient()
        client.force_authenticate(viewer)
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(self.url())
        self.assertEqual(resp.status_code, 200)
        return len(ctx.captured_queries)

    def test_query_count_scale_invariant(self) -> None:
        self.make_request(org_user=self.ou, game_type=GameType.DOTA2)
        viewers = (self.subject, self.org_staff, self.member, self.league_mate)
        small = {v.username: self.count(v) for v in viewers}
        self.add_memberships(orgs=2, leagues=2)
        self.assertEqual(LeagueUser.objects.filter(user=self.subject).count(), 5)
        self.assertEqual(OrgUser.objects.filter(user=self.subject).count(), 3)
        large = {v.username: self.count(v) for v in viewers}
        self.assertEqual(small, large)
