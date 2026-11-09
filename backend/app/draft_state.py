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
    DraftOptions,
    DraftRound,
    Game,
    HeroDraft,
    League,
    Organization,
    Team,
    Tournament,
)
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
        Prefetch(f"{prefix}league", queryset=_qs(League, fresh)),
        Prefetch(f"{prefix}league__organization", queryset=_qs(Organization, fresh)),
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
        Prefetch("league__admins", queryset=_qs(CustomUser, fresh)),
        Prefetch("league__staff", queryset=_qs(CustomUser, fresh)),
        Prefetch(
            "draft_options",
            queryset=_qs(DraftOptions, fresh).annotate(
                loaded_uncached=Value(fresh, output_field=BooleanField())
            ),
        ),
        Prefetch("draft", queryset=_qs(Draft, fresh)),
        _draft_round_prefetch("draft__", fresh),
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
    import time as _t  # TEMP-DIAG

    from telemetry.logging import get_logger as _gl

    _t0 = _t.monotonic()
    with transaction.atomic():
        _t1 = _t.monotonic()
        try:
            return _build_draft_state(draft_id, fresh=fresh)
        finally:
            _gl(__name__).debug(
                "diag_build_state",
                system="websocket",
                subsystem="diag",
                draft_id=draft_id,
                lock_wait_ms=round((_t1 - _t0) * 1000, 1),
                build_ms=round((_t.monotonic() - _t1) * 1000, 1),
            )


def _build_draft_state(draft_id: int, *, fresh: bool) -> dict | None:
    try:
        draft = draft_state_queryset(fresh=fresh).get(pk=draft_id)
    except Draft.DoesNotExist:
        return None
    data = DraftSerializerSlim(draft, context={"fresh": fresh}).data
    users = _build_users_dict(draft.tournament, fresh=fresh)
    # msgpack strict mode in the channel layer forbids int map keys
    data["_users"] = {str(k): v for k, v in users.items()}
    return data
