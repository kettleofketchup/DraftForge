"""Team-draft state serialization shared by broadcasts, consumers and views.

The prefetch plan loads every relation the draft-state serializers walk, so a
serialization costs a fixed number of queries regardless of rounds, teams or
users. ``fresh=True`` bypasses cacheops on every level; use it for anything
built right after a write (broadcasts, endpoint responses) so the payload never
depends on the ordering of post-commit invalidations. Related users and
captains are only ever read for their pk here, which the cached FK columns
keep correct, so the select_related joins cannot leak stale profile data.
"""

from django.db.models import Model, Prefetch, QuerySet

from app.models import CustomUser, Draft, DraftRound, Game, HeroDraft, Team, Tournament
from app.serializers import DraftSerializerSlim, _build_users_dict

_TEAM_USER_RELATIONS: tuple[str, ...] = ("members", "dropin_members", "left_members")
_GAME_TEAM_RELATIONS: tuple[str, ...] = ("radiant_team", "dire_team", "winning_team")


def _qs[M: Model](model: type[M], fresh: bool) -> QuerySet[M]:
    qs = model.objects.all()
    return qs.nocache() if fresh else qs


def _team_prefetches(path: str, fresh: bool) -> list[Prefetch]:
    team_qs = _qs(Team, fresh).select_related("captain", "deputy_captain")
    return [
        Prefetch(path, queryset=team_qs),
        *(
            Prefetch(f"{path}__{rel}", queryset=_qs(CustomUser, fresh))
            for rel in _TEAM_USER_RELATIONS
        ),
    ]


def _tournament_prefetches(prefix: str, fresh: bool) -> list[Prefetch]:
    return [
        *_team_prefetches(f"{prefix}teams", fresh),
        Prefetch(f"{prefix}users", queryset=_qs(CustomUser, fresh)),
    ]


def _draft_round_prefetch(prefix: str, fresh: bool) -> Prefetch:
    rounds_qs = _qs(DraftRound, fresh).select_related("captain", "choice")
    return Prefetch(f"{prefix}draft_rounds", queryset=rounds_qs)


def draft_state_queryset(*, fresh: bool) -> QuerySet[Draft]:
    return _qs(Draft, fresh).prefetch_related(
        Prefetch("tournament", queryset=_qs(Tournament, fresh)),
        _draft_round_prefetch("", fresh),
        *_tournament_prefetches("tournament__", fresh),
    )


def tournament_state_queryset(*, fresh: bool) -> QuerySet[Tournament]:
    game_prefetches: list[Prefetch] = [
        Prefetch("games", queryset=_qs(Game, fresh)),
        Prefetch("games__herodraft", queryset=_qs(HeroDraft, fresh)),
    ]
    for rel in _GAME_TEAM_RELATIONS:
        game_prefetches.extend(_team_prefetches(f"games__{rel}", fresh))
    return _qs(Tournament, fresh).prefetch_related(
        *_tournament_prefetches("", fresh),
        Prefetch("draft", queryset=_qs(Draft, fresh)),
        _draft_round_prefetch("draft__", fresh),
        *game_prefetches,
    )


def build_draft_state(draft_id: int, *, fresh: bool) -> dict | None:
    """DraftSerializerSlim payload plus the ``_users`` hydration dict (str keys)."""
    try:
        draft = draft_state_queryset(fresh=fresh).get(pk=draft_id)
    except Draft.DoesNotExist:
        return None
    data = DraftSerializerSlim(draft).data
    # msgpack strict mode in the channel layer forbids int map keys
    data["_users"] = {str(k): v for k, v in _build_users_dict(draft.tournament).items()}
    return data
