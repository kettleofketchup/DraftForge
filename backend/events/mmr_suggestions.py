"""MMR suggestion logic for the EventSignup approval modal.

Pure functions — no DB access, no Django-model imports. Caller passes a
duck-typed `profile` (the relevant fields of PlayerDotaProfile) and the
`prior_approved_mmr` (OrgUser.mmr, or None).

Settings constants:
    DOTA_MEDAL_MMR_RANGES        — medal name → (low, high)
    DOTA_BATTLE_CUP_MMR_RANGES   — tier (1-8) → (low, high)
    DOTA_DEFAULT_MMR_RANGE       — fallback (low, high)
"""
from typing import Optional

from django.conf import settings


def suggest_mmr(profile, prior_approved_mmr: Optional[int]) -> dict:
    """Compute the values the approval modal needs.

    Returns:
        {
            "default": int,         # form pre-fill
            "default_source": str,  # "prior" | "self_report" | "medal" | "battle_cup" | "fallback"
            "range": [low, high],   # always shown as helper text
            "range_source": str,    # "medal" | "battle_cup" | "fallback"
        }
    """
    range_low, range_high, range_source = _compute_range(profile)

    if prior_approved_mmr is not None:
        default, default_source = prior_approved_mmr, "prior"
    elif profile is not None and profile.mmr is not None:
        default, default_source = profile.mmr, "self_report"
    else:
        default, default_source = (range_low + range_high) // 2, range_source

    return {
        "default": default,
        "default_source": default_source,
        "range": [range_low, range_high],
        "range_source": range_source,
    }


def _compute_range(profile) -> tuple[int, int, str]:
    if profile is not None and profile.rank_medal:
        medal_name, _star = _parse_medal(profile.rank_medal)
        ranges = settings.DOTA_MEDAL_MMR_RANGES
        if medal_name in ranges:
            low, high = ranges[medal_name]
            return low, high, "medal"

    if (
        profile is not None
        and profile.rank_status == "never"
        and profile.battle_cup_tier
    ):
        ranges = settings.DOTA_BATTLE_CUP_MMR_RANGES
        if profile.battle_cup_tier in ranges:
            low, high = ranges[profile.battle_cup_tier]
            return low, high, "battle_cup"

    low, high = settings.DOTA_DEFAULT_MMR_RANGE
    return low, high, "fallback"


def _parse_medal(medal: str) -> tuple[str, int]:
    """'Crusader 3' → ('Crusader', 3); 'Immortal' → ('Immortal', 1)."""
    parts = medal.strip().split(" ", 1)
    name = parts[0]
    star = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    return name, star
