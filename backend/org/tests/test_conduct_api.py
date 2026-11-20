import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, League
from org.models import OrgLog, Organization
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.serializers import EventSignupSerializer
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


class ConductEventApiBase(ConductReadApiBase):
    def setUp(self) -> None:
        super().setUp()
        self.league_staff = CustomUser.objects.create_user(
            username="conapi_league_staff", password="x"
        )
        self.league = League.objects.create(
            name="Conduct API League", organization=self.org, steam_league_id=99871
        )
        self.league.staff.add(self.league_staff)
        self.users["league_staff"] = self.league_staff

    def make_event(self, org: Organization | None = None, **kw: Any) -> Event:
        fields: dict[str, Any] = {
            "organization": org or self.org,
            "name": "Conduct API Event",
            "scheduled_at": timezone.now() - timedelta(hours=1),
            "state": EventState.IN_PROGRESS,
            "created_by": self.users["owner"],
            "auto_approve": True,
            "require_steam_id": False,
            "require_mmr_verified": False,
            "require_profile_complete": False,
        }
        fields.update(kw)
        return Event.objects.create(**fields)

    def signup(self, event: Event, org_user: OrgUser, status: str) -> EventSignup:
        return EventSignup.objects.create(
            event=event, user=org_user.user, status=status
        )


