from collections.abc import Iterable, Mapping, Sequence
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


def tier_for_score(score: MemberScore, settings: OrgConductSettings) -> Tier:
    if score.status == "new" and not settings.enforce_on_new_members:
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


def tiers_for(gate: ConductGate, users: Iterable[CustomUser]) -> dict[int, Tier]:
    user_ids = [user.pk for user in users]
    settings = gate.settings
    if not gate.enforcement_active or settings is None or gate.org_id is None:
        return dict.fromkeys(user_ids, Tier.OK)
    scores = user_scores(gate.org_id, user_ids, now=tz.now(), settings=settings)
    return {
        user_id: tier_for_score(score, settings) for user_id, score in scores.items()
    }


def tier_for(gate: ConductGate, user: CustomUser) -> Tier:
    return tiers_for(gate, [user])[user.pk]


def defer_back_of_line[T: HasUserId](
    candidates: Sequence[T], tiers: Mapping[int, Tier]
) -> list[T]:
    ahead = [c for c in candidates if tiers.get(c.user_id, Tier.OK) == Tier.OK]
    behind = [c for c in candidates if tiers.get(c.user_id, Tier.OK) != Tier.OK]
    return ahead + behind
