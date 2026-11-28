from typing import Any
from unittest import mock

from cacheops import invalidate_obj
from django.utils import timezone as tz

from app.models import CustomUser
from org.leadership.adapter import LEADERSHIP
from org.leadership.kinds import LeadershipKind
from org.leadership.summary import member_payload
from org.leadership.visibility import REVIEW_DERIVED_KINDS, feedback_hidden
from org.models_leadership import OrgLeadershipSettings
from org.standing import api as standing
from org.standing.periods import parse_period
from org.standing.types import Leaderboard
from org.tests.leadership_base import ALL_FIVES
from org.tests.test_leadership_api import ApiCase

RATING_METRICS = ("rating", *(f"rating.{key}" for key in ALL_FIVES))
MEMBER_KEYS = {"member", "rating", "status", "reviews", "traits", "points"}


class VisibilityCase(ApiCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        for mate in self.mates_a:
            self.review(mate, self.cap_a, 4)
        for mate in self.mates_b:
            self.review(mate, self.cap_b, 3)
        self.expire_window()
        self.set_settings(visible=False)
        self.rating_points = self.points(self.cap_a, LeadershipKind.CAPTAIN_RATING)
        assert self.rating_points

    def set_settings(self, *, visible: bool, public: bool = True) -> None:
        OrgLeadershipSettings.objects.update_or_create(
            organization=self.org,
            defaults={
                "leaderboard_public": public,
                "ranked_min_reviews": 1,
                "captain_feedback_visible": visible,
            },
        )

    def member_view(
        self, viewer: CustomUser, captain: CustomUser | None = None
    ) -> dict[str, Any]:
        res = self.client_for(viewer).get(
            self.url(f"members/{self.ou(captain or self.cap_a).pk}/")
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def board(self, viewer: CustomUser, metric: str) -> Leaderboard:
        return standing.leaderboard(
            self.org,
            "leadership",
            metric,
            parse_period(self.org, None),
            viewer=viewer,
        )

    def row_users(self, board: Leaderboard) -> list[int]:
        return [int(r.member["user_pk"]) for r in board.rows]

    def event_reviews(self, viewer: CustomUser) -> dict[int, dict[str, Any]]:
        res = self.client_for(viewer).get(self.url(f"events/{self.event.pk}/reviews/"))
        self.assertEqual(res.status_code, 200, res.content)
        return {c["org_user_id"]: c for c in res.json()["captains"]}

    def make_admin(self, user: CustomUser) -> None:
        self.org.admins.add(user)
        invalidate_obj(self.org)

    def assert_hidden_member(self, body: dict[str, Any]) -> None:
        self.assertIs(body["feedback_private"], True)
        self.assertIsNone(body["rating"])
        self.assertEqual(body["status"], "new")
        self.assertIsNone(body["reviews"])
        self.assertTrue(body["traits"])
        for trait in body["traits"]:
            self.assertIsNone(trait["rating"])
        self.assertNotIn("events", body)


class PredicateTest(VisibilityCase):
    def test_feedback_hidden_only_for_self_when_off(self) -> None:
        captain = self.ou(self.cap_a)
        other = self.ou(self.mates_b[0])
        self.assertTrue(feedback_hidden(self.org, viewer=captain, subject=captain))
        self.assertFalse(feedback_hidden(self.org, viewer=other, subject=captain))
        self.assertFalse(feedback_hidden(self.org, viewer=None, subject=captain))
        self.set_settings(visible=True)
        self.assertFalse(feedback_hidden(self.org, viewer=captain, subject=captain))

    def test_review_derived_kinds(self) -> None:
        self.assertEqual(
            REVIEW_DERIVED_KINDS, frozenset({LeadershipKind.CAPTAIN_RATING})
        )


class MemberPayloadTest(VisibilityCase):
    def test_member_payload_self_hidden(self) -> None:
        body = self.member_view(self.cap_a)
        self.assert_hidden_member(body)
        self.assertEqual(body["points"]["all_time"], 5 + 10)
        direct = member_payload(
            self.ou(self.cap_a),
            now=tz.now(),
            detail=True,
            staff=False,
            viewer_user_id=self.cap_a.pk,
        )
        self.assertNotIn("events", direct)
        self.assertEqual(direct["points"], 5 + 10)
        self.assertIs(direct["feedback_private"], True)

    def test_member_payload_others_unchanged(self) -> None:
        body = self.member_view(self.mates_b[0])
        self.assertIs(body["feedback_private"], False)
        self.assertIsNotNone(body["rating"])
        self.assertEqual(body["reviews"], 3)
        self.assertEqual(body["points"]["all_time"], 5 + 10 + self.rating_points)

    def test_staff_captain_no_exemption(self) -> None:
        self.make_admin(self.cap_a)
        body = self.member_view(self.cap_a)
        self.assert_hidden_member(body)
        self.assertEqual(body["points"]["all_time"], 5 + 10)
        for metric in (*RATING_METRICS, "points"):
            with self.subTest(metric=metric):
                board = self.board(self.cap_a, metric)
                self.assertTrue(board.own_private)
                self.assertNotIn(self.cap_a.pk, self.row_users(board))
        own = self.event_reviews(self.cap_a)[self.ou(self.cap_a).pk]
        self.assertIsNone(own["aggregate"])
        self.assertIs(own["feedback_private"], True)

    def test_staff_view_of_captain_unchanged(self) -> None:
        body = self.member_view(self.admin)
        self.assertIs(body["feedback_private"], False)
        self.assertIsNotNone(body["rating"])
        self.assertEqual(body["reviews"], 3)
        self.assertEqual(body["events"][0]["reviews"], 3)
        self.assertEqual(body["points"]["all_time"], 5 + 10 + self.rating_points)
        entry = self.event_reviews(self.admin)[self.ou(self.cap_a).pk]
        self.assertIs(entry["feedback_private"], False)
        self.assertEqual(len(entry["reviews"]), 3)

    def test_member_standing_own_ratings_hidden(self) -> None:
        captain = self.ou(self.cap_a)
        found = standing.member_standing(
            captain,
            viewer=self.cap_a,
            roles=standing.viewer_roles(self.org, self.cap_a),
        )
        block = found["leadership"]
        self.assertIs(block["feedback_private"], True)
        self.assertIsNone(block["rating"])
        self.assertIsNone(block["reviews"])
        self.assertEqual(block["status"], "new")
        self.assertTrue(all(t["rating"] is None for t in block["traits"]))
        self.assertEqual(block["points"], 5 + 10)
        other = standing.member_standing(
            captain,
            viewer=self.mates_b[0],
            roles=standing.viewer_roles(self.org, self.mates_b[0]),
        )["leadership"]
        self.assertIs(other["feedback_private"], False)
        self.assertIsNotNone(other["rating"])
        self.assertEqual(other["points"], 5 + 10 + self.rating_points)


class LeaderboardVisibilityTest(VisibilityCase):
    def test_leaderboard_rating_and_trait_metrics_own_row_hidden(self) -> None:
        for metric in RATING_METRICS:
            with self.subTest(metric=metric):
                board = self.board(self.cap_a, metric)
                self.assertIsNone(board.own_row)
                self.assertTrue(board.own_private)
                self.assertEqual(self.row_users(board), [self.cap_b.pk])

    def test_leaderboard_points_own_row_recomputed(self) -> None:
        board = self.board(self.cap_a, "points")
        self.assertTrue(board.own_private)
        self.assertNotIn(self.cap_a.pk, self.row_users(board))
        assert board.own_row is not None
        self.assertEqual(board.own_row.org_user_id, self.ou(self.cap_a).pk)
        self.assertEqual(board.own_row.value, 5 + 10)
        self.assertEqual(board.own_row.status, "new")
        self.assertEqual(board.own_row.sample, 2)

    def test_points_total_consistent_for_hidden_captain(self) -> None:
        full = self.board(self.admin, "points")
        others = sum(
            int(r.value or 0) for r in full.rows if r.member["user_pk"] != self.cap_a.pk
        )
        for public in (True, False):
            with self.subTest(rows_visible=public):
                self.set_settings(visible=False, public=public)
                board = self.board(self.cap_a, "points")
                self.assertIs(board.rows_visible, public)
                assert board.own_row is not None
                assert board.total is not None
                shown = sum(int(r.value or 0) for r in board.rows)
                self.assertEqual(shown, others if public else 0)
                self.assertEqual(board.total - others - board.own_row.value, 0)
                if public:
                    self.assertEqual(board.total - shown - board.own_row.value, 0)

    def test_points_total_other_viewer_unchanged(self) -> None:
        full = self.board(self.admin, "points")
        board = self.board(self.mates_b[0], "points")
        self.assertEqual(board.total, full.total)
        self.assertTrue(board.own_private)
        values = {r.member["user_pk"]: r.value for r in board.rows}
        self.assertEqual(values[self.cap_a.pk], 5 + 10 + self.rating_points)

    def test_other_viewer_sees_captain_row(self) -> None:
        for metric in RATING_METRICS:
            with self.subTest(metric=metric):
                board = self.board(self.mates_b[0], metric)
                self.assertTrue(board.own_private)
                self.assertIsNone(board.own_row)
                self.assertIn(self.cap_a.pk, self.row_users(board))

    def add_third_captain(self) -> CustomUser:
        event, tournament = self.make_event("Cup 2")
        cap = self.make_user("ld_cap_c")
        mates = [self.make_user(f"ld_c{i}") for i in range(2)]
        self.make_team("Charlie", cap, mates, tournament=tournament)
        for user in [cap, *mates]:
            self.admit(user, event)
        self.close(event)
        for mate in mates:
            self.review(mate, cap, 2, event=event)
        self.expire_window(event)
        return cap

    def test_hidden_own_row_removed_before_limit(self) -> None:
        cap_c = self.add_third_captain()
        for metric in (*RATING_METRICS, "points"):
            with self.subTest(metric=metric):
                full = self.board(self.admin, metric)
                self.assertEqual(
                    self.row_users(full), [self.cap_a.pk, self.cap_b.pk, cap_c.pk]
                )
                with mock.patch("org.leadership.adapter.LEADERBOARD_LIMIT", 2):
                    board = self.board(self.cap_a, metric)
                self.assertEqual(self.row_users(board), [self.cap_b.pk, cap_c.pk])

    def test_track_info_own_private(self) -> None:
        for user, expected in ((self.cap_a, True), (self.admin, False)):
            with self.subTest(user=user.username):
                (info,) = standing.tracks_for(
                    self.org.pk,
                    viewer=user,
                    features={"leadership"},
                    roles=standing.viewer_roles(self.org, user),
                )
                self.assertIs(info.own_private, expected)
        res = self.client_for(self.cap_a).get(
            f"/api/organizations/{self.org.pk}/standing/tracks/"
        )
        (track,) = res.json()["tracks"]
        self.assertIs(track["own_private"], True)
        res = self.client_for(self.cap_a).get(
            f"/api/organizations/{self.org.pk}/standing/leadership/leaderboard/"
            "?metric=points"
        )
        body = res.json()
        self.assertIs(body["own_private"], True)
        self.assertNotIn(self.cap_a.pk, [r["member"]["user_pk"] for r in body["rows"]])
        self.set_settings(visible=True)
        (info,) = standing.tracks_for(
            self.org.pk,
            viewer=self.cap_a,
            features={"leadership"},
            roles=standing.viewer_roles(self.org, self.cap_a),
        )
        self.assertIs(info.own_private, False)


class EventReviewsVisibilityTest(VisibilityCase):
    def test_event_reviews_own_aggregate_hidden(self) -> None:
        self.make_admin(self.cap_a)
        entries = self.event_reviews(self.cap_a)
        own = entries[self.ou(self.cap_a).pk]
        self.assertTrue(own["own_snapshot"])
        self.assertIsNone(own["aggregate"])
        self.assertIs(own["feedback_private"], True)
        self.assertIs(own["released"], False)
        self.assertEqual(own["release_state"], "hidden")
        self.assertIsNone(own["released_at"])
        self.assertIsNone(own["released_by"])
        theirs = entries[self.ou(self.cap_b).pk]
        self.assertIs(theirs["feedback_private"], False)
        self.assertEqual(len(theirs["reviews"]), 2)


class VisibleSettingTest(VisibilityCase):
    def setUp(self) -> None:
        super().setUp()
        self.set_settings(visible=True)

    def test_visible_setting_true_changes_nothing(self) -> None:
        body = self.member_view(self.cap_a)
        self.assertEqual(set(body), MEMBER_KEYS | {"events", "feedback_private"})
        self.assertIs(body["feedback_private"], False)
        self.assertIsNotNone(body["rating"])
        self.assertEqual(body["reviews"], 3)
        self.assertEqual(body["events"][0]["reviews"], 3)
        self.assertEqual(body["points"]["all_time"], 5 + 10 + self.rating_points)
        for metric in RATING_METRICS:
            with self.subTest(metric=metric):
                board = self.board(self.cap_a, metric)
                self.assertFalse(board.own_private)
                assert board.own_row is not None
                self.assertIsNotNone(board.own_row.value)
                self.assertIn(self.cap_a.pk, self.row_users(board))
        points = self.board(self.cap_a, "points")
        self.assertFalse(points.own_private)
        assert points.own_row is not None
        self.assertEqual(points.own_row.value, 5 + 10 + self.rating_points)
        self.assertEqual(points.own_row.status, "ranked")
        self.assertEqual(points.total, sum(int(r.value or 0) for r in points.rows))
        self.make_admin(self.cap_a)
        own = self.event_reviews(self.cap_a)[self.ou(self.cap_a).pk]
        self.assertIs(own["feedback_private"], False)
        self.assertIsNotNone(own["aggregate"])
        self.assertEqual(own["release_state"], "released")
        self.assertTrue(own["released"])
        captain = self.ou(self.cap_a)
        block = LEADERSHIP.member_standing(
            captain,
            viewer=self.cap_a,
            roles=standing.viewer_roles(self.org, self.cap_a),
            now=tz.now(),
        )
        assert block is not None
        self.assertEqual(set(block), (MEMBER_KEYS - {"member"}) | {"feedback_private"})
        self.assertIs(block["feedback_private"], False)
        self.assertIsNotNone(block["rating"])
