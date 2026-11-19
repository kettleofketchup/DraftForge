import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, Organization, OrgLog
from org.conduct.constants import Outcome, OutcomeSource
from org.features import FeatureKey, set_org_feature
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome, OrgConductSettings

ROLES = (
    "owner",
    "admin",
    "staff",
    "promoter",
    "member",
    "outsider",
    "site_admin",
    "anon",
)
ADMIN_ROLES = {"owner", "admin", "site_admin"}
STAFF_TIER = {"owner", "admin", "staff", "site_admin"}
MEMBER_ROLES = {"promoter", "member"}


def base(org_id: int) -> str:
    return f"/api/organizations/{org_id}/conduct/"


class ConductApiBase(TestCase):
    def setUp(self) -> None:
        self.users: dict[str, CustomUser | None] = {"anon": None}
        for role in ROLES[:-1]:
            self.users[role] = CustomUser.objects.create_user(
                username=f"conapi_{role}",
                password="x",
                is_staff=role == "site_admin",
            )
        self.org = Organization.objects.create(
            name="Conduct API Org", owner=self.users["owner"]
        )
        self.org.admins.add(self.users["admin"])
        self.org.staff.add(self.users["staff"])
        self.org.promoters.add(self.users["promoter"])
        self.org_users: dict[str, OrgUser] = {}
        for role in ("promoter", "member"):
            self.org_users[role] = OrgUser.objects.create(
                user=self.users[role], organization=self.org
            )
        self.site_admin = self.users["site_admin"]
        self.client = APIClient()

    def unlock(self, org: Organization | None = None) -> None:
        set_org_feature(
            org or self.org,
            FeatureKey.CONDUCT,
            enabled=True,
            actor=self.site_admin,
        )

    def as_role(self, role: str) -> APIClient:
        self.client.force_authenticate(user=self.users[role])
        return self.client

    def request(self, role: str, method: str, path: str, data: Any = None) -> Response:
        client = self.as_role(role)
        return getattr(client, method)(path, data, format="json")

    def assertCode(self, response: Response, code: str | None) -> None:
        self.assertEqual(response.status_code, 403, response.content)
        body = response.json()
        if code is None:
            self.assertNotIn("code", body)
        else:
            self.assertEqual(body.get("code"), code)

    def assertDenied(self, response: Response, role: str) -> None:
        if role == "anon":
            self.assertCode(response, None)
            self.assertEqual(
                response.json()["detail"],
                "Authentication credentials were not provided.",
            )
            return
        self.assertCode(response, "not_permitted")


