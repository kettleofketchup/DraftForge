from dataclasses import dataclass
from datetime import datetime

from org.conduct.queries import member_scores
from org.conduct.scoring import MemberScore, prior_member_score
from org.conduct.serializers import rate
from org.models import Organization, OrgUser
from org.models_conduct import OrgConductSettings
from user.querysets import with_user_profiles


@dataclass(frozen=True)
class ConductBoard:
    ranked: list[tuple[OrgUser, MemberScore, int]]
    new: list[tuple[OrgUser, MemberScore]]
    own: tuple[OrgUser, MemberScore, int | None] | None


def _sort_name(org_user: OrgUser) -> str:
    user = org_user.user
    return (user.nickname or user.username).casefold()


def _ranked(
    scored: list[tuple[OrgUser, MemberScore]],
) -> list[tuple[OrgUser, MemberScore, int]]:
    ordered = sorted(
        scored,
        key=lambda pair: (
            -rate(pair[1].show_rate),
            -pair[1].counted_events,
            _sort_name(pair[0]),
            pair[0].pk,
        ),
    )
    result: list[tuple[OrgUser, MemberScore, int]] = []
    rank = 0
    previous: tuple[float, int] | None = None
    for org_user, score in ordered:
        key = (rate(score.show_rate), score.counted_events)
        if key != previous:
            rank += 1
            previous = key
        result.append((org_user, score, rank))
    return result


def conduct_board(
    org: Organization,
    *,
    own: OrgUser | None,
    now: datetime,
    settings: OrgConductSettings,
) -> ConductBoard:
    scores = member_scores(org.pk, None, now=now, settings=settings)
    members = with_user_profiles(
        OrgUser.objects.filter(pk__in=scores), "user"
    ).in_bulk()
    ranked = _ranked(
        [
            (members[pk], score)
            for pk, score in scores.items()
            if score.status == "scored" and pk in members
        ]
    )
    new = sorted(
        (
            (members[pk], score)
            for pk, score in scores.items()
            if score.status == "new" and pk in members
        ),
        key=lambda pair: (-pair[1].counted_events, _sort_name(pair[0]), pair[0].pk),
    )
    own_entry: tuple[OrgUser, MemberScore, int | None] | None = None
    if own is not None:
        ranks = {org_user.pk: rank for org_user, _, rank in ranked}
        own_entry = (
            own,
            scores.get(own.pk) or prior_member_score(settings),
            ranks.get(own.pk),
        )
    return ConductBoard(ranked=ranked, new=new, own=own_entry)
