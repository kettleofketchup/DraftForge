from datetime import datetime
from typing import Any

from org.contributions.serializers import member_summary
from org.leadership.queries import (
    CaptainRating,
    captain_events,
    member_points,
    rating_board,
)
from org.leadership.rating import display
from org.leadership.settings import get_leadership_settings
from org.leadership.traits import effective_traits
from org.models import OrgUser
from org.models_leadership import CaptainTrait


def trait_data(trait: CaptainTrait) -> dict[str, Any]:
    return {
        "key": trait.key,
        "label": trait.label,
        "order": trait.order,
        "active": trait.active,
    }


def rating_data(
    rating: CaptainRating | None, traits: list[CaptainTrait]
) -> dict[str, Any]:
    overall = rating.overall if rating else None
    rates = rating.traits if rating else {}
    return {
        "rating": display(overall),
        "status": rating.status if rating else "new",
        "reviews": rating.reviews if rating else 0,
        "traits": [
            {**trait_data(t), "rating": display(rates.get(t.pk))}
            for t in traits
            if t.active
        ],
    }


def member_payload(
    org_user: OrgUser,
    *,
    now: datetime,
    detail: bool,
    staff: bool,
    period_points: bool = False,
) -> dict[str, Any]:
    org_id = org_user.organization_id
    settings = get_leadership_settings(org_id)
    traits = effective_traits(org_id)
    rating = rating_board(
        org_id,
        now=now,
        settings=settings,
        traits=traits,
        include_unreleased=staff,
        captain_ids=[org_user.pk],
    ).get(org_user.pk)
    points = member_points(org_user, now=now, include_unreleased=staff)
    payload: dict[str, Any] = {
        "member": member_summary(org_user),
        **rating_data(rating, traits),
        "points": points if period_points else points["all_time"],
    }
    if detail:
        payload["events"] = captain_events(
            org_user, now=now, settings=settings, traits=traits, staff=staff
        )
    return payload
