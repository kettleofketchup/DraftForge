from __future__ import annotations

from enum import StrEnum

from app.models import CustomUser, GameType
from events.eligibility.steam import (
    STEAM_ACCOUNT_ID_RANGE,
    STORED_STEAM_ACCOUNT_ID_MAX,
    steam_friend_id_from_profiles,
)
from events.models import Event
from org.models import OrgUser


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
        or event.discord_require_previous_rank_screenshot
    ):
        metrics.add(GatedMetric.MMR)
    if event.discord_require_battlecup_screenshot:
        metrics.add(GatedMetric.BATTLE_CUP)
    return frozenset(metrics)


def is_skill_gated(event: Event) -> bool:
    return bool(gated_metrics(event))


def has_registered_steam_id(user: CustomUser, org_user: OrgUser | None) -> bool:
    """The single Steam ID definition: a linked Steam account, or a numeric
    friend ID on either game profile that no other user owns as
    ``steam_account_id``."""
    if user.steamid:
        return True
    fid = steam_friend_id_from_profiles(org_user)
    if not fid:
        return False
    account_id = int(fid)
    if account_id not in STEAM_ACCOUNT_ID_RANGE:
        return False
    if account_id > STORED_STEAM_ACCOUNT_ID_MAX:
        return True
    return (
        not CustomUser.objects.filter(steam_account_id=account_id)
        .exclude(pk=user.pk)
        .exists()
    )
