"""
Broadcast helper for sending draft events to WebSocket channel groups.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from cacheops.transaction import is_sql_dirty
from channels.layers import get_channel_layer
from django.db import DEFAULT_DB_ALIAS, connection, connections, transaction
from django.db.backends.base.base import BaseDatabaseWrapper

from app.draft_state import build_draft_state
from app.models import Draft
from app.serializers import (
    DraftEventSerializer,
    DraftTeamSerializerFull,
    HeroDraftSerializer,
)
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from app.models import DraftEvent, DraftTeam, HeroDraft

log = get_logger(__name__)


@dataclass
class _SharedStates:
    thread_id: int
    db: BaseDatabaseWrapper
    states: dict[int, tuple[int, dict | None]] = field(default_factory=dict)


_shared_draft_states: ContextVar[_SharedStates | None] = ContextVar(
    "_shared_draft_states", default=None
)


def _owned_shared_states() -> dict[int, tuple[int, dict | None]] | None:
    """The shared states, unless this context was inherited by another thread."""
    shared = _shared_draft_states.get()
    if shared is None:
        return None
    if shared.thread_id != threading.get_ident():
        return None
    if shared.db is not connections[DEFAULT_DB_ALIAS]:
        return None
    return shared.states


def _forget_states_on_write(
    execute: Callable[..., object],
    sql: str,
    params: object,
    many: bool,
    context: dict[str, object],
) -> object:
    shared = _owned_shared_states()
    if shared and is_sql_dirty(sql):
        shared.clear()
    return execute(sql, params, many, context)


@contextmanager
def atomic_sharing_draft_state() -> Iterator[None]:
    """``transaction.atomic()`` whose post-commit draft broadcasts share one state.

    When this is the outermost block, the on_commit broadcasts it triggers run
    before it exits and reuse a single build per draft. Any SQL write on this
    connection drops the shared states, and a commit by any other connection
    (seen through SQLite's ``data_version``) forces a rebuild; nested blocks
    defer their callbacks past the exit and build per event as usual. The
    states belong to the opening thread and connection; a thread that inherits
    this context sees none of them.
    """
    token = _shared_draft_states.set(
        _SharedStates(threading.get_ident(), connections[DEFAULT_DB_ALIAS])
    )
    try:
        with connection.execute_wrapper(_forget_states_on_write):
            with transaction.atomic():
                yield
    finally:
        _shared_draft_states.reset(token)


def _data_version() -> int | None:
    """Changes whenever another connection commits; None off SQLite."""
    if connection.vendor != "sqlite":
        return None
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA data_version")
        return cursor.fetchone()[0]


def _draft_state(draft_id: int) -> dict | None:
    shared = _owned_shared_states()
    if shared is None or connection.in_atomic_block:
        return build_draft_state(draft_id, fresh=True)
    version = _data_version()
    if version is None:
        return build_draft_state(draft_id, fresh=True)
    cached = shared.get(draft_id)
    if cached is None or cached[0] != version:
        cached = (version, build_draft_state(draft_id, fresh=True))
        shared[draft_id] = cached
    return cached[1]


def broadcast_event(event: "DraftEvent", include_draft_state: bool = True) -> None:
    """
    Broadcast a DraftEvent to both draft-specific and tournament channel groups.

    Args:
        event: DraftEvent instance to broadcast
        include_draft_state: If True, include the full draft state in the broadcast.
            This allows clients to update their state without making additional API calls.

    Note:
        This function gracefully handles connection errors (e.g., Redis unavailable)
        to allow draft operations to proceed even without real-time broadcasting.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        log.warning(
            "broadcast_skipped",
            system="websocket",
            subsystem="broadcast",
            kind="draft",
            reason="no_channel_layer",
            draft_id=event.draft_id,
        )
        return

    payload = DraftEventSerializer(event).data
    tournament_id = event.draft.tournament_id

    # Include the full draft state so clients can update without additional API calls
    draft_state = None
    if include_draft_state:
        try:
            draft_state = _draft_state(event.draft_id)
            if draft_state is None:
                raise Draft.DoesNotExist(f"Draft {event.draft_id} does not exist")
        except Exception as e:
            log.warning(
                "broadcast_serialize_failed",
                system="websocket",
                subsystem="broadcast",
                kind="draft",
                draft_id=event.draft_id,
                error=str(e),
            )

    try:
        message = {
            "type": "draft.event",
            "payload": payload,
        }
        if draft_state:
            message["draft_state"] = draft_state

        # Send to draft-specific channel
        import time as _t  # TEMP-DIAG

        import redis as _redis

        _g0 = _t.monotonic()
        async_to_sync(channel_layer.group_send)(
            f"draft_{event.draft_id}",
            message,
        )
        try:
            _members = _redis.Redis(host=__import__("django.conf").conf.settings.REDIS_HOST, port=6379, db=0).zrange(channel_layer._group_key(f"draft_{event.draft_id}"), 0, -1)
        except Exception as _e:
            _members = [f"err:{_e}"]
        log.debug(
            "diag_group_send",
            system="websocket",
            subsystem="diag",
            draft_id=event.draft_id,
            event_type=event.event_type,
            duration_ms=round((_t.monotonic() - _g0) * 1000, 1),
            members=[m.decode() if isinstance(m, bytes) else m for m in _members],
        )

        # Send to tournament channel
        async_to_sync(channel_layer.group_send)(
            f"tournament_{tournament_id}",
            message,
        )

        log.info(
            "broadcast_sent",
            system="websocket",
            subsystem="broadcast",
            kind="draft",
            event_type=event.event_type,
            draft_id=event.draft_id,
            tournament_id=tournament_id,
            with_state=bool(draft_state),
        )
    except Exception as e:
        # Log the error but don't fail the draft operation
        log.warning(
            "broadcast_failed",
            system="websocket",
            subsystem="broadcast",
            kind="draft",
            event_type=event.event_type,
            draft_id=event.draft_id,
            error=str(e),
        )


def broadcast_event_after_commit(event: "DraftEvent") -> None:
    """Broadcast ``event`` once the transaction commits; failures are logged, not raised.

    The write is already committed when the hook runs, so a raising broadcast
    must neither fail the caller's response nor skip the hooks queued after it.
    """
    transaction.on_commit(lambda: _broadcast_committed_event(event))


def _broadcast_committed_event(event: "DraftEvent") -> None:
    try:
        broadcast_event(event)
    except Exception as e:
        log.error(
            "broadcast_after_commit_failed",
            system="websocket",
            subsystem="broadcast",
            kind="draft",
            event_type=event.event_type,
            draft_id=event.draft_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )


def broadcast_herodraft_event(
    draft: "HeroDraft",
    event_type: str,
    draft_team: "DraftTeam | None" = None,
    metadata: dict | None = None,
) -> None:
    """
    Broadcast a HeroDraft event to WebSocket consumers.

    Args:
        draft: HeroDraft instance
        event_type: Type of event (e.g., "captain_ready", "hero_selected")
        draft_team: DraftTeam instance (optional)
        metadata: Additional event metadata (optional)
    """
    from app.models import HeroDraftEvent

    channel_layer = get_channel_layer()
    if channel_layer is None:
        log.warning(
            "broadcast_skipped",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft",
            reason="no_channel_layer",
            draft_id=draft.id,
        )
        return

    # Create event record (if not already created by the view)
    event = HeroDraftEvent.objects.create(
        draft=draft,
        event_type=event_type,
        draft_team=draft_team,
        metadata=metadata or {},
    )

    # Build payload
    payload = {
        "type": "herodraft.event",
        "event_type": event_type,
        "event_id": event.id,
        "draft_team": DraftTeamSerializerFull(draft_team).data if draft_team else None,
        "metadata": metadata or {},  # Include metadata for hero_id, action_type etc
        "timestamp": event.created_at.isoformat(),
    }

    # Include full draft state with prefetched members
    try:
        from app.models import HeroDraft

        draft = HeroDraft.objects.prefetch_related(
            "draft_teams__tournament_team__captain",
            "draft_teams__tournament_team__members",
            "rounds",
        ).get(id=draft.id)
        payload["draft_state"] = HeroDraftSerializer(draft).data
    except Exception as e:
        log.warning(
            "broadcast_serialize_failed",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft",
            draft_id=draft.id,
            error=str(e),
        )

    # Send to channel group
    room_group_name = f"herodraft_{draft.id}"

    try:
        async_to_sync(channel_layer.group_send)(room_group_name, payload)
        log.debug(
            "broadcast_sent",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft",
            event_type=event_type,
            draft_id=draft.id,
            event_id=event.id,
        )
    except Exception as e:
        log.warning(
            "broadcast_failed",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft",
            event_type=event_type,
            draft_id=draft.id,
            error=str(e),
        )


def broadcast_herodraft_state(
    draft: "HeroDraft",
    event_type: str,
    metadata: dict | None = None,
    draft_team: "DraftTeam | None" = None,
) -> None:
    """
    Broadcast the current HeroDraft state to WebSocket consumers.

    Used for state changes like pause/resume where the event is already created.
    This avoids creating duplicate events.

    Args:
        draft: HeroDraft instance (should be refreshed from DB)
        event_type: Type of event for logging (e.g., "draft_paused", "draft_resumed")
        metadata: Additional event metadata (optional, e.g., countdown_seconds)
        draft_team: DraftTeam instance (optional, for captain_connected/disconnected events)
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        log.warning(
            "broadcast_skipped",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft_state",
            reason="no_channel_layer",
            draft_id=draft.id,
        )
        return

    # Build payload with current state
    payload = {
        "type": "herodraft.event",
        "event_type": event_type,
    }

    if metadata:
        payload["metadata"] = metadata

    # Include draft_team with captain data for connection events
    if draft_team:
        payload["draft_team"] = DraftTeamSerializerFull(draft_team).data

    # Include full draft state with prefetched members
    try:
        from app.models import HeroDraft

        draft = HeroDraft.objects.prefetch_related(
            "draft_teams__tournament_team__captain",
            "draft_teams__tournament_team__members",
            "rounds",
        ).get(id=draft.id)
        payload["draft_state"] = HeroDraftSerializer(draft).data
    except Exception as e:
        log.warning(
            "broadcast_serialize_failed",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft_state",
            draft_id=draft.id,
            error=str(e),
        )
        return  # Don't broadcast without state

    # Send to channel group
    room_group_name = f"herodraft_{draft.id}"

    try:
        async_to_sync(channel_layer.group_send)(room_group_name, payload)
        log.debug(
            "broadcast_sent",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft_state",
            event_type=event_type,
            draft_id=draft.id,
        )
    except Exception as e:
        log.warning(
            "broadcast_failed",
            system="websocket",
            subsystem="broadcast",
            kind="herodraft_state",
            event_type=event_type,
            draft_id=draft.id,
            error=str(e),
        )
