from __future__ import annotations

from enum import StrEnum

from app.models import CustomUser, GameType
from events.models import Event


class GatedMetric(StrEnum):
    MMR = "mmr"
    BATTLE_CUP = "battle_cup"


def gated_metrics(event: Event) -> frozenset[GatedMetric]:
    """Skill metrics the event's settings gate on."""
    if event.game_type != GameType.DOTA2:
        return frozenset()
    metrics: set[GatedMetric] = set()
    if (
        event.require_mmr_verified
        or event.min_mmr
        or event.discord_require_rank_screenshot
    ):
        metrics.add(GatedMetric.MMR)
    if event.discord_require_battlecup_screenshot:
        metrics.add(GatedMetric.BATTLE_CUP)
    return frozenset(metrics)


def is_skill_gated(event: Event) -> bool:
    return bool(gated_metrics(event))


def has_registered_steam_id(user: CustomUser) -> bool:
    """The single Steam ID definition: the user's stored Friend ID."""
    return user.steam_account_id is not None or user.steamid is not None
