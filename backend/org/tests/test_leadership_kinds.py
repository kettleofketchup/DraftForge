from django.test import SimpleTestCase

from org.leadership.kinds import PLACEMENT_KINDS, RATED_KINDS, LeadershipKind
from org.standing.kinds import FORMULA_KINDS, KINDS, ONCE_PER_EVENT_KINDS, kinds_for


class LeadershipKindsTest(SimpleTestCase):
    def test_kinds_for_leadership(self) -> None:
        self.assertEqual(
            kinds_for("leadership"),
            {
                "captained",
                "placement_1",
                "placement_2",
                "placement_3",
                "draft_completed",
                "captain_rating",
            },
        )

    def test_defaults(self) -> None:
        self.assertEqual(
            {k: KINDS[k].default_points for k in kinds_for("leadership")},
            {
                "captained": 5,
                "placement_1": 10,
                "placement_2": 6,
                "placement_3": 3,
                "draft_completed": 2,
                "captain_rating": None,
            },
        )

    def test_captain_rating_is_formula(self) -> None:
        self.assertEqual(FORMULA_KINDS, {"captain_rating"})

    def test_once_per_event_union(self) -> None:
        self.assertEqual(
            ONCE_PER_EVENT_KINDS,
            {"event_host", "event_helper", *kinds_for("leadership")},
        )

    def test_contribution_kinds_unchanged(self) -> None:
        self.assertEqual(
            kinds_for("contribution"),
            {
                "promo_message",
                "event_host",
                "event_helper",
                "manual",
                "promo_void",
                "promo_restore",
            },
        )

    def test_rated_and_placement_kinds(self) -> None:
        self.assertNotIn(LeadershipKind.CAPTAIN_RATING, RATED_KINDS)
        self.assertEqual(len(RATED_KINDS), 5)
        self.assertEqual(
            dict(PLACEMENT_KINDS),
            {
                1: LeadershipKind.PLACEMENT_1,
                2: LeadershipKind.PLACEMENT_2,
                3: LeadershipKind.PLACEMENT_3,
            },
        )
