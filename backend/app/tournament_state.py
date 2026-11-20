"""Prefetch plans for tournament state and the helpers draft state reuses.

``fresh=True`` makes every prefetch bypass cacheops, so a payload built right
after a write never depends on the ordering of post-commit invalidations.
"""

from django.db.models import BooleanField, Model, Prefetch, QuerySet, Value

from app.models import (
    CustomUser,
    Draft,
    DraftOptions,
    DraftRound,
    Game,
    League,
    Organization,
    Team,
    Tournament,
)
from draft.models import HeroDraft

_TEAM_USER_RELATIONS: tuple[str, ...] = ("members", "dropin_members", "left_members")
_GAME_TEAM_RELATIONS: tuple[str, ...] = ("radiant_team", "dire_team", "winning_team")


def qs[M: Model](model: type[M], fresh: bool) -> QuerySet[M]:
    queryset = model.objects.all()
    return queryset.nocache() if fresh else queryset


def team_prefetches(path: str, fresh: bool) -> list[Prefetch]:
    team_qs = qs(Team, fresh).select_related("captain", "deputy_captain")
    return [
        Prefetch(path, queryset=team_qs),
        *(
            Prefetch(f"{path}__{rel}", queryset=qs(CustomUser, fresh))
            for rel in _TEAM_USER_RELATIONS
        ),
    ]


def tournament_prefetches(prefix: str, fresh: bool) -> list[Prefetch]:
    return [
        *team_prefetches(f"{prefix}teams", fresh),
        Prefetch(f"{prefix}users", queryset=qs(CustomUser, fresh)),
        Prefetch(f"{prefix}league", queryset=qs(League, fresh)),
        Prefetch(f"{prefix}league__organization", queryset=qs(Organization, fresh)),
    ]


def draft_round_prefetch(prefix: str, fresh: bool) -> Prefetch:
    rounds_qs = qs(DraftRound, fresh).select_related("captain", "choice")
    return Prefetch(f"{prefix}draft_rounds", queryset=rounds_qs)


def tournament_state_queryset(*, fresh: bool) -> QuerySet[Tournament]:
    game_prefetches: list[Prefetch] = [
        Prefetch("games", queryset=qs(Game, fresh)),
        Prefetch("games__herodraft", queryset=qs(HeroDraft, fresh)),
    ]
    for rel in _GAME_TEAM_RELATIONS:
        game_prefetches.extend(team_prefetches(f"games__{rel}", fresh))
    return qs(Tournament, fresh).prefetch_related(
        *tournament_prefetches("", fresh),
        Prefetch("league__admins", queryset=qs(CustomUser, fresh)),
        Prefetch("league__staff", queryset=qs(CustomUser, fresh)),
        Prefetch(
            "draft_options",
            queryset=qs(DraftOptions, fresh).annotate(
                loaded_uncached=Value(fresh, output_field=BooleanField())
            ),
        ),
        Prefetch("draft", queryset=qs(Draft, fresh)),
        draft_round_prefetch("draft__", fresh),
        *game_prefetches,
    )
