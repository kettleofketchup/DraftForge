"""Unit tests for events.mmr_suggestions.suggest_mmr."""
from types import SimpleNamespace

import pytest

from events.mmr_suggestions import suggest_mmr


def make_profile(rank_status="active", rank_medal="", mmr=None, battle_cup_tier=None):
    """Build a duck-typed stand-in for PlayerDotaProfile."""
    return SimpleNamespace(
        rank_status=rank_status,
        rank_medal=rank_medal,
        mmr=mmr,
        battle_cup_tier=battle_cup_tier,
    )


# ---------- precedence: default value --------------------------------------

def test_self_report_wins_over_prior():
    """Player just told us a number — trust it as the autofill anchor."""
    profile = make_profile(rank_medal="Legend 3", mmr=3500)
    result = suggest_mmr(profile, prior_approved_mmr=2400)
    assert result["default"] == 3500
    assert result["default_source"] == "self_report"
    assert result["range"] == [3388, 3542]
    assert result["range_source"] == "medal"


def test_prior_wins_when_no_self_report():
    profile = make_profile(rank_medal="Legend 3", mmr=None)
    result = suggest_mmr(profile, prior_approved_mmr=2400)
    assert result["default"] == 2400
    assert result["default_source"] == "prior"
    assert result["range"] == [3388, 3542]


def test_medal_midpoint_when_no_prior_no_self_report():
    profile = make_profile(rank_medal="Crusader 1", mmr=None)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    # Crusader 1: (1540, 1694) → midpoint 1617
    assert result["default"] == 1617
    assert result["default_source"] == "medal"
    assert result["range"] == [1540, 1694]


def test_battle_cup_midpoint_for_never_ranked():
    profile = make_profile(
        rank_status="never", rank_medal="", battle_cup_tier=5
    )
    result = suggest_mmr(profile, prior_approved_mmr=None)
    # BC tier 5: (3000, 4000) → midpoint 3500
    assert result["default"] == 3500
    assert result["default_source"] == "battle_cup"
    assert result["range"] == [3000, 4000]
    assert result["range_source"] == "battle_cup"


def test_fallback_when_no_profile():
    result = suggest_mmr(profile=None, prior_approved_mmr=None)
    assert result["default"] == 1000  # midpoint of (0, 2000)
    assert result["default_source"] == "fallback"
    assert result["range"] == [0, 2000]
    assert result["range_source"] == "fallback"


def test_fallback_when_profile_has_no_signals():
    profile = make_profile(rank_status="never", rank_medal="", battle_cup_tier=None)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    assert result["default_source"] == "fallback"
    assert result["range_source"] == "fallback"


def test_previous_rank_uses_medal_range():
    profile = make_profile(rank_status="previous", rank_medal="Divine 2", mmr=None)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    # Divine 2 per-star: (4780, 4940) → midpoint 4860
    assert result["default"] == 4860
    assert result["default_source"] == "medal"
    assert result["range"] == [4780, 4940]
    assert result["range_source"] == "medal"


def test_prior_zero_is_treated_as_present():
    """org_user.mmr=0 is not None, so prior is selected when no self-report."""
    profile = make_profile(rank_medal="Legend 3", mmr=None)
    result = suggest_mmr(profile, prior_approved_mmr=0)
    assert result["default"] == 0
    assert result["default_source"] == "prior"


# ---------- parametric coverage --------------------------------------------

@pytest.mark.parametrize(
    "medal,expected_low,expected_high",
    [
        ("Herald 1",   0,    154),
        ("Herald 5",   616,  770),
        ("Guardian 1", 770,  924),
        ("Guardian 5", 1386, 1540),
        ("Crusader 3", 1848, 2002),
        ("Archon 2",   2464, 2618),
        ("Legend 4",   3542, 3696),
        ("Ancient 1",  3850, 4004),
        ("Ancient 5",  4466, 4620),
        ("Divine 2",   4780, 4940),
        ("Immortal",   5420, 8000),
    ],
)
def test_all_medals_match_settings_range(medal, expected_low, expected_high):
    profile = make_profile(rank_medal=medal)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    assert result["range"] == [expected_low, expected_high]
    assert result["range_source"] == "medal"


@pytest.mark.parametrize(
    "tier,expected_low,expected_high",
    [
        (1, 0,    500),
        (2, 500,  1000),
        (3, 1000, 2000),
        (4, 2000, 3000),
        (5, 3000, 4000),
        (6, 4000, 5000),
        (7, 5000, 6000),
        (8, 6000, 8000),
    ],
)
def test_all_battle_cup_tiers_match_settings_range(tier, expected_low, expected_high):
    profile = make_profile(rank_status="never", rank_medal="", battle_cup_tier=tier)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    assert result["range"] == [expected_low, expected_high]
    assert result["range_source"] == "battle_cup"
