from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Literal

from django.test import SimpleTestCase, override_settings
from django.utils import timezone as tz

from org.conduct.constants import Outcome, Tier
from org.conduct.enforcement import (
    defer_back_of_line,
    tier_for,
    tier_for_score,
    tiers_for,
)
from org.conduct.gate import GATE_OFF, ConductGate
from org.conduct.scoring import MemberScore
from org.models_conduct import OrgConductSettings
from org.tests.conduct_base import ConductTestCase


def _score(rate: float, status: Literal["new", "scored"] = "scored") -> MemberScore:
    return MemberScore(
        show_rate=rate, status=status, counted_events=5, weighted_events=5.0
    )


@override_settings(CACHEOPS_ENABLED=False)
class TierTest(ConductTestCase):
    def all_modes(self, **overrides: object) -> OrgConductSettings:
        fields: dict[str, object] = {
            "organization": self.org,
            "back_of_line_enabled": True,
            "back_of_line_below": Decimal("0.75"),
            "require_approval_enabled": True,
            "require_approval_below": Decimal("0.65"),
            "block_enabled": True,
            "block_below": Decimal("0.40"),
        }
        fields.update(overrides)
        return OrgConductSettings(**fields)

    def active_gate(self, settings: OrgConductSettings) -> ConductGate:
        return ConductGate(
            org_id=self.org.pk,
            feature_on=True,
            settings=settings,
            enforcement_active=True,
        )

    def test_off_gate_zero_queries(self) -> None:
        with self.assertNumQueries(0):
            self.assertEqual(tier_for(GATE_OFF, self.user), Tier.OK)
            self.assertEqual(
                tiers_for(GATE_OFF, [self.user, self.admin]),
                {self.user.pk: Tier.OK, self.admin.pk: Tier.OK},
            )

    def test_feature_on_without_modes_zero_queries(self) -> None:
        gate = ConductGate(
            org_id=self.org.pk,
            feature_on=True,
            settings=OrgConductSettings(organization=self.org),
            enforcement_active=False,
        )
        with self.assertNumQueries(0):
            self.assertEqual(tier_for(gate, self.user), Tier.OK)

    def test_strictest_tier_wins(self) -> None:
        settings = self.all_modes()
        self.assertEqual(tier_for_score(_score(0.3), settings), Tier.BLOCK)
        self.assertEqual(tier_for_score(_score(0.5), settings), Tier.REQUIRE_APPROVAL)
        self.assertEqual(tier_for_score(_score(0.7), settings), Tier.BACK_OF_LINE)
        self.assertEqual(tier_for_score(_score(0.8), settings), Tier.OK)

    def test_threshold_is_strictly_below(self) -> None:
        settings = self.all_modes()
        self.assertEqual(tier_for_score(_score(0.75), settings), Tier.OK)
        self.assertEqual(tier_for_score(_score(0.40), settings), Tier.REQUIRE_APPROVAL)

    def test_disabled_modes_skipped(self) -> None:
        settings = self.all_modes(block_enabled=False)
        self.assertEqual(tier_for_score(_score(0.3), settings), Tier.REQUIRE_APPROVAL)
        settings = self.all_modes(block_enabled=False, require_approval_enabled=False)
        self.assertEqual(tier_for_score(_score(0.3), settings), Tier.BACK_OF_LINE)

    def test_new_member_exempt_unless_configured(self) -> None:
        settings = self.all_modes()
        self.assertEqual(tier_for_score(_score(0.1, "new"), settings), Tier.OK)
        settings = self.all_modes(enforce_on_new_members=True)
        self.assertEqual(tier_for_score(_score(0.1, "new"), settings), Tier.BLOCK)

    def test_tier_for_scores_member(self) -> None:
        now = tz.now()
        for days in (1, 2, 3, 4):
            self.outcome(
                self.user,
                outcome=Outcome.NO_SHOW,
                starts_at=now - timedelta(days=days),
            )
        gate = self.active_gate(self.all_modes())

        with self.assertNumQueries(1):
            self.assertEqual(tier_for(gate, self.user), Tier.BLOCK)

    def test_tiers_for_single_query(self) -> None:
        now = tz.now()
        for days in (1, 2, 3, 4):
            self.outcome(
                self.user,
                outcome=Outcome.NO_SHOW,
                starts_at=now - timedelta(days=days),
            )
            self.outcome(self.admin, starts_at=now - timedelta(days=days))
        gate = self.active_gate(self.all_modes())

        with self.assertNumQueries(1):
            tiers = tiers_for(gate, [self.user, self.admin, self.league_staff])

        self.assertEqual(
            tiers,
            {
                self.user.pk: Tier.BLOCK,
                self.admin.pk: Tier.OK,
                self.league_staff.pk: Tier.OK,
            },
        )


@dataclass(frozen=True)
class _Candidate:
    name: str
    user_id: int


class DeferTest(SimpleTestCase):
    def test_stable_partition(self) -> None:
        a, b, c, d = (_Candidate(n, i) for i, n in enumerate("abcd", start=1))
        tiers = {1: Tier.OK, 2: Tier.BACK_OF_LINE, 3: Tier.OK, 4: Tier.BLOCK}

        self.assertEqual(defer_back_of_line([a, b, c, d], tiers), [a, c, b, d])

    def test_missing_tier_counts_as_ok(self) -> None:
        a, b = _Candidate("a", 1), _Candidate("b", 2)

        self.assertEqual(defer_back_of_line([a, b], {1: Tier.REQUIRE_APPROVAL}), [b, a])

    def test_defer_empty(self) -> None:
        self.assertEqual(defer_back_of_line([], {}), [])
