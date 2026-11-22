import json
from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext, override_settings
from django.utils import timezone as tz

from app.models import CustomUser
from org.contributions.services import award_entry
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import Organization, OrgUser
from org.models_leadership import CaptainReview, EventCaptain, OrgLeadershipSettings
from org.tests.leadership_base import LeadershipTestCase, scores


def _dump(response: object) -> str:
    return json.dumps(response.json(), default=str)  # type: ignore[attr-defined]


class ReviewApiTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        self.cap_ou = self.ou(self.cap_a)

    def review_url(
        self, event_id: int | None = None, captain: int | None = None
    ) -> str:
        return self.url(
            f"events/{event_id or self.event.pk}/captains/{captain or self.cap_ou.pk}/review/"
        )

    def test_pending_lists_open_windows(self) -> None:
        res = self.client_for(self.mates_a[0]).get(self.url("reviews/pending/"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["pending"]), 1)
        self.assertEqual(len(res.json()["traits"]), 4)

    def test_put_and_delete_review(self) -> None:
        client = self.client_for(self.mates_a[0])
        res = client.put(self.review_url(), {"scores": scores(4)}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["scores"]["drafting"], 4)
        res = client.delete(self.review_url())
        self.assertEqual(res.status_code, 204)
        self.assertEqual(CaptainReview.objects.get().void_kind, "withdrawn")

    def test_not_in_pool_forbidden(self) -> None:
        res = self.client_for(self.mates_b[0]).put(
            self.review_url(), {"scores": scores(4)}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_closed_window_conflict(self) -> None:
        self.expire_window()
        res = self.client_for(self.mates_a[0]).put(
            self.review_url(), {"scores": scores(4)}, format="json"
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], "review_window_closed")

    def test_locked_feature(self) -> None:
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        res = self.client_for(self.mates_a[0]).put(
            self.review_url(), {"scores": scores(4)}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_cross_org_event_is_404(self) -> None:
        other = Organization.objects.create(name="Other", owner=self.admin)
        set_org_feature(other, FeatureKey.LEADERSHIP, enabled=True, actor=None)
        OrgUser.objects.create(user=self.mates_a[0], organization=other)
        res = self.client_for(self.mates_a[0]).put(
            f"/api/organizations/{other.pk}/leadership/events/{self.event.pk}/captains/{self.cap_ou.pk}/review/",
            {"scores": scores(4)},
            format="json",
        )
        self.assertEqual(res.status_code, 404)


class ModerationApiTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        self.first = self.review(self.mates_a[0], self.cap_a, 5)
        self.review(self.mates_a[1], self.cap_a, 4)

    def test_staff_sees_raters(self) -> None:
        res = self.client_for(self.admin).get(
            self.url(f"events/{self.event.pk}/reviews/")
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("rater", res.json()["reviews"][0])

    def test_member_cannot_list(self) -> None:
        res = self.client_for(self.mates_a[0]).get(
            self.url(f"events/{self.event.pk}/reviews/")
        )
        self.assertEqual(res.status_code, 403)

    def test_void_requires_reason_and_unvoid(self) -> None:
        client = self.client_for(self.admin)
        url = self.url(f"reviews/{self.first.pk}/void/")
        self.assertEqual(client.post(url, {}, format="json").status_code, 400)
        res = client.post(url, {"reason": "abuse"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["void_kind"], "moderated")
        res = client.post(
            self.url(f"reviews/{self.first.pk}/unvoid/"),
            {"reason": "fine"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["void_kind"], "")

    def test_captain_admin_cannot_moderate_or_see_raters(self) -> None:
        self.org.admins.add(self.cap_a)
        client = self.client_for(self.cap_a)
        res = client.get(self.url(f"events/{self.event.pk}/reviews/"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["reviews"], [])
        self.review(self.mates_b[0], self.cap_b, 3)
        body = client.get(self.url(f"events/{self.event.pk}/reviews/")).json()
        self.assertEqual(
            [r["captain"]["org_user_pk"] for r in body["reviews"]],
            [self.ou(self.cap_b).pk],
        )
        self.assertNotIn(self.first.pk, [r["pk"] for r in body["reviews"]])
        res = client.post(
            self.url(f"reviews/{self.first.pk}/void/"),
            {"reason": "mine"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], "cannot_moderate_own_reviews")

    def test_cross_org_void_is_404(self) -> None:
        other = Organization.objects.create(name="Other", owner=self.admin)
        set_org_feature(other, FeatureKey.LEADERSHIP, enabled=True, actor=None)
        other.admins.add(self.admin)
        res = self.client_for(self.admin).post(
            f"/api/organizations/{other.pk}/leadership/reviews/{self.first.pk}/void/",
            {"reason": "abuse"},
            format="json",
        )
        self.assertEqual(res.status_code, 404)


class AnonymityTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()

    def member_view(self, viewer: CustomUser) -> dict:
        return (
            self.client_for(viewer)
            .get(self.url(f"members/{self.ou(self.cap_a).pk}/"))
            .json()
        )

    def test_captain_never_sees_rater_ids(self) -> None:
        for mate in self.mates_a:
            self.review(mate, self.cap_a, 4)
        self.expire_window()
        body = _dump(
            self.client_for(self.cap_a).get(
                self.url(f"members/{self.ou(self.cap_a).pk}/")
            )
        )
        for mate in self.mates_a:
            self.assertNotIn(mate.username, body)
            self.assertNotIn(f'"org_user_pk": {self.ou(mate).pk}', body)

    def test_nothing_before_release(self) -> None:
        for mate in self.mates_a:
            self.review(mate, self.cap_a, 4)
        own = self.member_view(self.cap_a)
        self.assertIsNone(own["rating"])
        self.assertEqual(own["reviews"], 0)
        self.assertEqual(own["history"], [])
        self.assertEqual(own["points"], 5 + 10)

    def test_released_aggregate_needs_three_reviews(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 4)
        self.review(self.mates_a[1], self.cap_a, 2)
        self.expire_window()
        own = self.member_view(self.cap_a)
        self.assertEqual(own["reviews"], 2)
        self.assertIsNone(own["history"][0]["traits"])
        self.assertIsNone(own["history"][0]["reviews"])
        self.review_third()
        own = self.member_view(self.cap_a)
        self.assertIsNotNone(own["history"][0]["traits"])

    def review_third(self) -> None:
        CaptainReview.objects.create(
            event_captain=self.snapshot(self.cap_a),
            rater=self.ou(self.mates_a[2]),
            submitted_at=self.snapshot(self.cap_a).window_closes_at,
        ).scores.create(trait=self.org.captain_traits.first(), score=3)

    def test_single_review_event_never_released(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 5)
        self.expire_window()
        own = self.member_view(self.cap_a)
        self.assertIsNone(own["rating"])
        self.assertEqual(own["history"], [])

    def test_others_get_summary_only_when_public(self) -> None:
        self.assertEqual(
            self.client_for(self.mates_b[0])
            .get(self.url(f"members/{self.ou(self.cap_a).pk}/"))
            .status_code,
            403,
        )
        OrgLeadershipSettings.objects.create(
            organization=self.org, leaderboard_public=True
        )
        body = self.member_view(self.mates_b[0])
        self.assertNotIn("history", body)


class SettingsApiTest(LeadershipTestCase):
    def test_min_reviewers_floor(self) -> None:
        res = self.client_for(self.admin).patch(
            self.url("settings/"), {"rating_min_reviewers": 1}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_patch_creates_row_and_kind_points(self) -> None:
        res = self.client_for(self.admin).patch(
            self.url("settings/"),
            {"review_window_hours": 24, "kind_points": {"captained": 8}},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["review_window_hours"], 24)
        captained = next(
            k for k in res.json()["kind_points"] if k["kind"] == "captained"
        )
        self.assertEqual(captained["points"], 8)
        self.assertTrue(
            self.org.logs.filter(action="update_leadership_settings").exists()
        )

    def test_member_cannot_read_settings(self) -> None:
        res = self.client_for(self.cap_a).get(self.url("settings/"))
        self.assertEqual(res.status_code, 403)


class TraitsApiTest(LeadershipTestCase):
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

    def test_delete_scored_trait_conflicts(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a, 4)
        res = self.client_for(self.admin).delete(self.url("traits/drafting/"))
        self.assertEqual(res.status_code, 409)
        res = self.client_for(self.admin).put(
            self.url("traits/"),
            {"traits": [{"key": "drafting", "active": False}]},
            format="json",
        )
        self.assertEqual(res.status_code, 200)

    def test_too_many_active(self) -> None:
        items = [{"key": f"t{i}", "label": f"T{i}"} for i in range(5)]
        res = self.client_for(self.admin).put(
            self.url("traits/"), {"traits": items}, format="json"
        )
        self.assertEqual(res.status_code, 400)


class LeaderboardTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        OrgLeadershipSettings.objects.create(
            organization=self.org, leaderboard_public=True, ranked_min_reviews=2
        )
        self.close()
        for mate in self.mates_a:
            self.review(mate, self.cap_a, 5)
        self.expire_window()

    def board(self, viewer: CustomUser, metric: str = "rating") -> dict:
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
        board = self.board(self.mates_b[0], "rating.drafting")
        self.assertEqual(len(board["rows"]), 1)

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

    def test_tracks_endpoint_lists_leadership(self) -> None:
        res = self.client_for(self.cap_a).get(
            f"/api/organizations/{self.org.pk}/standing/tracks/"
        )
        self.assertIn("leadership", [t["key"] for t in res.json()["tracks"]])

    @override_settings(CACHEOPS_ENABLED=False)
    def test_rating_board_query_budget(self) -> None:
        with CaptureQueriesContext(connection) as ctx:
            self.board(self.admin)
        self.assertLessEqual(len(ctx.captured_queries), 14)

    def test_unknown_trait_metric_rejected(self) -> None:
        res = self.client_for(self.mates_b[0]).get(
            f"/api/organizations/{self.org.pk}/standing/leadership/leaderboard/?metric=rating.bogus"
        )
        self.assertEqual(res.status_code, 400)

    def test_tracks_list_trait_metrics(self) -> None:
        res = self.client_for(self.cap_a).get(
            f"/api/organizations/{self.org.pk}/standing/tracks/"
        )
        track = next(t for t in res.json()["tracks"] if t["key"] == "leadership")
        self.assertIn("rating.communication", [m["key"] for m in track["metrics"]])

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
