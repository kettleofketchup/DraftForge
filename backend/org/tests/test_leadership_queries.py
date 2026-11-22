from datetime import datetime, timedelta

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as tz

from app.models import CustomUser
from events.models import Event
from org.leadership.queries import (
    CaptainRating,
    EventAggregate,
    captain_events,
    member_points,
    points_board,
    rating_board,
)
from org.leadership.rating import rate_params
from org.leadership.settings import get_leadership_settings
from org.leadership.traits import effective_traits
from org.models_leadership import CaptainTrait
from org.standing.periods import parse_period
from org.standing.scoring import Observation, weighted_rate
from org.tests.leadership_base import LeadershipTestCase, scores

AFTER_WINDOW = timedelta(hours=73)


class LeadershipQueriesTest(LeadershipTestCase):
    def board(
        self, now: datetime, *, include_unreleased: bool = False
    ) -> dict[int, CaptainRating]:
        return rating_board(
            self.org.pk,
            now=now,
            settings=get_leadership_settings(self.org),
            traits=effective_traits(self.org),
            include_unreleased=include_unreleased,
        )

    def points(
        self, now: datetime, *, include_unreleased: bool = False
    ) -> dict[int, int]:
        period = parse_period(self.org, None)
        return {
            row["org_user"]: row["total"]
            for row in points_board(
                self.org.pk, period, now=now, include_unreleased=include_unreleased
            )
        }

    def events_for(
        self, captain: CustomUser, now: datetime, *, staff: bool
    ) -> list[EventAggregate]:
        return captain_events(
            self.ou(captain),
            now=now,
            settings=get_leadership_settings(self.org),
            traits=effective_traits(self.org),
            staff=staff,
        )

    def review_all(self, captain: CustomUser, mates: list[CustomUser]) -> None:
        for mate in mates:
            self.review(mate, captain)

    def test_unreleased_event_invisible_to_captain(self) -> None:
        self.run_snapshot()
        self.review_all(self.cap_a, self.mates_a)
        cap = self.ou(self.cap_a).pk
        now = tz.now()

        self.assertNotIn(cap, self.board(now))
        self.assertEqual(self.points(now)[cap], 15)
        self.assertEqual(self.events_for(self.cap_a, now, staff=False), [])
        self.assertEqual(
            member_points(self.ou(self.cap_a), now=now, include_unreleased=False),
            {"all_time": 15, "this_month": 15},
        )

        self.assertIn(cap, self.board(now, include_unreleased=True))
        self.assertEqual(self.points(now, include_unreleased=True)[cap], 25)
        staff_view = self.events_for(self.cap_a, now, staff=True)
        self.assertEqual(len(staff_view), 1)
        self.assertFalse(staff_view[0]["released"])
        self.assertEqual(staff_view[0]["reviews"], 3)

        later = now + AFTER_WINDOW
        rating = self.board(later)[cap]
        self.assertEqual(rating.reviews, 3)
        self.assertEqual(self.points(later)[cap], 25)
        released = self.events_for(self.cap_a, later, staff=False)
        self.assertEqual(len(released), 1)
        self.assertTrue(released[0]["released"])
        self.assertEqual(released[0]["reviews"], 3)
        self.assertEqual(released[0]["rating"], 5.0)
        self.assertEqual(released[0]["captain_rating_points"], 10)
        self.assertNotIn("pool_size", released[0])

    def test_below_minimum_never_releases(self) -> None:
        self.run_snapshot()
        self.review(self.mates_a[0], self.cap_a)
        later = tz.now() + AFTER_WINDOW
        self.assertNotIn(self.ou(self.cap_a).pk, self.board(later))
        self.assertEqual(self.events_for(self.cap_a, later, staff=False), [])

    def test_event_aggregate_needs_three(self) -> None:
        self.run_snapshot()
        self.review_all(self.cap_a, self.mates_a)
        self.review_all(self.cap_b, self.mates_b)
        later = tz.now() + AFTER_WINDOW

        (two,) = self.events_for(self.cap_b, later, staff=False)
        self.assertTrue(two["released"])
        self.assertIsNone(two["reviews"])
        self.assertIsNone(two["rating"])
        self.assertIsNone(two["traits"])
        self.assertEqual(two["captain_rating_points"], 10)

        (three,) = self.events_for(self.cap_a, later, staff=False)
        self.assertEqual(three["reviews"], 3)
        self.assertEqual(three["rating"], 5.0)
        self.assertEqual(
            [t["key"] for t in three["traits"]],
            ["communication", "drafting", "composure", "sportsmanship"],
        )

        (staff,) = self.events_for(self.cap_b, later, staff=True)
        self.assertEqual(staff["reviews"], 2)

    def _older_event(self, days_ago: int) -> Event:
        event, tournament = self.make_event("Older")
        self.make_team("Alpha old", self.cap_a, self.mates_a, tournament=tournament)
        for user in [self.cap_a, *self.mates_a]:
            self.admit(user, event)
        self.run_snapshot(event)
        for mate in self.mates_a:
            self.review(mate, self.cap_a, 1, event=event)
        Event.objects.filter(pk=event.pk).update(
            scheduled_at=tz.now() - timedelta(days=days_ago)
        )
        event.refresh_from_db()
        return event

    def test_rating_decay_and_ranked_threshold(self) -> None:
        self.run_snapshot()
        self.review_all(self.cap_a, self.mates_a)
        self.review_all(self.cap_b, self.mates_b)
        later = tz.now() + AFTER_WINDOW
        board = self.board(later)
        self.assertEqual(board[self.ou(self.cap_b).pk].status, "new")
        self.assertEqual(board[self.ou(self.cap_a).pk].status, "ranked")

        older = self._older_event(100)
        self.event.refresh_from_db()
        params = rate_params(get_leadership_settings(self.org))
        expected = weighted_rate(
            [Observation(1.0, self.event.scheduled_at)] * 3
            + [Observation(0.0, older.scheduled_at)] * 3,
            now=later,
            params=params,
        )
        rating = self.board(later)[self.ou(self.cap_a).pk]
        self.assertEqual(rating.reviews, 6)
        communication = CaptainTrait.objects.get(
            organization=self.org, key="communication"
        )
        self.assertAlmostEqual(rating.traits[communication.pk], expected.rate)
        self.assertGreater(expected.rate, 0.5)

        Event.objects.filter(pk=older.pk).update(
            scheduled_at=tz.now() - timedelta(days=800)
        )
        rating = self.board(later)[self.ou(self.cap_a).pk]
        self.assertEqual(rating.reviews, 3)
        recent_only = weighted_rate(
            [Observation(1.0, self.event.scheduled_at)] * 3, now=later, params=params
        )
        self.assertAlmostEqual(rating.traits[communication.pk], recent_only.rate)

    def test_inactive_trait_excluded_from_overall(self) -> None:
        self.run_snapshot()
        for mate in self.mates_a:
            self.review(mate, self.cap_a, {**scores(5), "communication": 1})
        later = tz.now() + AFTER_WINDOW
        before = self.board(later)[self.ou(self.cap_a).pk]
        CaptainTrait.objects.filter(organization=self.org, key="communication").update(
            active=False
        )
        after = self.board(later)[self.ou(self.cap_a).pk]
        communication = CaptainTrait.objects.get(
            organization=self.org, key="communication"
        )
        self.assertNotIn(communication.pk, after.traits)
        self.assertEqual(len(after.traits), 3)
        self.assertAlmostEqual(
            after.overall, sum(after.traits.values()) / len(after.traits)
        )
        self.assertGreater(after.overall, before.overall)


