import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from unittest import mock
from uuid import uuid4

from cacheops import invalidate_obj
from django.core.cache.backends.locmem import LocMemCache
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext, override_settings
from django.utils import timezone as tz
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from events.models import Event
from org.contributions.services import award_entry
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.leadership.lifecycle import void_event
from org.leadership.reviews import void_review
from org.leadership.traits import upsert_traits
from org.leadership.views import CaptainReviewThrottle
from org.models import Organization, OrgUser
from org.models_leadership import CaptainReview, EventCaptain, OrgLeadershipSettings
from org.tests.leadership_base import LeadershipTestCase, scores

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
ADMIN_ROLES = frozenset({"owner", "admin", "site_admin"})
MEMBER_ROLES = frozenset({"promoter", "member"})


def _dump(response: Response) -> str:
    return json.dumps(response.json(), default=str)


@dataclass(frozen=True)
class OtherOrg:
    org: Organization
    event: Event
    captain: OrgUser
    review: CaptainReview
    member: OrgUser


class ApiCase(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(
            CaptainReviewThrottle,
            "cache",
            LocMemCache(f"captain-review-{uuid4().hex}", {}),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def review_url(self, captain: CustomUser, event: Event | None = None) -> str:
        return self.url(
            f"events/{(event or self.event).pk}/captains/{self.ou(captain).pk}/review/"
        )

    def other_org(self, rater: CustomUser) -> OtherOrg:
        home = self.org
        other = Organization.objects.create(
            name="Other Org", owner=self.make_user("ob_owner")
        )
        set_org_feature(other, FeatureKey.LEADERSHIP, enabled=True, actor=None)
        self.org = other
        try:
            event, tournament = self.make_event("Other Cup")
            captain = self.make_user("ob_cap")
            mates = [rater, self.make_user("ob_m1")]
            self.make_team("Oscar", captain, mates, placement=1, tournament=tournament)
            for user in [captain, *mates]:
                self.admit(user, event)
            self.close(event)
            review = self.review(rater, captain, 4, event=event)
            upsert_traits(
                other,
                actor=self.admin,
                items=[{"key": "macro", "label": "Macro", "order": 9, "active": False}],
            )
            return OtherOrg(
                org=other,
                event=event,
                captain=self.ou(captain),
                review=review,
                member=self.ou(mates[1]),
            )
        finally:
            self.org = home


class PermissionMatrixTest(ApiCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        self.first = self.review(self.mates_a[0], self.cap_a, 4)
        self.users: dict[str, CustomUser | None] = {"anon": None}
        for role in ROLES[:-1]:
            self.users[role] = CustomUser.objects.create_user(
                username=f"ldapi_{role}",
                password="x",
                is_staff=role == "site_admin",
            )
        self.org.owner = self.users["owner"]
        self.org.save()
        self.org.admins.add(self.users["admin"])
        self.org.staff.add(self.users["staff"])
        self.org.promoters.add(self.users["promoter"])
        invalidate_obj(self.org)
        for role in MEMBER_ROLES:
            OrgUser.objects.create(user=self.users[role], organization=self.org)
        self.member_ou = self.ou(self.users["member"])  # type: ignore[arg-type]

    def call(self, role: str, method: str, suffix: str, data: Any = None) -> Response:
        client = self.client_for(self.users[role]) if self.users[role] else None
        if client is None:
            client = APIClient()
        return getattr(client, method)(self.url(suffix), data, format="json")

    def assert_denied(self, response: Response, role: str) -> None:
        self.assertEqual(response.status_code, 403, response.content)
        if role == "anon":
            self.assertEqual(
                response.json()["detail"],
                "Authentication credentials were not provided.",
            )
        else:
            self.assertEqual(response.json().get("code"), "not_permitted")

    def run_matrix(
        self,
        method: str,
        suffix: str,
        expected: dict[str, tuple[int, str | None]],
        *,
        data: Any = None,
        before: Any = None,
    ) -> None:
        for role in ROLES:
            with self.subTest(method=method, suffix=suffix, role=role):
                if before is not None:
                    before()
                response = self.call(role, method, suffix, data)
                if role not in expected:
                    self.assert_denied(response, role)
                    continue
                status, code = expected[role]
                self.assertEqual(response.status_code, status, response.content)
                if code is not None:
                    self.assertEqual(response.json()["code"], code)

    def test_matrix(self) -> None:
        admins = {role: (200, None) for role in ADMIN_ROLES}
        members = {role: (200, None) for role in MEMBER_ROLES}
        self.run_matrix("get", "settings/", admins)
        self.run_matrix("patch", "settings/", admins, data={"review_window_hours": 48})
        self.run_matrix("get", "traits/", {**admins, **members})
        self.run_matrix(
            "put",
            "traits/",
            admins,
            data={"traits": [{"key": "macro", "label": "Macro", "active": False}]},
        )

        def add_temp() -> None:
            upsert_traits(
                self.org,
                actor=self.admin,
                items=[{"key": "temp", "label": "Temp", "order": 9, "active": False}],
            )

        self.run_matrix(
            "delete",
            "traits/temp/",
            {role: (204, None) for role in ADMIN_ROLES},
            before=add_temp,
        )
        self.run_matrix("get", "reviews/pending/", members)
        self.run_matrix("get", "reviews/mine/", members)
        self.run_matrix(
            "put",
            f"events/{self.event.pk}/captains/{self.ou(self.cap_a).pk}/review/",
            {role: (403, "not_in_pool") for role in MEMBER_ROLES},
            data={"scores": scores(4)},
        )
        self.run_matrix("get", f"events/{self.event.pk}/reviews/", admins)
        self.run_matrix(
            "post",
            f"reviews/{self.first.pk}/void/",
            {role: (400, None) for role in ADMIN_ROLES},
            data={},
        )
        self.run_matrix(
            "post",
            f"reviews/{self.first.pk}/unvoid/",
            {role: (409, "not_moderated") for role in ADMIN_ROLES},
        )
        self.run_matrix(
            "get",
            f"members/{self.member_ou.pk}/",
            {**admins, "member": (200, None)},
        )

    def test_locked_feature_403(self) -> None:
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        cap = self.ou(self.cap_a).pk
        calls = [
            ("get", "settings/", None),
            ("patch", "settings/", {"review_window_hours": 48}),
            ("get", "traits/", None),
            ("put", "traits/", {"traits": []}),
            ("delete", "traits/drafting/", None),
            ("get", "reviews/pending/", None),
            ("get", "reviews/mine/", None),
            (
                "put",
                f"events/{self.event.pk}/captains/{cap}/review/",
                {"scores": scores(4)},
            ),
            ("delete", f"events/{self.event.pk}/captains/{cap}/review/", None),
            ("get", f"events/{self.event.pk}/reviews/", None),
            ("post", f"reviews/{self.first.pk}/void/", {"reason": "x"}),
            ("post", f"reviews/{self.first.pk}/unvoid/", None),
            ("get", f"members/{cap}/", None),
        ]
        for role in ("owner", "member", "anon"):
            for method, suffix, data in calls:
                with self.subTest(role=role, method=method, suffix=suffix):
                    response = self.call(role, method, suffix, data)
                    self.assertEqual(response.status_code, 403, response.content)
                    self.assertEqual(response.json()["code"], "feature_locked")


class CrossOrgTest(ApiCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        self.other = self.other_org(self.mates_a[0])

    def test_foreign_ids_are_404(self) -> None:
        admin = self.client_for(self.admin)
        rater = self.client_for(self.mates_a[0])
        o = self.other
        checks = [
            (
                rater.put,
                f"events/{o.event.pk}/captains/{o.captain.pk}/review/",
                {"scores": scores(4)},
            ),
            (
                rater.put,
                f"events/{self.event.pk}/captains/{o.captain.pk}/review/",
                {"scores": scores(4)},
            ),
            (
                rater.delete,
                f"events/{o.event.pk}/captains/{o.captain.pk}/review/",
                None,
            ),
            (admin.get, f"events/{o.event.pk}/reviews/", None),
            (admin.post, f"reviews/{o.review.pk}/void/", {"reason": "x"}),
            (admin.post, f"reviews/{o.review.pk}/unvoid/", None),
            (admin.delete, "traits/macro/", None),
            (admin.get, f"members/{o.member.pk}/", None),
            (admin.get, f"members/{o.captain.pk}/", None),
        ]
        for method, suffix, data in checks:
            with self.subTest(suffix=suffix):
                response = method(self.url(suffix), data, format="json")
                self.assertEqual(response.status_code, 404, response.content)

    def test_pending_filter_ignores_foreign_event(self) -> None:
        res = self.client_for(self.mates_a[0]).get(
            self.url(f"reviews/pending/?event_id={self.other.event.pk}")
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])


class ReviewApiTest(ApiCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()

    def test_pending_shape_and_filter(self) -> None:
        client = self.client_for(self.mates_a[0])
        body = client.get(self.url("reviews/pending/")).json()
        self.assertEqual(len(body), 1)
        item = body[0]
        self.assertEqual(item["captain_org_user_id"], self.ou(self.cap_a).pk)
        self.assertEqual(item["event_id"], self.event.pk)
        self.assertEqual(item["team_name"], "Alpha")
        self.assertEqual(len(item["traits"]), 4)
        self.assertIsNone(item["scores"])
        self.review(self.mates_a[0], self.cap_a, 3)
        item = client.get(
            self.url(f"reviews/pending/?event_id={self.event.pk}")
        ).json()[0]
        self.assertEqual(item["scores"]["drafting"], 3)
        self.assertEqual(
            client.get(
                self.url(f"reviews/pending/?event_id={self.event.pk + 999}")
            ).json(),
            [],
        )
        self.assertEqual(
            client.get(self.url("reviews/pending/?event_id=abc")).status_code, 400
        )

    def test_put_and_delete_review(self) -> None:
        client = self.client_for(self.mates_a[0])
        res = client.put(
            self.review_url(self.cap_a), {"scores": scores(4)}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["scores"]["drafting"], 4)
        self.assertIn("updated_at", res.json())
        self.assertIn("submitted_at", res.json())
        res = client.delete(self.review_url(self.cap_a))
        self.assertEqual(res.status_code, 204)
        self.assertEqual(CaptainReview.objects.get().void_kind, "withdrawn")

    def test_put_review_status_codes(self) -> None:
        client = self.client_for(self.mates_a[0])
        url = self.review_url(self.cap_a)
        res = client.put(url, {"scores": scores(4)}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        missing = {k: v for k, v in scores(4).items() if k != "drafting"}
        res = client.put(url, {"scores": missing}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], "invalid_scores")
        res = self.client_for(self.mates_b[0]).put(
            url, {"scores": scores(4)}, format="json"
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], "not_in_pool")
        review = CaptainReview.objects.get()
        void_review(
            self.org,
            review_id=review.pk,
            actor=self.admin,
            reason="abuse",
            now=tz.now(),
        )
        res = client.put(url, {"scores": scores(5)}, format="json")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], "review_moderated")
        mate = self.client_for(self.mates_a[1])
        self.expire_window()
        res = mate.put(url, {"scores": scores(4)}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], "review_window_closed")
        EventCaptain.objects.update(window_closes_at=tz.now() + timedelta(hours=1))
        with transaction.atomic():
            void_event(self.event, now=tz.now())
        res = mate.put(url, {"scores": scores(4)}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], "snapshot_voided")

    def test_review_put_throttled(self) -> None:
        client = self.client_for(self.mates_a[0])
        url = self.review_url(self.cap_a)
        with mock.patch.object(CaptainReviewThrottle, "rate", "2/min"):
            for _ in range(2):
                res = client.put(url, {"scores": scores(4)}, format="json")
                self.assertEqual(res.status_code, 200, res.content)
            res = client.put(url, {"scores": scores(4)}, format="json")
        self.assertEqual(res.status_code, 429)

    def test_reviews_mine(self) -> None:
        self.other_org(self.mates_a[0])
        client = self.client_for(self.mates_a[0])
        self.review(self.mates_a[0], self.cap_a, 4)
        self.review(self.mates_a[1], self.cap_a, 2)
        res = client.get(self.url("reviews/mine/"))
        self.assertEqual(res.status_code, 200, res.content)
        rows = res.json()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["scores"], scores(4))
        self.assertEqual(row["captain_org_user_id"], self.ou(self.cap_a).pk)
        self.assertEqual(row["void_kind"], "")
        self.assertNotIn("rater", row)
        self.assertNotIn("rating", row)
        body = _dump(res)
        self.assertNotIn(self.mates_a[1].username, body)
        self.expire_window()
        review = CaptainReview.objects.get(
            rater=self.ou(self.mates_a[0]), event_captain__event=self.event
        )
        void_review(
            self.org,
            review_id=review.pk,
            actor=self.admin,
            reason="abuse",
            now=tz.now(),
        )
        row = client.get(self.url("reviews/mine/")).json()[0]
        self.assertEqual(row["scores"], scores(4))
        self.assertEqual(row["void_kind"], "moderated")
        self.assertNotIn("void_reason", row)
        self.assertEqual(APIClient().get(self.url("reviews/mine/")).status_code, 403)
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        res = client.get(self.url("reviews/mine/"))
        self.assertEqual(res.json()["code"], "feature_locked")

    def test_reviews_mine_scoped_to_org(self) -> None:
        other = self.other_org(self.mates_a[0])
        res = self.client_for(self.mates_a[0]).get(self.url("reviews/mine/"))
        self.assertEqual(res.json(), [])
        res = self.client_for(self.mates_a[0]).get(
            f"/api/organizations/{other.org.pk}/leadership/reviews/mine/"
        )
        self.assertEqual([r["event_id"] for r in res.json()], [other.event.pk])


