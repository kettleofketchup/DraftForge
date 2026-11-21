from collections.abc import Collection
from datetime import datetime

from org.conduct.constants import CONDUCT_BLOCK_MESSAGE, Tier
from org.conduct.enforcement import ConductStanding, standings_for
from org.conduct.gate import ConductGate, conduct_gate
from org.models import OrgUser
from org.standing.cache import StandingCache, memo

__all__ = [
    "CONDUCT_BLOCK_MESSAGE",
    "Tier",
    "conduct_tier",
    "gate_for",
    "prime",
    "standings",
]


def gate_for(org_id: int, cache: StandingCache | None) -> ConductGate:
    if cache is None:
        return conduct_gate(org_id)
    return memo(cache, "conduct", f"gate:{org_id}", lambda: conduct_gate(org_id))


def standings(
    org_id: int,
    user_ids: Collection[int],
    *,
    now: datetime,
    cache: StandingCache | None,
) -> dict[int, ConductStanding]:
    cache = cache or StandingCache()
    ids = list(dict.fromkeys(user_ids))
    known: dict[int, ConductStanding] = memo(
        cache, "conduct", f"standings:{org_id}", dict
    )
    missing = [user_id for user_id in ids if user_id not in known]
    if missing:
        known.update(standings_for(gate_for(org_id, cache), missing, now=now))
    return {user_id: known[user_id] for user_id in ids}


def prime(
    cache: StandingCache, org_id: int, user_ids: Collection[int], *, now: datetime
) -> None:
    standings(org_id, user_ids, now=now, cache=cache)


def conduct_tier(
    org_id: int,
    org_user: OrgUser,
    *,
    now: datetime,
    cache: StandingCache | None,
) -> Tier:
    found = standings(org_id, [org_user.user_id], now=now, cache=cache)
    return found[org_user.user_id].tier