class ConductAttendanceApiTest(ConductEventApiBase):
    def url(self, event: Event, org: Organization | None = None) -> str:
        return f"{base((org or self.org).pk)}events/{event.pk}/attendance/"

    def put(self, event: Event, data: Any, role: str = "staff") -> Response:
        return self.request(role, "put", self.url(event), data)

    def rows_by_user(self, body: dict[str, Any]) -> dict[int, dict[str, Any]]:
        return {row["member"]["user_pk"]: row for row in body["rows"]}

    def test_attendance_role_matrix(self) -> None:
        event = self.make_event(tournament_league=self.league)
        for role in (*ROLES, "league_staff"):
            with self.subTest(role=role):
                response = self.request(role, "get", self.url(event))
                if role in STAFF_TIER or role == "league_staff":
                    self.assertEqual(response.status_code, 200, response.content)
                else:
                    self.assertDenied(response, role)

    def test_attendance_virtual_rows_before_finalize(self) -> None:
        event = self.make_event()
        member = self.org_users["member"]
        self.signup(event, member, SignupStatus.APPROVED)
        self.signup(event, self.org_users["promoter"], SignupStatus.WAITLISTED)
        response = self.request("staff", "get", self.url(event))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["event_id"], event.pk)
        self.assertEqual(body["state"], EventState.IN_PROGRESS)
        self.assertIsNone(body["finalized_at"])
        self.assertIs(body["editable"], True)
        self.assertIsNone(body["editable_reason"])
        self.assertEqual(len(body["rows"]), 1)
        row = body["rows"][0]
        self.assertEqual(row["org_user_pk"], member.pk)
        self.assertEqual(row["signup_status"], SignupStatus.APPROVED)
        self.assertEqual(row["outcome"], Outcome.PENDING)
        self.assertEqual(row["source"], OutcomeSource.DEFAULT)
        self.assertIs(row["virtual"], True)
        self.assertIs(row["committed"], True)
        self.assertIs(row["finalized"], False)
        self.assertIs(row["voided"], False)
        self.assertIsNone(row["flag"])
        self.assertIsNone(row["set_by"])
        self.assertEqual(row["reason"], "")
        self.assertEqual(row["show_rate"], 0.85)
        self.assertEqual(row["status"], "new")
        self.assertEqual(AttendanceOutcome.objects.nocache().count(), 0)

    def test_attendance_flags(self) -> None:
        event = self.make_event(roll_call_enabled=True, state=EventState.ROLL_CALL)
        confirmed = self.make_member("conapi_confirmed")
        unconfirmed = self.make_member("conapi_unconfirmed")
        dropped = self.make_member("conapi_dropped")
        self.signup(event, confirmed, SignupStatus.CONFIRMED)
        self.signup(event, unconfirmed, SignupStatus.APPROVED)
        self.signup(event, dropped, SignupStatus.DROPPED)
        body = self.request("staff", "get", self.url(event)).json()
        rows = self.rows_by_user(body)
        self.assertIsNone(rows[confirmed.user_id]["flag"])
        self.assertEqual(rows[unconfirmed.user_id]["flag"], "roll_call_unconfirmed")
        self.assertEqual(rows[dropped.user_id]["flag"], "dropped_unattributed")
        self.assertEqual(AttendanceOutcome.objects.nocache().count(), 0)

    def test_attendance_existing_rows_after_finalize(self) -> None:
        event = self.make_event(
            state=EventState.COMPLETED, conduct_finalized_at=timezone.now()
        )
        member = self.org_users["member"]
        signup = self.signup(event, member, SignupStatus.APPROVED)
        self.signup(event, self.org_users["promoter"], SignupStatus.APPROVED)
        AttendanceOutcome.objects.create(
            organization=self.org,
            org_user=member,
            event=event,
            event_name=event.name,
            event_starts_at=event.scheduled_at,
            signup=signup,
            outcome=Outcome.NO_SHOW,
            source=OutcomeSource.STAFF,
            set_by=self.users["staff"],
            reason="Never joined",
            finalized_at=timezone.now(),
        )
        body = self.request("staff", "get", self.url(event)).json()
        self.assertIs(body["editable"], True)
        self.assertIsNotNone(body["finalized_at"])
        self.assertEqual(len(body["rows"]), 1)
        row = body["rows"][0]
        self.assertIs(row["virtual"], False)
        self.assertIs(row["finalized"], True)
        self.assertEqual(row["outcome"], Outcome.NO_SHOW)
        self.assertEqual(row["reason"], "Never joined")
        self.assertEqual(
            row["set_by"],
            {
                "user_pk": self.users["staff"].pk,
                "username": self.users["staff"].username,
            },
        )

    def test_put_batch_one_orglog_per_changed_row(self) -> None:
        event = self.make_event()
        member = self.org_users["member"]
        promoter = self.org_users["promoter"]
        self.signup(event, member, SignupStatus.APPROVED)
        self.signup(event, promoter, SignupStatus.APPROVED)
        response = self.put(
            event,
            {
                "changes": [
                    {"org_user_pk": member.pk, "outcome": "no_show"},
                    {"org_user_pk": promoter.pk, "outcome": "attended"},
                ],
                "reason": "Checked voice",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        logs = OrgLog.objects.filter(organization=self.org, action="set_attendance")
        self.assertEqual(logs.count(), 2)
        rows = self.rows_by_user(response.json())
        self.assertEqual(rows[member.user_id]["outcome"], "no_show")
        self.assertEqual(rows[member.user_id]["source"], "staff")
        self.assertIs(rows[member.user_id]["virtual"], False)
        response = self.put(
            event,
            {
                "changes": [
                    {"org_user_pk": member.pk, "outcome": "no_show"},
                    {"org_user_pk": promoter.pk, "outcome": "excused"},
                ],
                "reason": "Second pass",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(logs.count(), 3)

    def test_put_bad_inputs_400(self) -> None:
        event = self.make_event()
        member = self.org_users["member"]
        self.signup(event, member, SignupStatus.APPROVED)
        other = Organization.objects.create(
            name="Other Attendance Org", owner=self.users["outsider"]
        )
        foreign = OrgUser.objects.create(
            user=self.users["outsider"], organization=other
        )
        walkin = self.org_users["promoter"]
        good = {"org_user_pk": member.pk, "outcome": "attended"}
        cases: dict[str, dict[str, Any]] = {
            "duplicate_pk": {"changes": [good, good], "reason": "dup"},
            "duplicate_after_resolution": {
                "changes": [good, {"user_pk": member.user_id, "outcome": "attended"}],
                "reason": "dup",
            },
            "other_org_pk": {
                "changes": [{"org_user_pk": foreign.pk, "outcome": "attended"}],
                "reason": "nope",
            },
            "unknown_pk": {
                "changes": [{"org_user_pk": 987654, "outcome": "attended"}],
                "reason": "nope",
            },
            "empty_changes": {"changes": [], "reason": "empty"},
            "missing_changes": {"reason": "empty"},
            "pending_outcome": {
                "changes": [{"org_user_pk": member.pk, "outcome": "pending"}],
                "reason": "pending",
            },
            "unknown_outcome": {
                "changes": [{"org_user_pk": member.pk, "outcome": "vanished"}],
                "reason": "unknown",
            },
            "short_reason": {"changes": [good], "reason": "ab"},
            "blank_reason": {"changes": [good], "reason": "   ab  "},
            "missing_reason": {"changes": [good]},
            "both_keys": {
                "changes": [
                    {
                        "org_user_pk": member.pk,
                        "user_pk": member.user_id,
                        "outcome": "attended",
                    }
                ],
                "reason": "both",
            },
            "neither_key": {"changes": [{"outcome": "attended"}], "reason": "none"},
            "user_pk_no_show": {
                "changes": [{"user_pk": walkin.user_id, "outcome": "no_show"}],
                "reason": "walk-in no-show",
            },
            "user_pk_not_member": {
                "changes": [{"user_pk": self.users["owner"].pk, "outcome": "attended"}],
                "reason": "not a member",
            },
        }
        for name, body in cases.items():
            with self.subTest(case=name):
                response = self.put(event, body)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(AttendanceOutcome.objects.nocache().count(), 0)
        self.assertFalse(OrgLog.objects.filter(action="set_attendance").exists())

    def test_put_walkin_by_user_pk(self) -> None:
        event = self.make_event()
        walkin = self.org_users["promoter"]
        response = self.put(
            event,
            {
                "changes": [{"user_pk": walkin.user_id, "outcome": "attended"}],
                "reason": "walked in",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        row = AttendanceOutcome.objects.nocache().get(event=event, org_user=walkin)
        self.assertIs(row.committed, False)
        self.assertEqual(row.source, OutcomeSource.STAFF)
        self.assertIsNone(row.signup_id)
        body = self.request("staff", "get", self.url(event)).json()
        rows = self.rows_by_user(body)
        self.assertEqual(rows[walkin.user_id]["outcome"], "attended")
        self.assertIs(rows[walkin.user_id]["committed"], False)
        self.assertIsNone(rows[walkin.user_id]["signup_status"])

    def test_put_expected_signup_without_org_user(self) -> None:
        event = self.make_event()
        legacy = CustomUser.objects.create_user(username="confc_legacy", password="x")
        EventSignup.objects.create(
            event=event, user=legacy, status=SignupStatus.APPROVED
        )
        body = self.request("staff", "get", self.url(event)).json()
        self.assertIsNone(self.rows_by_user(body)[legacy.pk]["org_user_pk"])

        response = self.put(
            event,
            {
                "changes": [{"user_pk": legacy.pk, "outcome": "no_show"}],
                "reason": "never joined",
            },
        )

        self.assertEqual(response.status_code, 200, response.content)
        org_user = OrgUser.objects.get(user=legacy, organization=self.org)
        row = AttendanceOutcome.objects.nocache().get(event=event, org_user=org_user)
        self.assertEqual(row.outcome, Outcome.NO_SHOW)
        legacy_row = self.rows_by_user(response.json())[legacy.pk]
        self.assertEqual(legacy_row["org_user_pk"], org_user.pk)

    def test_put_bad_batch_creates_no_org_user(self) -> None:
        event = self.make_event()
        legacy = CustomUser.objects.create_user(username="confc_legacy2", password="x")
        EventSignup.objects.create(
            event=event, user=legacy, status=SignupStatus.APPROVED
        )

        response = self.put(
            event,
            {
                "changes": [
                    {"user_pk": legacy.pk, "outcome": "no_show"},
                    {"org_user_pk": 987654, "outcome": "attended"},
                ],
                "reason": "bad batch",
            },
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(OrgUser.objects.filter(user=legacy).exists())

    def test_put_cancelled_event_400_and_get_editable_false(self) -> None:
        event = self.make_event(
            state=EventState.CANCELLED, conduct_finalized_at=timezone.now()
        )
        member = self.org_users["member"]
        self.signup(event, member, SignupStatus.APPROVED)
        response = self.put(
            event,
            {
                "changes": [{"org_user_pk": member.pk, "outcome": "attended"}],
                "reason": "was there",
            },
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("reopen", response.json()["detail"].lower())
        self.assertEqual(AttendanceOutcome.objects.nocache().count(), 0)
        body = self.request("staff", "get", self.url(event)).json()
        self.assertIs(body["editable"], False)
        self.assertIn("reopen", body["editable_reason"].lower())
        self.assertEqual(body["rows"], [])

    def test_untracked_completed_event_not_editable(self) -> None:
        event = self.make_event(state=EventState.COMPLETED)
        self.signup(event, self.org_users["member"], SignupStatus.APPROVED)
        body = self.request("staff", "get", self.url(event)).json()
        self.assertIs(body["editable"], False)
        self.assertEqual(
            body["editable_reason"], "Attendance was not tracked for this event."
        )
        self.assertEqual(body["rows"], [])

    def test_event_from_other_org_404(self) -> None:
        other = Organization.objects.create(
            name="Other Event Org", owner=self.users["outsider"]
        )
        self.unlock(other)
        event = self.make_event(org=other)
        response = self.request("staff", "get", self.url(event))
        self.assertEqual(response.status_code, 404, response.content)
        response = self.put(
            event,
            {
                "changes": [
                    {"org_user_pk": self.org_users["member"].pk, "outcome": "attended"}
                ],
                "reason": "cross org",
            },
        )
        self.assertEqual(response.status_code, 404, response.content)

    def test_feature_locked(self) -> None:
        set_org_feature(
            self.org, FeatureKey.CONDUCT, enabled=False, actor=self.site_admin
        )
        event = self.make_event()
        self.assertCode(self.request("owner", "get", self.url(event)), "feature_locked")
        self.assertCode(
            self.put(
                event,
                {
                    "changes": [
                        {
                            "org_user_pk": self.org_users["member"].pk,
                            "outcome": "attended",
                        }
                    ],
                    "reason": "locked",
                },
                role="owner",
            ),
            "feature_locked",
        )


class ConductForecastApiTest(ConductEventApiBase):
    def forecast_url(self, event: Event) -> str:
        return f"{base(self.org.pk)}events/{event.pk}/forecast/"

    def forecast(self, event: Event, role: str = "staff") -> dict[str, Any]:
        response = self.request(role, "get", self.forecast_url(event))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_forecast_manual_approval_event(self) -> None:
        event = self.make_event(
            auto_approve=False, state=EventState.SIGNUPS_OPEN, max_players=None
        )
        members = [self.make_member(f"confc_rsvp_{i}") for i in range(3)]
        for org_user in members:
            self.signup(event, org_user, SignupStatus.RSVP)
        waiting = self.make_member("confc_wait")
        self.signup(event, waiting, SignupStatus.WAITLISTED)
        self.signup(event, self.make_member("confc_gone"), SignupStatus.CANCELLED)

        body = self.forecast(event)
        self.assertEqual(body["seat_holders"], 3)
        self.assertEqual(body["pending_approval"], 0)
        self.assertEqual(body["waitlisted"], 1)
        self.assertEqual(body["new_members"], 3)
        self.assertEqual(body["expected"], round(3 * 0.85, 3))
        self.assertLessEqual(body["low"], body["expected"])
        self.assertGreaterEqual(body["high"], body["expected"])
        self.assertLessEqual(body["high"], 3)
        self.assertIsNone(body["capacity"])
        self.assertIsNone(body["expected_open_seats"])
        expected_keys = {str(m.user_id) for m in (*members, waiting)}
        self.assertEqual(set(body["members"]), expected_keys)
        self.assertEqual(
            body["members"][str(waiting.user_id)],
            {"show_rate": 0.85, "status": "new", "tier": "ok", "deferred": False},
        )
        self.assertEqual(AttendanceOutcome.objects.nocache().count(), 0)

    def test_forecast_pending_approval_counted(self) -> None:
        event = self.make_event(state=EventState.SIGNUPS_OPEN, max_players=4)
        approved = self.make_member("confc_approved")
        pending = self.make_member("confc_pending")
        confirmed = self.make_member("confc_confirmed")
        self.signup(event, approved, SignupStatus.APPROVED)
        self.signup(event, pending, SignupStatus.PENDING_APPROVAL)
        self.signup(event, confirmed, SignupStatus.CONFIRMED)
        self.add_outcomes(confirmed, [Outcome.ATTENDED] * 4)

        body = self.forecast(event)
        self.assertEqual(body["seat_holders"], 3)
        self.assertEqual(body["pending_approval"], 1)
        self.assertEqual(body["waitlisted"], 0)
        self.assertEqual(body["new_members"], 2)
        confirmed_rate = body["members"][str(confirmed.user_id)]["show_rate"]
        self.assertEqual(body["members"][str(confirmed.user_id)]["status"], "scored")
        self.assertGreater(confirmed_rate, 0.85)
        self.assertAlmostEqual(body["expected"], 0.85 * 2 + confirmed_rate, places=2)
        self.assertEqual(body["capacity"], 4)
        self.assertEqual(
            body["expected_open_seats"], round(max(0.0, 4 - body["expected"]), 3)
        )

    def test_forecast_deferred_flag_staff_only(self) -> None:
        OrgConductSettings.objects.nocache().update_or_create(
            organization=self.org, defaults={"back_of_line_enabled": True}
        )
        event = self.make_event(state=EventState.SIGNUPS_OPEN, max_players=1)
        seated = self.make_member("confc_seated")
        flagged = self.make_member("confc_flagged")
        clean = self.make_member("confc_clean")
        self.signup(event, seated, SignupStatus.APPROVED)
        flagged_signup = self.signup(event, flagged, SignupStatus.WAITLISTED)
        self.signup(event, clean, SignupStatus.WAITLISTED)
        self.add_outcomes(flagged, [Outcome.NO_SHOW] * 5)
        self.add_outcomes(seated, [Outcome.NO_SHOW] * 5)

        members = self.forecast(event)["members"]
        self.assertEqual(members[str(flagged.user_id)]["tier"], "back_of_line")
        self.assertIs(members[str(flagged.user_id)]["deferred"], True)
        self.assertIs(members[str(clean.user_id)]["deferred"], False)
        self.assertEqual(members[str(seated.user_id)]["tier"], "back_of_line")
        self.assertIs(members[str(seated.user_id)]["deferred"], False)

        public = EventSignupSerializer(flagged_signup).data
        self.assertFalse(
            [key for key in public if "deferred" in key],
            sorted(public),
        )

    def test_forecast_deferred_ignores_stricter_tier(self) -> None:
        OrgConductSettings.objects.nocache().update_or_create(
            organization=self.org,
            defaults={
                "back_of_line_enabled": True,
                "back_of_line_below": Decimal("0.01"),
                "require_approval_enabled": True,
                "require_approval_below": Decimal("0.99"),
            },
        )
        event = self.make_event(state=EventState.SIGNUPS_OPEN, max_players=1)
        self.signup(event, self.make_member("confc_held_seat"), SignupStatus.APPROVED)
        held = self.make_member("confc_held")
        self.signup(event, held, SignupStatus.WAITLISTED)
        self.add_outcomes(held, [Outcome.NO_SHOW] * 5)

        member = self.forecast(event)["members"][str(held.user_id)]
        self.assertEqual(member["tier"], "require_approval")
        self.assertIs(member["deferred"], False)

    def test_forecast_permissions(self) -> None:
        event = self.make_event(tournament_league=self.league)
        for role in (*ROLES, "league_staff"):
            with self.subTest(role=role):
                response = self.request(role, "get", self.forecast_url(event))
                if role in STAFF_TIER or role == "league_staff":
                    self.assertEqual(response.status_code, 200, response.content)
                else:
                    self.assertDenied(response, role)

        other = Organization.objects.create(
            name="Other Forecast Org", owner=self.users["outsider"]
        )
        self.unlock(other)
        foreign = self.make_event(org=other)
        response = self.request("staff", "get", self.forecast_url(foreign))
        self.assertEqual(response.status_code, 404, response.content)

        set_org_feature(
            self.org, FeatureKey.CONDUCT, enabled=False, actor=self.site_admin
        )
        self.assertCode(
            self.request("owner", "get", self.forecast_url(event)), "feature_locked"
        )
