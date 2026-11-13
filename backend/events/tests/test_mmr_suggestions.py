"""Unit tests for events.mmr_suggestions.suggest_mmr."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from events.mmr_suggestions import suggest_mmr


def make_profile(
    rank_status: str = "active",
    rank_medal: str = "",
    mmr: int | None = None,
    battle_cup_tier: int | None = None,
) -> SimpleNamespace:
    """Build a duck-typed stand-in for PlayerDotaProfile."""
    return SimpleNamespace(
        rank_status=rank_status,
        rank_medal=rank_medal,
        mmr=mmr,
        battle_cup_tier=battle_cup_tier,
    )


class SuggestMmrPrecedenceTest(SimpleTestCase):
    def test_self_report_wins_over_prior(self) -> None:
        """Player just told us a number — trust it as the autofill anchor."""
        profile = make_profile(rank_medal="Legend 3", mmr=3500)
        result = suggest_mmr(profile, prior_approved_mmr=2400)
        self.assertEqual(result["default"], 3500)
        self.assertEqual(result["default_source"], "self_report")
        self.assertEqual(result["range"], [3388, 3542])
        self.assertEqual(result["range_source"], "medal")

    def test_prior_wins_when_no_self_report(self) -> None:
        profile = make_profile(rank_medal="Legend 3", mmr=None)
        result = suggest_mmr(profile, prior_approved_mmr=2400)
        self.assertEqual(result["default"], 2400)
        self.assertEqual(result["default_source"], "prior")
        self.assertEqual(result["range"], [3388, 3542])

    def test_medal_midpoint_when_no_prior_no_self_report(self) -> None:
        profile = make_profile(rank_medal="Crusader 1", mmr=None)
        result = suggest_mmr(profile, prior_approved_mmr=None)
        # Crusader 1: (1540, 1694) → midpoint 1617
        self.assertEqual(result["default"], 1617)
        self.assertEqual(result["default_source"], "medal")
        self.assertEqual(result["range"], [1540, 1694])

    def test_battle_cup_midpoint_for_never_ranked(self) -> None:
        profile = make_profile(rank_status="never", rank_medal="", battle_cup_tier=5)
        result = suggest_mmr(profile, prior_approved_mmr=None)
        # BC tier 5: (3000, 4000) → midpoint 3500
        self.assertEqual(result["default"], 3500)
        self.assertEqual(result["default_source"], "battle_cup")
        self.assertEqual(result["range"], [3000, 4000])
        self.assertEqual(result["range_source"], "battle_cup")

    def test_fallback_when_no_profile(self) -> None:
        result = suggest_mmr(profile=None, prior_approved_mmr=None)
        self.assertEqual(result["default"], 1000)  # midpoint of (0, 2000)
        self.assertEqual(result["default_source"], "fallback")
        self.assertEqual(result["range"], [0, 2000])
        self.assertEqual(result["range_source"], "fallback")

    def test_fallback_when_profile_has_no_signals(self) -> None:
        profile = make_profile(rank_status="never", rank_medal="", battle_cup_tier=None)
        result = suggest_mmr(profile, prior_approved_mmr=None)
        self.assertEqual(result["default_source"], "fallback")
        self.assertEqual(result["range_source"], "fallback")

    def test_previous_rank_uses_medal_range(self) -> None:
        profile = make_profile(rank_status="previous", rank_medal="Divine 2", mmr=None)
        result = suggest_mmr(profile, prior_approved_mmr=None)
        # Divine 2 per-star: (4780, 4940) → midpoint 4860
        self.assertEqual(result["default"], 4860)
        self.assertEqual(result["default_source"], "medal")
        self.assertEqual(result["range"], [4780, 4940])
        self.assertEqual(result["range_source"], "medal")

    def test_prior_zero_is_treated_as_present(self) -> None:
        """org_user.mmr=0 is not None, so prior is selected when no self-report."""
        profile = make_profile(rank_medal="Legend 3", mmr=None)
        result = suggest_mmr(profile, prior_approved_mmr=0)
        self.assertEqual(result["default"], 0)
        self.assertEqual(result["default_source"], "prior")


MEDAL_RANGES: list[tuple[str, int, int]] = [
    ("Herald 1", 0, 154),
    ("Herald 5", 616, 770),
    ("Guardian 1", 770, 924),
    ("Guardian 5", 1386, 1540),
    ("Crusader 3", 1848, 2002),
    ("Archon 2", 2464, 2618),
    ("Legend 4", 3542, 3696),
    ("Ancient 1", 3850, 4004),
    ("Ancient 5", 4466, 4620),
    ("Divine 2", 4780, 4940),
    ("Immortal", 5420, 8000),
]

BATTLE_CUP_RANGES: list[tuple[int, int, int]] = [
    (1, 0, 500),
    (2, 500, 1000),
    (3, 1000, 2000),
    (4, 2000, 3000),
    (5, 3000, 4000),
    (6, 4000, 5000),
    (7, 5000, 6000),
    (8, 6000, 8000),
]


class SuggestMmrRangeTableTest(SimpleTestCase):
    def test_all_medals_match_settings_range(self) -> None:
        for medal, expected_low, expected_high in MEDAL_RANGES:
            with self.subTest(medal=medal):
                result = suggest_mmr(make_profile(rank_medal=medal), prior_approved_mmr=None)
                self.assertEqual(result["range"], [expected_low, expected_high])
                self.assertEqual(result["range_source"], "medal")

    def test_all_battle_cup_tiers_match_settings_range(self) -> None:
        for tier, expected_low, expected_high in BATTLE_CUP_RANGES:
            with self.subTest(tier=tier):
                profile = make_profile(rank_status="never", rank_medal="", battle_cup_tier=tier)
                result = suggest_mmr(profile, prior_approved_mmr=None)
                self.assertEqual(result["range"], [expected_low, expected_high])
                self.assertEqual(result["range_source"], "battle_cup")
