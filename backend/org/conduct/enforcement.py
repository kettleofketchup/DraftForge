from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from django.utils import timezone as tz

from app.models import CustomUser
from org.conduct.constants import Tier
from org.conduct.gate import ConductGate
from org.conduct.queries import user_scores
from org.conduct.scoring import MemberScore
from org.models_conduct import OrgConductSettings


class HasUserId(Protocol):
    @property
    def user_id(self) -> int: ...


@dataclass(frozen=True)
class Standing:
    tier: Tier
    deferred: bool


STANDING_OK = Standing(tier=Tier.OK, deferred=False)


def _exempt(score: MemberScore, settings: OrgConductSettings) -> bool:
    return score.status == "new" and not settings.enforce_on_new_members


def tier_for_score(score: MemberScore, settings: OrgConductSettings) -> Tier:
    if _exempt(score, settings):
        return Tier.OK
    rate = score.show_rate
    if settings.block_enabled and rate < float(settings.block_below):
        return Tier.BLOCK
    if settings.require_approval_enabled and rate < float(
        settings.require_approval_below
    ):
        return Tier.REQUIRE_APPROVAL
    if settings.back_of_line_enabled and rate < float(settings.back_of_line_below):
        return Tier.BACK_OF_LINE
    return Tier.OK


def is_deferred(score: MemberScore, settings: OrgConductSettings) -> bool:
    """Back of line uses its own threshold, not the strictest tier."""
    return (
        settings.back_of_line_enabled
        and not _exempt(score, settings)
        and score.show_rate < float(settings.back_of_line_below)
    )


def standing_for_score(score: MemberScore, settings: OrgConductSettings) -> Standing:
    return Standing(
        tier=tier_for_score(score, settings), deferred=is_deferred(score, settings)
    )


def standings_for(
    gate: ConductGate, users: Iterable[CustomUser]
) -> dict[int, Standing]:
    user_ids = [user.pk for user in users]
    settings = gate.settings
    if not gate.enforcement_active or settings is None or gate.org_id is None:
        return dict.fromkeys(user_ids, STANDING_OK)
    scores = user_scores(gate.org_id, user_ids, now=tz.now(), settings=settings)
    return {
        user_id: standing_for_score(score, settings)
        for user_id, score in scores.items()
    }


def tiers_for(gate: ConductGate, users: Iterable[CustomUser]) -> dict[int, Tier]:
    return {
        user_id: standing.tier
        for user_id, standing in standings_for(gate, users).items()
    }


def tier_for(gate: ConductGate, user: CustomUser) -> Tier:
    return tiers_for(gate, [user])[user.pk]


def defer_back_of_line[T: HasUserId](
    candidates: Sequence[T], deferred: Collection[int]
) -> list[T]:
    ahead = [c for c in candidates if c.user_id not in deferred]
    behind = [c for c in candidates if c.user_id in deferred]
    return ahead + behind