class ConductSettingsApiTest(ConductApiBase):
    def settings_url(self) -> str:
        return f"{base(self.org.pk)}settings/"

    def patch(self, data: dict[str, Any], role: str = "owner") -> Response:
        return self.request(role, "patch", self.settings_url(), data)

    def test_settings_role_matrix(self) -> None:
        self.unlock()
        for role in ROLES:
            with self.subTest(role=role):
                response = self.request(role, "get", self.settings_url())
                if role in ADMIN_ROLES:
                    self.assertEqual(response.status_code, 200, response.content)
                else:
                    self.assertDenied(response, role)

    def test_settings_feature_locked(self) -> None:
        response = self.request("owner", "get", self.settings_url())
        self.assertCode(response, "feature_locked")
        response = self.patch({"min_events": 5})
        self.assertCode(response, "feature_locked")

    def test_settings_get_does_not_create_row(self) -> None:
        self.unlock()
        response = self.request("owner", "get", self.settings_url())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(OrgConductSettings.objects.nocache().count(), 0)
        body = response.json()
        self.assertEqual(body["half_life_days"], 90)
        self.assertEqual(body["late_cancel_weight"], 0.5)
        self.assertIsInstance(body["late_cancel_weight"], float)
        self.assertIs(body["leaderboard_public"], True)
        self.assertEqual(body["defaults"]["prior_show_rate"], 0.85)
        self.assertEqual(body["defaults"]["min_events"], 3)
        self.assertIs(body["defaults"]["block_enabled"], False)
        self.assertNotIn("organization", body)
        self.assertNotIn("updated_by", body)

    def test_patch_validates_ranges(self) -> None:
        self.unlock()
        response = self.patch({"half_life_days": 5})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("half_life_days", response.json())
        response = self.patch({"block_below": "1.5"})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(OrgConductSettings.objects.nocache().count(), 0)

    def test_patch_partial_cross_field_uses_stored_values(self) -> None:
        self.unlock()
        response = self.patch({"half_life_days": 200})
        self.assertEqual(response.status_code, 200, response.content)
        response = self.patch({"max_age_days": 150})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("max_age_days", response.json())
        response = self.patch({"half_life_days": 400})
        self.assertEqual(response.status_code, 400, response.content)
        row = OrgConductSettings.objects.nocache().get(organization=self.org)
        self.assertEqual(row.half_life_days, 200)
        self.assertEqual(row.max_age_days, 365)

        response = self.patch({"late_cancel_weight": "0.5"})
        self.assertEqual(response.status_code, 200, response.content)
        response = self.patch({"late_cancel_weight": 0.25})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["late_cancel_weight"], 0.25)
        row = OrgConductSettings.objects.nocache().get(organization=self.org)
        self.assertEqual(row.late_cancel_weight, Decimal("0.25"))

    def test_patch_unknown_field_400(self) -> None:
        self.unlock()
        response = self.patch({"min_events": 4, "bogus": 1})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("bogus", response.json())
        response = self.patch({"updated_by": self.users["owner"].pk})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(OrgConductSettings.objects.nocache().count(), 0)

    def test_patch_non_admin_denied(self) -> None:
        self.unlock()
        for role in ("staff", "member", "outsider", "anon"):
            with self.subTest(role=role):
                self.assertDenied(self.patch({"min_events": 4}, role=role), role)
        self.assertEqual(OrgConductSettings.objects.nocache().count(), 0)

    def test_patch_writes_orglog_and_updated_by(self) -> None:
        self.unlock()
        before = OrgLog.objects.filter(organization=self.org).count()
        response = self.patch(
            {"min_events": 5, "block_enabled": True, "leaderboard_public": True}
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["min_events"], 5)
        self.assertIs(body["block_enabled"], True)
        row = OrgConductSettings.objects.nocache().get(organization=self.org)
        self.assertEqual(row.updated_by_id, self.users["owner"].pk)
        self.assertEqual(row.min_events, 5)
        logs = OrgLog.objects.filter(organization=self.org).order_by("-pk")
        self.assertEqual(logs.count(), before + 1)
        entry = logs.first()
        self.assertEqual(entry.action, "update")
        self.assertEqual(entry.actor_id, self.users["owner"].pk)
        self.assertEqual(
            entry.details,
            {
                "area": "conduct_settings",
                "changed_fields": ["min_events", "block_enabled"],
            },
        )

        response = self.patch({"min_events": 5}, role="admin")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            OrgLog.objects.filter(organization=self.org).count(), before + 1
        )

    def test_patch_reflected_in_get_after_cache(self) -> None:
        self.unlock()
        self.request("owner", "get", self.settings_url())
        self.patch({"prior_strength": "4.5"})
        response = self.request("owner", "get", self.settings_url())
        self.assertEqual(response.json()["prior_strength"], 4.5)


class ConductReadApiBase(ConductApiBase):
    def setUp(self) -> None:
        super().setUp()
        self.unlock()
        self.when = timezone.now() - timedelta(days=1)

    def make_member(self, username: str) -> OrgUser:
        user = CustomUser.objects.create_user(username=username, password="x")
        return OrgUser.objects.create(user=user, organization=self.org)

    def add_outcomes(
        self,
        org_user: OrgUser,
        outcomes: list[str],
        *,
        starts_at: datetime | None = None,
        **kw: Any,
    ) -> list[AttendanceOutcome]:
        fields: dict[str, Any] = {"finalized_at": timezone.now(), **kw}
        return [
            AttendanceOutcome.objects.create(
                organization=org_user.organization,
                org_user=org_user,
                event_name=f"Event {index}",
                event_starts_at=starts_at or self.when,
                outcome=outcome,
                **fields,
            )
            for index, outcome in enumerate(outcomes)
        ]

    def set_public(self, public: bool) -> None:
        OrgConductSettings.objects.nocache().update_or_create(
            organization=self.org, defaults={"leaderboard_public": public}
        )

    def set_members_private(self, private: bool) -> None:
        self.org.members_private = private
        self.org.save()


