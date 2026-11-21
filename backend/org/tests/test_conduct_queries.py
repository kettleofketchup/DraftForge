from datetime import timedelta

from django.test import override_settings
from django.utils import timezone as tz

from app.models import CustomUser, Organization
from org.conduct.constants import Outcome
from org.conduct.queries import member_scores, user_scores
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome, OrgConductSettings
from org.tests.conduct_base import ConductTestCase


@override_settings(CACHEOPS_ENABLED=False)
class ConductQueriesTest(ConductTestCase):
    def setUp(self) -> None:
        self.now = tz.now()
        self.settings = OrgConductSettings(organization=self.org)

    def test_member_scores_single_query(self) -> None:
        members = [self.admin, self.user, self.league_staff]
        for user in members:
            self.outcome(user, starts_at=self.now - timedelta(days=1))
        self.outcome(
            self.user,
            outcome=Outcome.NO_SHOW,
            starts_at=self.now - timedelta(days=2),
        )

        with self.assertNumQueries(1):
            scores = member_scores(
                self.org.pk, None, now=self.now, settings=self.settings
            )

        self.assertEqual(set(scores), {self.org_user(u).pk for u in members})
        self.assertEqual(scores[self.org_user(self.user).pk].counted_events, 2)

    def test_member_scores_filters_by_org_user_ids(self) -> None:
        self.outcome(self.admin, starts_at=self.now - timedelta(days=1))
        self.outcome(self.user, starts_at=self.now - timedelta(days=1))
        wanted = self.org_user(self.user).pk

        scores = member_scores(
            self.org.pk, [wanted], now=self.now, settings=self.settings
        )

        self.assertEqual(set(scores), {wanted})

    def test_member_scores_respects_counted_and_org(self) -> None:
        self.outcome(
            self.user,
            outcome=Outcome.ATTENDED,
            committed=False,
            starts_at=self.now - timedelta(days=1),
        )
        self.outcome(
            self.user,
            outcome=Outcome.NO_SHOW,
            voided_at=self.now,
            starts_at=self.now - timedelta(days=1),
        )
        other_org = Organization.objects.create(name="Other Org", owner=self.admin)
        other_org_user = OrgUser.objects.create(
            user=self.unrelated_user, organization=other_org
        )
        AttendanceOutcome.objects.create(
            organization=other_org,
            org_user=other_org_user,
            event_name="Elsewhere",
            event_starts_at=self.now - timedelta(days=1),
            outcome=Outcome.NO_SHOW,
            finalized_at=self.now,
        )

        scores = member_scores(self.org.pk, None, now=self.now, settings=self.settings)

        self.assertEqual(scores, {})

    def test_member_scores_max_age(self) -> None:
        self.outcome(
            self.user,
            outcome=Outcome.NO_SHOW,
            starts_at=self.now - timedelta(days=366),
        )

        scores = member_scores(self.org.pk, None, now=self.now, settings=self.settings)

        self.assertEqual(scores, {})

    def test_user_scores_fills_prior(self) -> None:
        self.outcome(
            self.user,
            outcome=Outcome.NO_SHOW,
            starts_at=self.now - timedelta(days=1),
        )
        stranger = CustomUser.objects.create_user(
            username="conduct_stranger", password="x"
        )

        with self.assertNumQueries(1):
            scores = user_scores(
                self.org.pk,
                [self.user.pk, stranger.pk],
                now=self.now,
                settings=self.settings,
            )

        self.assertEqual(set(scores), {self.user.pk, stranger.pk})
        self.assertEqual(scores[stranger.pk].show_rate, 0.85)
        self.assertEqual(scores[stranger.pk].status, "new")
        self.assertEqual(scores[stranger.pk].counted_events, 0)
        self.assertEqual(scores[self.user.pk].counted_events, 1)
        self.assertLess(scores[self.user.pk].show_rate, 0.85)

    def test_user_scores_empty_ids_no_query(self) -> None:
        with self.assertNumQueries(0):
            scores = user_scores(self.org.pk, [], now=self.now, settings=self.settings)
        self.assertEqual(scores, {})