class ModerationApiTest(ApiCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        self.first = self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 4)

    def captains(self, user: CustomUser) -> dict[int, dict[str, Any]]:
        res = self.client_for(user).get(self.url(f"events/{self.event.pk}/reviews/"))
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body["event"], {"pk": self.event.pk, "name": self.event.name})
        return {c["org_user_id"]: c for c in body["captains"]}

    def test_staff_sees_raters(self) -> None:
        entry = self.captains(self.admin)[self.ou(self.cap_a).pk]
        self.assertFalse(entry["own_snapshot"])
        self.assertIsNone(entry["aggregate"])
        self.assertFalse(entry["released"])
        raters = {r["rater"]["user_pk"] for r in entry["reviews"]}
        self.assertEqual(raters, {self.mates_a[0].pk, self.mates_a[1].pk})
        row = entry["reviews"][0]
        for key in (
            "pk",
            "scores",
            "submitted_at",
            "updated_at",
            "voided_at",
            "void_kind",
            "void_reason",
        ):
            self.assertIn(key, row)

    def test_void_requires_reason_and_unvoid(self) -> None:
        client = self.client_for(self.admin)
        url = self.url(f"reviews/{self.first.pk}/void/")
        self.assertEqual(client.post(url, {}, format="json").status_code, 400)
        res = client.post(url, {"reason": "abuse"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["void_kind"], "moderated")
        self.assertEqual(res.json()["void_reason"], "abuse")
        self.assertEqual(res.json()["rater"]["user_pk"], self.mates_a[0].pk)
        res = client.post(
            self.url(f"reviews/{self.first.pk}/unvoid/"), {}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["void_kind"], "")
        self.assertIsNone(res.json()["voided_at"])

    def test_admin_captain_sees_no_raters_and_cannot_void(self) -> None:
        third = self.review(self.mates_a[2], self.cap_a, 3)
        other = self.review(self.mates_b[0], self.cap_b, 3)
        own_reviews = list(
            CaptainReview.objects.filter(event_captain__captain__user=self.cap_a)
        )
        self.assertEqual(len(own_reviews), 3)
        self.org.admins.add(self.cap_a)
        invalidate_obj(self.org)
        client = self.client_for(self.cap_a)

        def check(released: bool) -> None:
            res = client.get(self.url(f"events/{self.event.pk}/reviews/"))
            self.assertEqual(res.status_code, 200, res.content)
            body = _dump(res)
            entries = {c["org_user_id"]: c for c in res.json()["captains"]}
            own = entries[self.ou(self.cap_a).pk]
            self.assertTrue(own["own_snapshot"])
            self.assertIsNone(own["reviews"])
            self.assertNotIn('"pk"', json.dumps(own, default=str))
            listed = {r["pk"] for c in entries.values() for r in c["reviews"] or []}
            self.assertEqual(listed, {other.pk})
            for review in own_reviews:
                self.assertNotIn(review.rater.user.username, body)
                self.assertNotIn(f'"org_user_pk": {review.rater_id}', body)
                self.assertNotIn(
                    review.submitted_at.isoformat().replace("+00:00", "Z"), body
                )
                self.assertNotIn(
                    review.updated_at.isoformat().replace("+00:00", "Z"), body
                )
            if released:
                self.assertIsNotNone(own["aggregate"])
                self.assertEqual(own["aggregate"]["reviews"], 3)
                self.assertTrue(own["released"])
            else:
                self.assertIsNone(own["aggregate"])
                self.assertFalse(own["released"])
            theirs = entries[self.ou(self.cap_b).pk]
            self.assertFalse(theirs["own_snapshot"])
            self.assertEqual(
                theirs["reviews"][0]["rater"]["user_pk"], self.mates_b[0].pk
            )

        check(released=False)
        self.expire_window()
        check(released=True)
        for action in ("void", "unvoid"):
            res = client.post(
                self.url(f"reviews/{third.pk}/{action}/"),
                {"reason": "mine"},
                format="json",
            )
            self.assertEqual(res.status_code, 403)
            self.assertEqual(res.json()["code"], "cannot_moderate_own_reviews")

    @override_settings(CACHEOPS_ENABLED=False)
    def test_event_reviews_budget_independent_of_review_count(self) -> None:
        def measure() -> int:
            with CaptureQueriesContext(connection) as ctx:
                self.captains(self.admin)
            return len(ctx.captured_queries)

        before = measure()
        self.review(self.mates_a[2], self.cap_a, 3)
        for mate in self.mates_b:
            self.review(mate, self.cap_b, 3)
        self.assertEqual(measure(), before)


class MemberApiTest(ApiCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()

    def member_view(
        self, viewer: CustomUser, captain: CustomUser | None = None
    ) -> dict[str, Any]:
        res = self.client_for(viewer).get(
            self.url(f"members/{self.ou(captain or self.cap_a).pk}/")
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def test_captain_endpoints_never_contain_rater_ids(self) -> None:
        for mate in self.mates_a:
            self.review(mate, self.cap_a, 4)
        self.expire_window()
        client = self.client_for(self.cap_a)
        responses = [
            client.get(self.url(f"members/{self.ou(self.cap_a).pk}/")),
            client.get(self.url("reviews/pending/")),
            client.get(self.url("reviews/mine/")),
            client.get(
                f"/api/organizations/{self.org.pk}/standing/leadership/leaderboard/?metric=rating"
            ),
            client.get(
                f"/api/organizations/{self.org.pk}/standing/leadership/leaderboard/?metric=points"
            ),
        ]
        for res in responses:
            self.assertEqual(res.status_code, 200, res.content)
            body = _dump(res)
            for mate in self.mates_a:
                self.assertNotIn(mate.username, body)
                self.assertNotIn(f'"org_user_pk": {self.ou(mate).pk}', body)
                self.assertNotIn(f'"user_pk": {mate.pk}', body)

    def test_captain_member_view_changes_only_at_release(self) -> None:
        baseline = self.member_view(self.cap_a)
        for mate in self.mates_a:
            self.review(mate, self.cap_a, 4)
            self.assertEqual(self.member_view(self.cap_a), baseline)
        self.assertIsNone(baseline["rating"])
        self.assertEqual(baseline["events"], [])
        self.assertEqual(baseline["points"]["all_time"], 5 + 10)
        self.expire_window()
        released = self.member_view(self.cap_a)
        self.assertIsNotNone(released["rating"])
        self.assertEqual(released["reviews"], 3)
        self.assertEqual(released["points"]["all_time"], 5 + 10 + 8)
        self.assertEqual(released["events"][0]["reviews"], 3)

    def test_staff_view_shows_live_events(self) -> None:
        for mate in self.mates_a[:2]:
            self.review(mate, self.cap_a, 4)
        body = self.member_view(self.admin)
        self.assertEqual(body["events"][0]["reviews"], 2)
        self.assertFalse(body["events"][0]["released"])
        self.assertEqual(set(body["points"]), {"all_time", "this_month"})

    def test_staff_view_totals_include_unreleased_events(self) -> None:
        for mate in self.mates_a[:2]:
            self.review(mate, self.cap_a, 4)
        rating_points = self.points(self.cap_a, "captain_rating")
        self.assertTrue(rating_points)
        staff = self.member_view(self.admin)
        own = self.member_view(self.cap_a)
        self.assertEqual(staff["reviews"], 2)
        self.assertIsNotNone(staff["rating"])
        self.assertEqual(own["reviews"], 0)
        self.assertIsNone(own["rating"])
        self.assertEqual(
            staff["points"]["all_time"], own["points"]["all_time"] + rating_points
        )

    def test_released_aggregate_needs_three_reviews(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 4)
        self.review(self.mates_a[1], self.cap_a, 2)
        self.expire_window()
        own = self.member_view(self.cap_a)
        self.assertEqual(own["reviews"], 2)
        self.assertIsNone(own["events"][0]["traits"])
        self.assertIsNone(own["events"][0]["reviews"])

    def test_other_member_summary_has_no_events(self) -> None:
        res = self.client_for(self.mates_b[0]).get(
            self.url(f"members/{self.ou(self.cap_a).pk}/")
        )
        self.assertEqual(res.status_code, 403)
        OrgLeadershipSettings.objects.create(
            organization=self.org, leaderboard_public=True
        )
        body = self.member_view(self.mates_b[0])
        self.assertNotIn("events", body)
        self.assertEqual(body["member"]["org_user_pk"], self.ou(self.cap_a).pk)
        for key in ("rating", "status", "reviews", "traits", "points"):
            self.assertIn(key, body)


class SettingsApiTest(ApiCase):
    def test_settings_patch_min_reviewers_floor(self) -> None:
        client = self.client_for(self.admin)
        res = client.patch(
            self.url("settings/"), {"rating_min_reviewers": 1}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        res = client.patch(
            self.url("settings/"), {"points": {"captain_rating": 2}}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        res = client.patch(self.url("settings/"), {"bogus": 2}, format="json")
        self.assertEqual(res.status_code, 400)
        res = client.patch(
            self.url("settings/"), {"review_window_hours": 0}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_patch_creates_row_and_points(self) -> None:
        res = self.client_for(self.admin).patch(
            self.url("settings/"),
            {
                "review_window_hours": 24,
                "points": {"captained": 8, "placement_1": None},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body["review_window_hours"], 24)
        self.assertIn("ranges", body)
        captained = next(k for k in body["points"] if k["kind"] == "captained")
        self.assertEqual(captained["points"], 8)
        self.assertTrue(
            self.org.logs.filter(action="update_leadership_settings").exists()
        )

    def test_get_lists_points(self) -> None:
        body = self.client_for(self.admin).get(self.url("settings/")).json()
        self.assertEqual(
            {k["kind"] for k in body["points"]},
            {
                "captained",
                "placement_1",
                "placement_2",
                "placement_3",
                "draft_completed",
            },
        )
        self.assertEqual(OrgLeadershipSettings.objects.count(), 0)

    def test_patch_release_fields(self) -> None:
        res = self.client_for(self.admin).patch(
            self.url("settings/"),
            {"require_staff_release": True, "auto_release_after_hours": 48},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertIs(body["require_staff_release"], True)
        self.assertEqual(body["auto_release_after_hours"], 48)

    def test_patch_hours_null_ok(self) -> None:
        res = self.client_for(self.admin).patch(
            self.url("settings/"), {"auto_release_after_hours": None}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIsNone(res.json()["auto_release_after_hours"])

    def test_patch_hours_bounds(self) -> None:
        client = self.client_for(self.admin)
        for hours in (0, 721):
            with self.subTest(hours=hours):
                res = client.patch(
                    self.url("settings/"),
                    {"auto_release_after_hours": hours},
                    format="json",
                )
                self.assertEqual(res.status_code, 400)
                errors = res.json()["auto_release_after_hours"]
                self.assertNotEqual(errors, ["Unknown setting."])

    def test_patch_gate_non_bool_400(self) -> None:
        res = self.client_for(self.admin).patch(
            self.url("settings/"), {"require_staff_release": "maybe"}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertNotEqual(res.json()["require_staff_release"], ["Unknown setting."])

    # Characterization: DRF already rejects null on non-nullable fields.
    def test_patch_null_non_nullable_400(self) -> None:
        res = self.client_for(self.admin).patch(
            self.url("settings/"), {"prior_rating": None}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_get_reports_hours_range(self) -> None:
        body = self.client_for(self.admin).get(self.url("settings/")).json()
        self.assertEqual(body["ranges"]["auto_release_after_hours"], [1, 720])


class TraitsApiTest(ApiCase):
    def test_list_defaults_and_upsert(self) -> None:
        res = self.client_for(self.cap_a).get(self.url("traits/"))
        self.assertEqual([t["key"] for t in res.json()["traits"]][0], "communication")
        res = self.client_for(self.admin).put(
            self.url("traits/"),
            {"traits": [{"key": "macro", "label": "Macro", "order": 5}]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(len(res.json()["traits"]), 5)

    def test_trait_delete_conflict(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a, 4)
        res = self.client_for(self.admin).delete(self.url("traits/drafting/"))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], "trait_in_use")
        res = self.client_for(self.admin).put(
            self.url("traits/"),
            {"traits": [{"key": "drafting", "active": False}]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)

    def test_delete_missing_trait_404(self) -> None:
        res = self.client_for(self.admin).delete(self.url("traits/nope/"))
        self.assertEqual(res.status_code, 404)

    def test_too_many_active(self) -> None:
        items = [{"key": f"t{i}", "label": f"T{i}"} for i in range(5)]
        res = self.client_for(self.admin).put(
            self.url("traits/"), {"traits": items}, format="json"
        )
        self.assertEqual(res.status_code, 400)


class LeaderboardTest(ApiCase):
    def setUp(self) -> None:
        super().setUp()
        OrgLeadershipSettings.objects.create(
            organization=self.org, leaderboard_public=True, ranked_min_reviews=2
        )
        self.close()
        for mate in self.mates_a:
            self.review(mate, self.cap_a, 5)
        self.expire_window()

    def board(self, viewer: CustomUser, metric: str = "rating") -> dict[str, Any]:
        res = self.client_for(viewer).get(
            f"/api/organizations/{self.org.pk}/standing/leadership/leaderboard/?metric={metric}"
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def test_rating_board_ranks_released_captains(self) -> None:
        board = self.board(self.mates_b[0])
        self.assertEqual(len(board["rows"]), 1)
        self.assertGreater(board["rows"][0]["value"], 4)
        self.assertEqual(board["rows"][0]["sample"], 3)

    def test_trait_metric(self) -> None:
        self.assertEqual(len(self.board(self.mates_b[0], "rating.drafting")["rows"]), 1)

    def test_points_board_excludes_contribution_rows(self) -> None:
        award_entry(
            org=self.org,
            user=self.cap_a,
            kind="manual",
            points=100,
            reason="help",
            occurred_at=tz.now(),
        )
        board = self.board(self.mates_b[0], "points")
        totals = {r["member"]["user_pk"]: r["value"] for r in board["rows"]}
        self.assertEqual(totals[self.cap_a.pk], 5 + 10 + 10)
        self.assertEqual(totals[self.cap_b.pk], 5 + 6)

    def test_tracks_list_trait_metrics(self) -> None:
        res = self.client_for(self.cap_a).get(
            f"/api/organizations/{self.org.pk}/standing/tracks/"
        )
        track = next(t for t in res.json()["tracks"] if t["key"] == "leadership")
        self.assertIn("rating.communication", [m["key"] for m in track["metrics"]])

    def test_unknown_trait_metric_rejected(self) -> None:
        res = self.client_for(self.mates_b[0]).get(
            f"/api/organizations/{self.org.pk}/standing/leadership/leaderboard/?metric=rating.bogus"
        )
        self.assertEqual(res.status_code, 400)

    def test_points_hide_unreleased_captain_rating(self) -> None:
        later, tournament = self.make_event("Later Cup")
        self.make_team(
            "Later", self.cap_a, self.mates_a, placement=None, tournament=tournament
        )
        for user in [self.cap_a, *self.mates_a]:
            self.admit(user, later)
        self.close(later)
        for mate in self.mates_a:
            self.review(mate, self.cap_a, 5, event=later)
        self.assertEqual(self.points(self.cap_a, "captain_rating", later), 10)
        totals = {
            r["member"]["user_pk"]: r["value"]
            for r in self.board(self.mates_b[0], "points")["rows"]
        }
        self.assertEqual(totals[self.cap_a.pk], 5 + 10 + 10 + 5)

    @override_settings(CACHEOPS_ENABLED=False)
    def test_board_budget_independent_of_captain_count(self) -> None:
        def measure(metric: str) -> int:
            with CaptureQueriesContext(connection) as ctx:
                self.board(self.admin, metric)
            return len(ctx.captured_queries)

        before = {m: measure(m) for m in ("rating", "points")}
        EventCaptain.objects.filter(captain__user=self.cap_b).update(
            window_closes_at=tz.now() + timedelta(hours=1)
        )
        for mate in self.mates_b:
            self.review(mate, self.cap_b, 4)
        self.expire_window()
        self.assertEqual(len(self.board(self.admin)["rows"]), 2)
        self.assertEqual({m: measure(m) for m in ("rating", "points")}, before)