class ConductLeaderboardApiTest(ConductReadApiBase):
    def url(self) -> str:
        return f"{base(self.org.pk)}leaderboard/"

    def get(self, role: str) -> Response:
        return self.request(role, "get", self.url())

    def test_leaderboard_feature_locked(self) -> None:
        set_org_feature(
            self.org, FeatureKey.CONDUCT, enabled=False, actor=self.site_admin
        )
        self.assertCode(self.get("owner"), "feature_locked")

    def test_leaderboard_public_visibility_matrix(self) -> None:
        self.add_outcomes(self.org_users["member"], [Outcome.ATTENDED] * 3)
        for role in ROLES:
            with self.subTest(role=role):
                response = self.get(role)
                self.assertEqual(response.status_code, 200, response.content)
                body = response.json()
                visible = role in STAFF_TIER | MEMBER_ROLES
                self.assertIs(body["rows_visible"], visible)
                self.assertEqual(len(body["rows"]), 1 if visible else 0)
                if role in MEMBER_ROLES:
                    self.assertIsNotNone(body["own_row"])
                else:
                    self.assertIsNone(body["own_row"])

    def test_leaderboard_members_private_hides_rows_keeps_own_row(self) -> None:
        self.set_members_private(True)
        self.add_outcomes(self.org_users["member"], [Outcome.ATTENDED] * 3)
        self.add_outcomes(self.make_member("conapi_new"), [Outcome.ATTENDED])
        body = self.get("member").json()
        self.assertIs(body["rows_visible"], False)
        self.assertEqual(body["rows"], [])
        self.assertEqual(body["new_members"], [])
        own = body["own_row"]
        self.assertEqual(own["member"]["org_user_pk"], self.org_users["member"].pk)
        self.assertEqual(own["rank"], 1)
        self.assertEqual(own["status"], "scored")
        staff = self.get("staff").json()
        self.assertIs(staff["rows_visible"], True)
        self.assertEqual(len(staff["rows"]), 1)
        self.assertEqual(len(staff["new_members"]), 1)

    def test_leaderboard_private_member_gets_own_row_only(self) -> None:
        self.set_public(False)
        self.add_outcomes(self.org_users["member"], [Outcome.ATTENDED] * 3)
        self.add_outcomes(self.make_member("conapi_new"), [Outcome.ATTENDED])
        body = self.get("member").json()
        self.assertIs(body["rows_visible"], False)
        self.assertEqual(body["rows"], [])
        self.assertEqual(body["new_members"], [])
        self.assertEqual(body["own_row"]["counted_events"], 3)
        for role in STAFF_TIER:
            with self.subTest(role=role):
                staff = self.get(role).json()
                self.assertIs(staff["rows_visible"], True)
                self.assertEqual(len(staff["rows"]), 1)

    def test_leaderboard_private_outsider_not_permitted(self) -> None:
        self.set_public(False)
        self.assertDenied(self.get("outsider"), "outsider")
        self.assertDenied(self.get("anon"), "anon")

    def test_leaderboard_no_no_show_counts(self) -> None:
        self.add_outcomes(
            self.org_users["member"],
            [Outcome.ATTENDED, Outcome.NO_SHOW, Outcome.NO_SHOW, Outcome.ATTENDED],
        )
        self.add_outcomes(self.org_users["promoter"], [Outcome.NO_SHOW])
        body = self.get("member").json()
        self.assertEqual(len(body["rows"]), 1)
        self.assertNotIn("no_show", json.dumps(body))

    def test_leaderboard_sort_and_ties(self) -> None:
        charlie = self.make_member("conapi_charlie")
        bravo = self.make_member("conapi_bravo")
        alpha = self.make_member("conapi_alpha")
        delta = self.make_member("conapi_delta")
        echo = self.make_member("conapi_echo")
        self.add_outcomes(charlie, [Outcome.ATTENDED] * 4)
        self.add_outcomes(bravo, [Outcome.ATTENDED] * 3)
        self.add_outcomes(alpha, [Outcome.ATTENDED] * 3)
        self.add_outcomes(delta, [Outcome.NO_SHOW] * 3)
        self.add_outcomes(echo, [Outcome.ATTENDED] * 2)
        body = self.get("staff").json()
        rows = body["rows"]
        self.assertEqual(
            [row["member"]["username"] for row in rows],
            ["conapi_charlie", "conapi_alpha", "conapi_bravo", "conapi_delta"],
        )
        self.assertEqual([row["rank"] for row in rows], [1, 2, 2, 3])
        self.assertEqual([row["counted_events"] for row in rows], [4, 3, 3, 3])
        self.assertEqual(rows[1]["show_rate"], rows[2]["show_rate"])
        self.assertAlmostEqual(rows[1]["show_rate"], 0.925, delta=0.005)
        self.assertAlmostEqual(rows[3]["show_rate"], 0.425, delta=0.005)
        self.assertEqual(
            [m["member"]["username"] for m in body["new_members"]], ["conapi_echo"]
        )
        self.assertEqual(body["new_members"][0]["counted_events"], 2)

    def test_new_members_excludes_zero_event_members(self) -> None:
        newbie = self.make_member("conapi_newbie")
        self.make_member("conapi_idle")
        voided = self.make_member("conapi_voided")
        self.add_outcomes(newbie, [Outcome.ATTENDED])
        self.add_outcomes(voided, [Outcome.ATTENDED], voided_at=timezone.now())
        self.add_outcomes(
            self.org_users["member"],
            [Outcome.ATTENDED],
            source=OutcomeSource.STAFF,
            reason="walk-in",
            committed=False,
        )
        body = self.get("staff").json()
        self.assertEqual(body["rows"], [])
        self.assertEqual(
            [m["member"]["org_user_pk"] for m in body["new_members"]], [newbie.pk]
        )

    def test_leaderboard_own_row_for_zero_event_member(self) -> None:
        for public in (True, False):
            with self.subTest(public=public):
                self.set_public(public)
                own = self.get("member").json()["own_row"]
                self.assertEqual(
                    own["member"]["org_user_pk"], self.org_users["member"].pk
                )
                self.assertEqual(own["status"], "new")
                self.assertEqual(own["counted_events"], 0)
                self.assertIsNone(own["rank"])
                self.assertEqual(own["show_rate"], 0.85)
        self.set_public(True)
        self.assertIsNone(self.get("outsider").json()["own_row"])