@override_settings(CACHEOPS_ENABLED=False)
class LeadershipQueryBudgetTest(LeadershipTestCase):
    def seed(self, captains: int) -> None:
        event, tournament = self.make_event(f"Budget {captains}")
        pairs: list[tuple[CustomUser, list[CustomUser]]] = []
        for i in range(captains):
            cap = self.make_user(f"bq{captains}_c{i}")
            mates = [self.make_user(f"bq{captains}_c{i}_m{j}") for j in range(2)]
            self.make_team(f"T{captains}-{i}", cap, mates, tournament=tournament)
            for user in [cap, *mates]:
                self.admit(user, event)
            pairs.append((cap, mates))
        self.run_snapshot(event)
        for cap, mates in pairs:
            for mate in mates:
                self.review(mate, cap, event=event)

    def board_queries(self, expected_captains: int) -> int:
        settings = get_leadership_settings(self.org)
        traits = effective_traits(self.org)
        later = tz.now() + AFTER_WINDOW
        with CaptureQueriesContext(connection) as ctx:
            result = rating_board(
                self.org.pk, now=later, settings=settings, traits=traits
            )
        self.assertEqual(len(result), expected_captains)
        return len(ctx.captured_queries)

    def test_rating_board_one_query(self) -> None:
        self.seed(3)
        self.assertEqual(self.board_queries(3), 1)
        self.seed(10)
        self.assertEqual(self.board_queries(13), 1)

    def test_captain_events_at_most_three_queries(self) -> None:
        self.run_snapshot()
        for mate in self.mates_a:
            self.review(mate, self.cap_a)
        captain = self.ou(self.cap_a)
        settings = get_leadership_settings(self.org)
        traits = effective_traits(self.org)
        later = tz.now() + AFTER_WINDOW
        with CaptureQueriesContext(connection) as ctx:
            rows = captain_events(
                captain, now=later, settings=settings, traits=traits, staff=True
            )
        self.assertEqual(len(rows), 1)
        self.assertLessEqual(len(ctx.captured_queries), 3)
