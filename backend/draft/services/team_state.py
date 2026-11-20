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
from django.db.models import Prefetch, QuerySet

from app.models import Draft, DraftEvent, Tournament
from app.serializers import DraftSerializerSlim, build_users_dict_with_org
from app.tournament_state import draft_round_prefetch, qs, tournament_prefetches
from draft.serializers.team import DraftEventSerializer


def draft_state_queryset(*, fresh: bool) -> QuerySet[Draft]:
    return qs(Draft, fresh).prefetch_related(
        Prefetch("tournament", queryset=qs(Tournament, fresh)),
        draft_round_prefetch("", fresh),
        *tournament_prefetches("tournament__", fresh),
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
