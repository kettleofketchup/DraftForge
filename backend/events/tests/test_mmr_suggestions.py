"""Unit tests for events.mmr_suggestions.suggest_mmr."""
from types import SimpleNamespace

import pytest

from events.mmr_suggestions import suggest_mmr, _parse_medal


def make_profile(rank_status="active", rank_medal="", mmr=None, battle_cup_tier=None):
    """Build a duck-typed stand-in for PlayerDotaProfile."""
    return SimpleNamespace(
        rank_status=rank_status,
        rank_medal=rank_medal,
        mmr=mmr,
        battle_cup_tier=battle_cup_tier,
    )


# ---------- _parse_medal ----------------------------------------------------

def test_parse_medal_with_star():
    assert _parse_medal("Crusader 3") == ("Crusader", 3)


def test_parse_medal_immortal_no_star():
    assert _parse_medal("Immortal") == ("Immortal", 1)


def test_parse_medal_strips_whitespace():
    assert _parse_medal("  Legend 5  ") == ("Legend", 5)


def test_parse_medal_garbage_falls_back_to_star_1():
    assert _parse_medal("Legend nope") == ("Legend", 1)


# ---------- precedence: default value --------------------------------------

def test_prior_approved_wins_over_everything():
    profile = make_profile(rank_medal="Legend 3", mmr=3200)
    result = suggest_mmr(profile, prior_approved_mmr=2400)
    assert result["default"] == 2400
    assert result["default_source"] == "prior"
    assert result["range"] == [3080, 3850]
    assert result["range_source"] == "medal"


def test_self_report_wins_when_no_prior():
    profile = make_profile(rank_medal="Legend 3", mmr=3200)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    assert result["default"] == 3200
    assert result["default_source"] == "self_report"
    assert result["range"] == [3080, 3850]


def test_medal_midpoint_when_no_prior_no_self_report():
    profile = make_profile(rank_medal="Crusader 1", mmr=None)
    result = suggest_mmr(profile, prior_approved_mmr=None)
    # Crusader range: (1540, 2310) → midpoint 1925
    assert result["default"] == 1925
    assert result["default_source"] == "medal"
    assert result["range"] == [1540, 2310]


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
    # Divine range: (4620, 5420) → midpoint 5020
    assert result["default"] == 5020
    assert result["default_source"] == "medal"
    assert result["range"] == [4620, 5420]
    assert result["range_source"] == "medal"


def test_prior_zero_is_treated_as_present():
    """org_user.mmr=0 is not None, so prior takes precedence."""
    profile = make_profile(rank_medal="Legend 3", mmr=3200)
    # Note: get_org_user_mmr nulls out zero MMR before passing in, so this
    # path verifies the function's contract — caller must pre-filter zero
    # if they want it to behave as "absent".
    result = suggest_mmr(profile, prior_approved_mmr=0)
    assert result["default"] == 0
    assert result["default_source"] == "prior"


# ---------- parametric coverage --------------------------------------------

@pytest.mark.parametrize(
    "medal,expected_low,expected_high",
    [
        ("Herald 1",   0,    770),
        ("Guardian 5", 770,  1540),
        ("Crusader 3", 1540, 2310),
        ("Archon 2",   2310, 3080),
        ("Legend 4",   3080, 3850),
        ("Ancient 1",  3850, 4620),
        ("Divine 2",   4620, 5420),
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