class ConductMemberApiTest(ConductReadApiBase):
    def url(self, org_user: OrgUser, query: str = "") -> str:
        return f"{base(self.org.pk)}members/{org_user.pk}/{query}"

    def test_member_feature_locked(self) -> None:
        set_org_feature(
            self.org, FeatureKey.CONDUCT, enabled=False, actor=self.site_admin
        )
        member = self.org_users["member"]
        self.assertCode(
            self.request("member", "get", self.url(member)), "feature_locked"
        )

    def test_member_history_shape_and_totals(self) -> None:
        member = self.org_users["member"]
        older = self.when - timedelta(days=10)
        self.add_outcomes(member, [Outcome.ATTENDED, Outcome.NO_SHOW])
        self.add_outcomes(member, [Outcome.EXCUSED], starts_at=older)
        self.add_outcomes(member, [Outcome.PENDING], starts_at=older, finalized_at=None)
        response = self.request("member", "get", self.url(member))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["member"]["org_user_pk"], member.pk)
        self.assertEqual(body["status"], "new")
        self.assertEqual(body["counted_events"], 2)
        self.assertGreater(body["weighted_events"], 1.9)
        self.assertEqual(
            body["totals"],
            {"attended": 1, "no_show": 1, "late_cancel": 0, "excused": 1},
        )
        self.assertEqual(len(body["history"]), 4)
        first = body["history"][0]
        self.assertEqual(
            set(first),
            {
                "event_id",
                "event_name",
                "event_starts_at",
                "outcome",
                "source",
                "committed",
                "finalized",
                "voided",
                "weight",
            },
        )
        starts = [item["event_starts_at"] for item in body["history"]]
        self.assertEqual(starts, sorted(starts, reverse=True))
        by_outcome = {item["outcome"]: item for item in body["history"]}
        self.assertEqual(by_outcome["excused"]["weight"], 0)
        self.assertEqual(by_outcome["pending"]["weight"], 0)
        self.assertIs(by_outcome["pending"]["finalized"], False)
        self.assertGreater(by_outcome["attended"]["weight"], 0)

    def test_member_history_weight_zero_outside_max_age(self) -> None:
        member = self.org_users["member"]
        now = timezone.now()
        self.add_outcomes(
            member, [Outcome.ATTENDED], starts_at=now - timedelta(days=366)
        )
        self.add_outcomes(
            member, [Outcome.ATTENDED], starts_at=now - timedelta(days=364)
        )
        body = self.request("staff", "get", self.url(member)).json()
        weights = [item["weight"] for item in body["history"]]
        self.assertGreater(weights[0], 0)
        self.assertEqual(weights[1], 0)
        self.assertEqual(body["counted_events"], 1)

    def test_member_self_vs_staff_reason(self) -> None:
        member = self.org_users["member"]
        self.add_outcomes(
            member,
            [Outcome.NO_SHOW],
            source=OutcomeSource.STAFF,
            reason="Never joined voice",
            set_by=self.users["staff"],
        )
        own = self.request("member", "get", self.url(member)).json()
        self.assertNotIn("reason", own["history"][0])
        self.assertNotIn("set_by", own["history"][0])
        for role in STAFF_TIER:
            with self.subTest(role=role):
                item = self.request(role, "get", self.url(member)).json()["history"][0]
                self.assertEqual(item["reason"], "Never joined voice")
                self.assertEqual(
                    item["set_by"],
                    {
                        "user_pk": self.users["staff"].pk,
                        "username": self.users["staff"].username,
                    },
                )

    def test_member_outsider_403_anon_401(self) -> None:
        member = self.org_users["member"]
        for role in ("outsider", "anon", "promoter"):
            with self.subTest(role=role):
                self.assertDenied(self.request(role, "get", self.url(member)), role)
        self.set_public(False)
        response = self.request("member", "get", self.url(member))
        self.assertEqual(response.status_code, 200, response.content)

    def test_member_pagination_bounds(self) -> None:
        member = self.org_users["member"]
        for days in (1, 2, 3):
            self.add_outcomes(
                member,
                [Outcome.ATTENDED],
                starts_at=timezone.now() - timedelta(days=days),
            )
        for query in ("?limit=500", "?limit=0", "?offset=-1", "?limit=x"):
            with self.subTest(query=query):
                response = self.request("staff", "get", self.url(member, query))
                self.assertEqual(response.status_code, 400, response.content)
        full = self.request("staff", "get", self.url(member)).json()["history"]
        page = self.request("staff", "get", self.url(member, "?limit=1&offset=1"))
        self.assertEqual(page.status_code, 200, page.content)
        self.assertEqual(page.json()["history"], full[1:2])
        self.assertEqual(
            self.request("staff", "get", self.url(member, "?limit=200")).status_code,
            200,
        )

    def test_cross_org_member_404(self) -> None:
        other = Organization.objects.create(
            name="Other Conduct Org", owner=self.users["outsider"]
        )
        self.unlock(other)
        foreign = OrgUser.objects.create(user=self.users["member"], organization=other)
        response = self.request("staff", "get", self.url(foreign))
        self.assertEqual(response.status_code, 404, response.content)
        response = self.request("member", "get", self.url(foreign))
        self.assertEqual(response.status_code, 404, response.content)
