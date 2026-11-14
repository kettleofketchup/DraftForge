from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization, OrgLog
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.contributions.services import award_entry, create_manual_award
from org.features import FeatureKey, set_org_feature
from org.models import ContributionEntry, ContributionPointValue, OrgUser

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
OCT_15 = datetime(2026, 10, 15, 16, 0, tzinfo=UTC)
NOV_5 = datetime(2026, 11, 5, 16, 0, tzinfo=UTC)


def base(org_id: int) -> str:
    return f"/api/organizations/{org_id}/contributions/"


class ContributionsApiBase(TestCase):
    def setUp(self) -> None:
        self.users: dict[str, CustomUser | None] = {"anon": None}
        for role in ROLES[:-1]:
            self.users[role] = CustomUser.objects.create_user(
                username=f"capi_{role}",
                password="x",
                is_staff=role == "site_admin",
            )
        self.target = CustomUser.objects.create_user(
            username="capi_target", password="x"
        )
        self.org = Organization.objects.create(
            name="Contributions API Org",
            owner=self.users["owner"],
            timezone="America/New_York",
        )
        self.org.admins.add(self.users["admin"])
        self.org.staff.add(self.users["staff"])
        self.org.promoters.add(self.users["promoter"])
        self.org_users: dict[str, OrgUser] = {}
        for role in ("promoter", "member"):
            self.org_users[role] = OrgUser.objects.create(
                user=self.users[role], organization=self.org
            )
        self.target_ou = OrgUser.objects.create(user=self.target, organization=self.org)
        self.site_admin = self.users["site_admin"]
        assert self.site_admin is not None
        self.client = APIClient()

        self.manual = award_entry(
            org=self.org,
            user=self.target,
            kind=ContributionKind.MANUAL,
            occurred_at=OCT_15,
            awarded_by=self.users["owner"],
            reason="secret reason",
            points=7,
        )
        award_entry(
            org=self.org,
            user=self.users["member"],
            kind=ContributionKind.PROMO_MESSAGE,
            occurred_at=NOV_5,
        )
        award_entry(
            org=self.org,
            user=self.users["promoter"],
            kind=ContributionKind.PROMO_MESSAGE,
            occurred_at=NOV_5,
        )

    def unlock(self, org: Organization | None = None) -> None:
        set_org_feature(
            org or self.org,
            FeatureKey.CONTRIBUTIONS,
            enabled=True,
            actor=self.site_admin,
        )

    def set_private(self, private: bool) -> None:
        self.org.members_private = private
        self.org.save()

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
        self.assertCode(response, None if role == "anon" else "not_permitted")


