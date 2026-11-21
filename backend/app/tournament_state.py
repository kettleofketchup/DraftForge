"""Team-draft state serialization shared by broadcasts, consumers and views.

The prefetch plan loads every relation the draft-state serializers walk, so a
serialization costs a fixed number of queries regardless of rounds, teams or
users. ``fresh=True`` makes no cacheops read anywhere in the payload: the
prefetches, draft options, league/organization (and the source event's
organization), the OrgUser/LeagueUser MMR overlay and the ``_users`` cores all
come from the database (pinned by DraftStateFreshReadTests). Use it for
anything built right after a write (broadcasts, endpoint responses) so the
payload never depends on the ordering of post-commit invalidations.
"""

from django.db import connection, transaction
from django.db.models import BooleanField, Model, Prefetch, QuerySet, Value

from app.models import (
    CustomUser,
    Draft,
    DraftEvent,
    DraftOptions,
    DraftRound,
    Game,
    League,
    Organization,
    Team,
    Tournament,
)
from app.serializers import (
    DraftEventSerializer,
    DraftSerializerSlim,
    build_users_dict_with_org,
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


def draft_state_queryset(*, fresh: bool) -> QuerySet[Draft]:
    return qs(Draft, fresh).prefetch_related(
        Prefetch("tournament", queryset=qs(Tournament, fresh)),
        draft_round_prefetch("", fresh),
        *tournament_prefetches("tournament__", fresh),
    )


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


def build_draft_state(draft_id: int, *, fresh: bool) -> dict | None:
    """DraftSerializerSlim payload plus the ``_users`` hydration dict (str keys).

    A fresh build outside a transaction runs in its own, so its reads share one
    snapshot. Under the configured ``BEGIN IMMEDIATE`` that holds the write
    lock for the build: other writers wait (busy timeout) rather than commit
    mid-build. DEFERRED is not used: the OrgUser auto-create write in
    _collect_context_mmr would then fail with SQLITE_BUSY_SNAPSHOT whenever
    another connection committed after the build's first read. Cached builds
    (every websocket connect) promise no freshness and stay plain autocommit
    reads, so spectators never queue on the write lock.
    """
    if not fresh or connection.in_atomic_block:
        return _build_draft_state(draft_id, fresh=fresh)
    with transaction.atomic():
        return _build_draft_state(draft_id, fresh=fresh)


def _build_draft_state(draft_id: int, *, fresh: bool) -> dict | None:
    try:
        draft = draft_state_queryset(fresh=fresh).get(pk=draft_id)
    except Draft.DoesNotExist:
        return None
    data = DraftSerializerSlim(draft, context={"fresh": fresh}).data
    users, org = build_users_dict_with_org(draft.tournament, fresh=fresh)
    data["organization_pk"] = org.pk if org else None
    # msgpack strict mode in the channel layer forbids int map keys
    data["_users"] = {str(k): v for k, v in users.items()}
    return data


def recent_draft_events(tournament_id: int, limit: int = 20) -> list[dict]:
    try:
        draft = Draft.objects.get(tournament_id=tournament_id)
        events = DraftEvent.objects.filter(draft=draft)[:limit]
        return DraftEventSerializer(events, many=True).data
    except Draft.DoesNotExist:
        return []
