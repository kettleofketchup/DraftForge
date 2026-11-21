from __future__ import annotations

import datetime
from collections.abc import Collection
from dataclasses import dataclass

from app.models import CustomUser
from events.constants import Commitment
from events.models import Event
from org.models import OrgUser
from org.models_profiles import PlayerDeadlockProfile, PlayerDotaProfile
from org.standing.cache import StandingCache


@dataclass(frozen=True, slots=True)
class EvalContext:
    """Everything a check reads, loaded once per evaluation. Never creates
    an OrgUser."""

    event: Event
    user: CustomUser
    org_user: OrgUser | None
    intent: Commitment
    now: datetime.datetime
    actor: CustomUser | None = None
    discord_role_ids: frozenset[str] = frozenset()
    for_staff_placement: bool = False
    standing_cache: StandingCache | None = None

    @classmethod
    def load(
        cls,
        event: Event,
        user: CustomUser,
        *,
        intent: Commitment,
        now: datetime.datetime,
        actor: CustomUser | None = None,
        discord_role_ids: Collection[str] | None = None,
        for_staff_placement: bool = False,
        standing_cache: StandingCache | None = None,
    ) -> EvalContext:
        return cls(
            event=event,
            user=user,
            org_user=_load_org_user(event, user),
            intent=intent,
            now=now,
            actor=actor,
            discord_role_ids=frozenset(discord_role_ids or ()),
            for_staff_placement=for_staff_placement,
            standing_cache=standing_cache,
        )

    @property
    def dota_profile(self) -> PlayerDotaProfile | None:
        return getattr(self.org_user, "dota_profile", None)

    @property
    def deadlock_profile(self) -> PlayerDeadlockProfile | None:
        return getattr(self.org_user, "deadlock_profile", None)


def _load_org_user(event: Event, user: CustomUser) -> OrgUser | None:
    if event.organization_id is None or user.pk is None:
        return None
    return (
        OrgUser.objects.select_related("dota_profile", "deadlock_profile")
        .filter(user=user, organization_id=event.organization_id)
        .first()
    )
