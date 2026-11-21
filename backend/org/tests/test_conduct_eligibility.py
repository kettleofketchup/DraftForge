from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as tz

from org.conduct.constants import Outcome, Tier
from org.conduct.eligibility import conduct_tier, gate_for, prime, standings
from org.conduct.enforcement import STANDING_OK
from org.conduct.gate import conduct_gate
from org.models_conduct import OrgConductSettings
from org.standing.cache import StandingCache
from org.tests.conduct_base import ConductTestCase

OUTCOME_TABLE = "org_attendanceoutcome"


@override_settings(CACHEOPS_ENABLED=False)
class ConductEligibilityTest(ConductTestCase):
    def setUp(self) -> None:
        self.now = tz.now()

    def enforce(self) -> None:
        self.unlock()
        OrgConductSettings.objects.update_or_create(
            organization=self.org,
            defaults={"require_approval_enabled": True, "block_enabled": True},
        )

    def no_shows(self, count: int) -> None:
        for days in range(1, count + 1):
            self.outcome(
                self.user,
                outcome=Outcome.NO_SHOW,
                starts_at=self.now - timedelta(days=days),
            )

    def test_gate_built_once_per_cache(self) -> None:
        cache = StandingCache()
        with patch("org.conduct.eligibility.conduct_gate", wraps=conduct_gate) as built:
            first = gate_for(self.org.pk, cache)
            second = gate_for(self.org.pk, cache)
        self.assertIs(first, second)
        built.assert_called_once_with(self.org.pk)

    def test_standings_one_query_for_many_users(self) -> None:
        self.enforce()
        cache = StandingCache()
        gate_for(self.org.pk, cache)
        ids = [self.user.pk, self.admin.pk, self.league_staff.pk]
        with self.assertNumQueries(1):
            found = standings(self.org.pk, ids, now=self.now, cache=cache)
        self.assertEqual(set(found), set(ids))

    def test_second_call_scores_only_missing_ids(self) -> None:
        self.enforce()
        cache = StandingCache()
        gate_for(self.org.pk, cache)
        standings(self.org.pk, [self.user.pk], now=self.now, cache=cache)

        with CaptureQueriesContext(connection) as ctx:
            found = standings(
                self.org.pk, [self.user.pk, self.admin.pk], now=self.now, cache=cache
            )
        self.assertEqual(len(ctx.captured_queries), 1)
        self.assertIn(str(self.admin.pk), ctx.captured_queries[0]["sql"])
        self.assertEqual(set(found), {self.user.pk, self.admin.pk})

        with self.assertNumQueries(0):
            standings(
                self.org.pk, [self.user.pk, self.admin.pk], now=self.now, cache=cache
            )

    def test_inactive_gate_zero_scoring_queries(self) -> None:
        cache = StandingCache()
        with CaptureQueriesContext(connection) as ctx:
            prime(cache, self.org.pk, [self.user.pk, self.admin.pk], now=self.now)
        self.assertFalse(any(OUTCOME_TABLE in q["sql"] for q in ctx.captured_queries))
        self.assertEqual(
            standings(self.org.pk, [self.user.pk], now=self.now, cache=cache),
            {self.user.pk: STANDING_OK},
        )

    def test_works_without_a_cache(self) -> None:
        self.assertIs(gate_for(self.org.pk, None).enforcement_active, False)
        self.assertEqual(
            standings(self.org.pk, [self.user.pk], now=self.now, cache=None),
            {self.user.pk: STANDING_OK},
        )

    def test_conduct_tier_strictest(self) -> None:
        self.enforce()
        self.no_shows(4)
        tier = conduct_tier(
            self.org.pk, self.org_user(self.user), now=self.now, cache=None
        )
        self.assertIs(tier, Tier.BLOCK)