class ContributionsPermissionMatrixTest(ContributionsApiBase):
    def _endpoints(self) -> list[tuple[str, str, Any]]:
        url = base(self.org.pk)
        return [
            ("get", f"{url}leaderboard/", None),
            ("get", f"{url}members/{self.target_ou.pk}/", None),
            ("get", f"{url}point-values/", None),
            (
                "put",
                f"{url}point-values/event_host/",
                {"points": 12, "apply_to_past": False, "since": None},
            ),
            ("get", f"{url}entries/", None),
            (
                "post",
                f"{url}entries/",
                {
                    "user_id": self.target.pk,
                    "points": 3,
                    "reason": "helped",
                    "date": "2026-11-01",
                },
            ),
            ("patch", f"{url}entries/{self.manual.pk}/", {"points": 4}),
            ("delete", f"{url}entries/{self.manual.pk}/", None),
        ]

    def test_locked_is_feature_locked_for_everyone(self) -> None:
        for private in (False, True):
            self.set_private(private)
            for role in ROLES:
                for method, path, data in self._endpoints():
                    with self.subTest(
                        private=private, role=role, method=method, path=path
                    ):
                        self.assertCode(
                            self.request(role, method, path, data), "feature_locked"
                        )

    def test_leaderboard_matrix(self) -> None:
        self.unlock()
        for private in (False, True):
            self.set_private(private)
            for role in ROLES:
                with self.subTest(private=private, role=role):
                    response = self.request(
                        role, "get", f"{base(self.org.pk)}leaderboard/"
                    )
                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    self.assertEqual(body["total"], 7 + 1 + 1)
                    visible = role in STAFF_TIER or (
                        role in MEMBER_ROLES and not private
                    )
                    self.assertEqual(body["rows_visible"], visible)
                    if visible:
                        self.assertEqual(
                            [r["username"] for r in body["rows"]],
                            ["capi_target", "capi_member", "capi_promoter"],
                        )
                    else:
                        self.assertEqual(body["rows"], [])
                    if role in MEMBER_ROLES:
                        self.assertEqual(
                            body["own_row"]["org_user_pk"], self.org_users[role].pk
                        )
                        self.assertEqual(body["own_row"]["points"], 1)
                    else:
                        self.assertIsNone(body["own_row"])

    def test_breakdown_other_member_matrix(self) -> None:
        self.unlock()
        path = f"{base(self.org.pk)}members/{self.target_ou.pk}/"
        for private in (False, True):
            self.set_private(private)
            for role in ROLES:
                with self.subTest(private=private, role=role):
                    response = self.request(role, "get", path)
                    allowed = role in STAFF_TIER or (
                        role in MEMBER_ROLES and not private
                    )
                    if allowed:
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(
                            response.json()["member"]["user_pk"], self.target.pk
                        )
                    else:
                        self.assertDenied(response, role)

    def test_breakdown_own_always_allowed(self) -> None:
        self.unlock()
        for private in (False, True):
            self.set_private(private)
            for role in MEMBER_ROLES:
                with self.subTest(private=private, role=role):
                    response = self.request(
                        role,
                        "get",
                        f"{base(self.org.pk)}members/{self.org_users[role].pk}/",
                    )
                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    self.assertEqual(body["totals"]["all_time"], 1)
                    self.assertEqual(len(body["entries"]), 1)
                    self.assertEqual(body["entries"][0]["kind"], "promo_message")

    def test_admin_endpoints_matrix(self) -> None:
        self.unlock()
        url = base(self.org.pk)
        for private in (False, True):
            self.set_private(private)
            for role in ROLES:
                cases: list[tuple[str, str, Any, int]] = [
                    ("get", f"{url}point-values/", None, 200),
                    (
                        "put",
                        f"{url}point-values/event_host/",
                        {"points": 12, "apply_to_past": False, "since": None},
                        200,
                    ),
                    ("get", f"{url}entries/", None, 200),
                    (
                        "post",
                        f"{url}entries/",
                        {
                            "user_id": self.target.pk,
                            "points": 3,
                            "reason": "helped",
                            "date": "2026-11-01",
                        },
                        201,
                    ),
                ]
                for method, path, data, ok in cases:
                    with self.subTest(private=private, role=role, method=method):
                        response = self.request(role, method, path, data)
                        if role in ADMIN_ROLES:
                            self.assertEqual(response.status_code, ok, response.content)
                        else:
                            self.assertDenied(response, role)

    def test_admin_entry_edit_delete_matrix(self) -> None:
        self.unlock()
        for private in (False, True):
            self.set_private(private)
            for role in ROLES:
                with self.subTest(private=private, role=role):
                    entry = create_manual_award(
                        org=self.org,
                        user=self.target,
                        points=5,
                        reason="matrix",
                        on_date=date(2026, 11, 1),
                        actor=self.users["owner"],
                    )
                    path = f"{base(self.org.pk)}entries/{entry.pk}/"
                    patched = self.request(role, "patch", path, {"points": 9})
                    if role in ADMIN_ROLES:
                        self.assertEqual(patched.status_code, 200, patched.content)
                        self.assertEqual(patched.json()["points"], 9)
                    else:
                        self.assertDenied(patched, role)
                        entry.refresh_from_db()
                        self.assertEqual(entry.points, 5)
                    deleted = self.request(role, "delete", path)
                    exists = ContributionEntry.objects.filter(pk=entry.pk).exists()
                    if role in ADMIN_ROLES:
                        self.assertEqual(deleted.status_code, 204, deleted.content)
                        self.assertFalse(exists)
                    else:
                        self.assertDenied(deleted, role)
                        self.assertTrue(exists)
                        entry.delete()

    def test_league_staff_sees_rows_and_breakdown_on_private_org(self) -> None:
        self.unlock()
        self.set_private(True)
        league = League.objects.create(
            name="Contributions League Staff",
            organization=self.org,
            steam_league_id=99792,
        )
        for field in ("admins", "staff"):
            user = CustomUser.objects.create_user(
                username=f"capi_league_{field}", password="x"
            )
            getattr(league, field).add(user)
            self.client.force_authenticate(user=user)
            with self.subTest(league_role=field):
                board = self.client.get(f"{base(self.org.pk)}leaderboard/")
                self.assertEqual(board.status_code, 200)
                self.assertTrue(board.json()["rows_visible"])
                self.assertEqual(len(board.json()["rows"]), 3)
                breakdown = self.client.get(
                    f"{base(self.org.pk)}members/{self.target_ou.pk}/"
                )
                self.assertEqual(breakdown.status_code, 200, breakdown.content)

    def test_anonymous_on_public_org_sees_total_only(self) -> None:
        self.unlock()
        self.set_private(False)
        response = self.request("anon", "get", f"{base(self.org.pk)}leaderboard/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 9)
        self.assertFalse(body["rows_visible"])
        self.assertEqual(body["rows"], [])
        self.assertIsNone(body["own_row"])
        self.assertEqual(body["period"], "all")

    def test_private_org_member_gets_own_row(self) -> None:
        self.unlock()
        self.set_private(True)
        response = self.request("member", "get", f"{base(self.org.pk)}leaderboard/")
        body = response.json()
        self.assertEqual(body["rows"], [])
        self.assertFalse(body["rows_visible"])
        self.assertEqual(body["own_row"]["user_pk"], self.users["member"].pk)


class ContributionsApiBehaviourTest(ContributionsApiBase):
    def setUp(self) -> None:
        super().setUp()
        self.unlock()
        self.other_owner = CustomUser.objects.create_user(
            username="capi_other_owner", password="x"
        )
        self.other_org = Organization.objects.create(
            name="Contributions Other Org", owner=self.other_owner
        )
        self.unlock(self.other_org)
        self.other_member = CustomUser.objects.create_user(
            username="capi_other_member", password="x"
        )
        self.other_ou = OrgUser.objects.create(
            user=self.other_member, organization=self.other_org
        )
        self.other_entry = award_entry(
            org=self.other_org,
            user=self.other_member,
            kind=ContributionKind.MANUAL,
            occurred_at=OCT_15,
            reason="other",
            points=2,
        )
        league = League.objects.create(
            name="Contributions API League",
            organization=self.org,
            steam_league_id=99791,
        )
        self.event = Event.objects.create(
            organization=self.org,
            name="Contributions API Event",
            scheduled_at=timezone.now() + timedelta(days=1),
            created_by=self.users["owner"],
            tournament_league=league,
        )

    def test_cross_org_entry_is_404(self) -> None:
        url = f"{base(self.org.pk)}entries/{self.other_entry.pk}/"
        self.assertEqual(
            self.request("admin", "patch", url, {"points": 5}).status_code, 404
        )
        self.assertEqual(self.request("admin", "delete", url).status_code, 404)
        self.other_entry.refresh_from_db()
        self.assertEqual(self.other_entry.points, 2)

    def test_cross_org_member_is_404(self) -> None:
        response = self.request(
            "admin", "get", f"{base(self.org.pk)}members/{self.other_ou.pk}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_unknown_org_is_404(self) -> None:
        response = self.request("admin", "get", f"{base(999999)}leaderboard/")
        self.assertEqual(response.status_code, 404)

    def test_manual_reason_hidden_from_member_shown_to_staff(self) -> None:
        self.set_private(False)
        path = f"{base(self.org.pk)}members/{self.target_ou.pk}/"
        member_entry = self.request("member", "get", path).json()["entries"][0]
        self.assertNotIn("reason", member_entry)
        self.assertNotIn("secret reason", str(member_entry))
        staff_entry = self.request("staff", "get", path).json()["entries"][0]
        self.assertEqual(staff_entry["reason"], "secret reason")

    def test_breakdown_shape(self) -> None:
        promo = award_entry(
            org=self.org,
            user=self.target,
            kind=ContributionKind.EVENT_HOST,
            occurred_at=NOV_5,
            event=self.event,
        )
        response = self.request(
            "admin",
            "get",
            f"{base(self.org.pk)}members/{self.target_ou.pk}/?period=2026-11",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["member"]["org_user_pk"], self.target_ou.pk)
        self.assertEqual(body["member"]["username"], "capi_target")
        self.assertEqual(body["totals"]["all_time"], 7 + 10)
        self.assertEqual(len(body["monthly"]), 12)
        self.assertEqual([e["pk"] for e in body["entries"]], [promo.pk])
        entry = body["entries"][0]
        self.assertEqual(
            entry["event"], {"id": self.event.pk, "name": "Contributions API Event"}
        )
        self.assertEqual(entry["event_name"], "Contributions API Event")
        self.assertEqual(entry["points"], 10)
        self.assertIn("occurred_at", entry)
        self.assertNotIn("promo_send", entry)

    def test_bad_period_is_400(self) -> None:
        for path in (
            f"{base(self.org.pk)}leaderboard/?period=garbage",
            f"{base(self.org.pk)}members/{self.target_ou.pk}/?period=2026-13",
            f"{base(self.org.pk)}entries/?period=nope",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.request("admin", "get", path).status_code, 400)

    def test_leaderboard_month_period(self) -> None:
        body = self.request(
            "admin", "get", f"{base(self.org.pk)}leaderboard/?period=2026-10"
        ).json()
        self.assertEqual(body["period"], "2026-10")
        self.assertEqual(body["total"], 7)
        self.assertEqual([r["username"] for r in body["rows"]], ["capi_target"])

    def test_leaderboard_reflects_new_award_with_cache_on(self) -> None:
        path = f"{base(self.org.pk)}leaderboard/"
        self.assertEqual(self.request("member", "get", path).json()["total"], 9)
        create_manual_award(
            org=self.org,
            user=self.target,
            points=5,
            reason="later",
            on_date=date(2026, 11, 2),
            actor=self.users["owner"],
        )
        self.assertEqual(self.request("member", "get", path).json()["total"], 14)

    def test_point_values_get(self) -> None:
        ContributionPointValue.objects.create(
            organization=self.org, kind="event_host", points=20
        )
        body = self.request("admin", "get", f"{base(self.org.pk)}point-values/").json()
        self.assertEqual(
            body,
            [
                {
                    "kind": "promo_message",
                    "points": 1,
                    "default": 1,
                    "is_default": True,
                },
                {
                    "kind": "event_host",
                    "points": 20,
                    "default": 10,
                    "is_default": False,
                },
                {
                    "kind": "event_helper",
                    "points": 5,
                    "default": 5,
                    "is_default": True,
                },
            ],
        )

    def test_point_values_put_apply_to_past(self) -> None:
        response = self.request(
            "owner",
            "put",
            f"{base(self.org.pk)}point-values/promo_message/",
            {"points": 3, "apply_to_past": True, "since": "2026-11-01"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json(),
            {"kind": "promo_message", "old": 1, "new": 3, "changed": 2},
        )
        self.assertTrue(
            OrgLog.objects.filter(organization=self.org, action="rescore").exists()
        )

    def test_point_values_put_reset(self) -> None:
        ContributionPointValue.objects.create(
            organization=self.org, kind="event_host", points=20
        )
        response = self.request(
            "owner",
            "put",
            f"{base(self.org.pk)}point-values/event_host/",
            {"points": None},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["new"], 10)
        self.assertFalse(
            ContributionPointValue.objects.filter(organization=self.org).exists()
        )

    def test_point_values_put_rejects_manual_and_bad_points(self) -> None:
        url = base(self.org.pk)
        for path, data in (
            (f"{url}point-values/manual/", {"points": 3}),
            (f"{url}point-values/bogus/", {"points": 3}),
            (f"{url}point-values/event_host/", {"points": -1}),
            (f"{url}point-values/event_host/", {"points": 5000}),
            (f"{url}point-values/event_host/", {"points": 3, "since": "2026-11-01"}),
        ):
            with self.subTest(path=path, data=data):
                self.assertEqual(
                    self.request("owner", "put", path, data).status_code, 400
                )

    def test_create_manual_award(self) -> None:
        response = self.request(
            "admin",
            "post",
            f"{base(self.org.pk)}entries/",
            {
                "user_id": self.target.pk,
                "points": 4,
                "reason": "  ran the bracket  ",
                "date": "2026-11-01",
                "event_id": self.event.pk,
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        entry = ContributionEntry.objects.get(pk=body["pk"])
        self.assertEqual(entry.kind, "manual")
        self.assertEqual(entry.reason, "ran the bracket")
        self.assertEqual(entry.event_id, self.event.pk)
        self.assertEqual(entry.occurred_at, datetime(2026, 11, 1, 17, 0, tzinfo=UTC))
        self.assertEqual(entry.awarded_by, self.users["admin"])
        self.assertEqual(body["reason"], "ran the bracket")
        self.assertEqual(body["member"]["user_pk"], self.target.pk)

    def test_create_manual_award_validation(self) -> None:
        url = f"{base(self.org.pk)}entries/"
        ok = {
            "user_id": self.target.pk,
            "points": 4,
            "reason": "x",
            "date": "2026-11-01",
        }
        foreign_event = Event.objects.create(
            organization=self.other_org,
            name="Foreign",
            scheduled_at=timezone.now() + timedelta(days=1),
            created_by=self.other_owner,
        )
        for change in (
            {"reason": "   "},
            {"points": 0},
            {"points": 1001},
            {"date": "nope"},
            {"user_id": self.other_member.pk},
            {"user_id": 999999},
            {"event_id": foreign_event.pk},
            {"event_id": 999999},
        ):
            with self.subTest(change=change):
                response = self.request("admin", "post", url, {**ok, **change})
                self.assertEqual(response.status_code, 400, response.content)

    def test_patch_and_delete_manual(self) -> None:
        url = f"{base(self.org.pk)}entries/{self.manual.pk}/"
        response = self.request(
            "admin", "patch", url, {"points": 9, "event_id": self.event.pk}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.manual.refresh_from_db()
        self.assertEqual(self.manual.points, 9)
        self.assertEqual(self.manual.event_id, self.event.pk)
        response = self.request("admin", "patch", url, {"event_id": None})
        self.assertEqual(response.status_code, 200, response.content)
        self.manual.refresh_from_db()
        self.assertIsNone(self.manual.event_id)
        self.assertEqual(self.request("admin", "delete", url).status_code, 204)
        self.assertFalse(ContributionEntry.objects.filter(pk=self.manual.pk).exists())

    def test_patch_and_delete_non_manual_is_400(self) -> None:
        promo = ContributionEntry.objects.get(
            organization=self.org, org_user=self.org_users["member"]
        )
        url = f"{base(self.org.pk)}entries/{promo.pk}/"
        self.assertEqual(
            self.request("admin", "patch", url, {"points": 5}).status_code, 400
        )
        self.assertEqual(self.request("admin", "delete", url).status_code, 400)
        self.assertTrue(ContributionEntry.objects.filter(pk=promo.pk).exists())

    def test_entries_list_filters_and_pagination(self) -> None:
        url = f"{base(self.org.pk)}entries/"
        body = self.request("admin", "get", url).json()
        self.assertEqual(body["count"], 3)
        self.assertEqual(len(body["results"]), 3)
        self.assertNotIn(self.other_entry.pk, [e["pk"] for e in body["results"]])
        self.assertEqual(body["results"][-1]["reason"], "secret reason")

        body = self.request("admin", "get", f"{url}?kind=promo_message").json()
        self.assertEqual(body["count"], 2)
        body = self.request("admin", "get", f"{url}?member={self.target_ou.pk}").json()
        self.assertEqual([e["pk"] for e in body["results"]], [self.manual.pk])
        body = self.request("admin", "get", f"{url}?period=2026-11").json()
        self.assertEqual(body["count"], 2)
        body = self.request("admin", "get", f"{url}?limit=1&offset=1").json()
        self.assertEqual(body["count"], 3)
        self.assertEqual(len(body["results"]), 1)
        self.assertEqual(
            self.request("admin", "get", f"{url}?kind=bogus").status_code, 400
        )

    def test_promotion_points_visible_after_unlock(self) -> None:
        locked_org = Organization.objects.create(
            name="Contributions Locked Org", owner=self.users["owner"]
        )
        award_entry(
            org=locked_org,
            user=self.users["member"],
            kind=ContributionKind.PROMO_MESSAGE,
            occurred_at=NOV_5,
        )
        path = f"{base(locked_org.pk)}leaderboard/"
        self.assertCode(self.request("owner", "get", path), "feature_locked")
        self.unlock(locked_org)
        body = self.request("owner", "get", path).json()
        self.assertEqual(body["total"], 1)
        self.assertEqual([r["username"] for r in body["rows"]], ["capi_member"])
