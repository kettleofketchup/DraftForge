"""Discord voice presence for events: watched channels, presence rows and voice confirms."""

import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

import redis
from django.db.models import Q, QuerySet
from django.utils import timezone as tz

from app.redis_client import get_redis_client
from app.redis_keys import namespaced_key
from events.constants import EventState
from events.models import Event
from events.ready_check_constants import PRESENCE_FRESH, ReadyCheckPhase
from telemetry.logging import get_logger

__all__ = [
    "FEED_HEARTBEAT_TTL_SECONDS",
    "PRESENCE_FRESH",
    "PresenceOutcome",
    "SNAPSHOT_GRACE",
    "WATCH_LOOKAHEAD",
    "WATCH_LOOKBEHIND",
    "WatchedChannel",
    "touch_feed_heartbeat",
    "voice_feed_age_seconds",
    "watched_channels",
    "watched_events",
]

log = get_logger(__name__)

WATCH_LOOKAHEAD: Final = timedelta(hours=6)
WATCH_LOOKBEHIND: Final = timedelta(hours=24)
FEED_HEARTBEAT_TTL_SECONDS: Final = 3600
SNAPSHOT_GRACE: Final = timedelta(seconds=30)
# CLOSED is live for the one-check-per-event rule but no longer needs the feed.
_WATCH_CHECK_PHASES: Final[tuple[str, ...]] = (
    ReadyCheckPhase.OPEN,
    ReadyCheckPhase.ESCALATED,
    ReadyCheckPhase.HELD,
)
_LOG = {"system": "events", "subsystem": "voice_presence"}


@dataclass(frozen=True)
class WatchedChannel:
    guild_id: str
    channel_id: str
    event_ids: tuple[int, ...]


@dataclass
class PresenceOutcome:
    events: int = 0
    joined: int = 0
    left: int = 0
    confirmed: int = 0
    unknown_users: int = 0
    not_signed_up: int = 0
    detail: str = ""


def watched_events(now: datetime | None = None) -> QuerySet[Event]:
    now = now or tz.now()
    in_window = Q(
        state__in=(EventState.SIGNUPS_OPEN, EventState.ROLL_CALL),
        scheduled_at__gte=now - WATCH_LOOKBEHIND,
        scheduled_at__lte=now + WATCH_LOOKAHEAD,
    )
    in_progress = Q(
        state=EventState.IN_PROGRESS, scheduled_at__gte=now - WATCH_LOOKBEHIND
    )
    live_check = Q(ready_checks__phase__in=_WATCH_CHECK_PHASES)
    return (
        Event.objects.nocache()
        .select_related("organization")
        .exclude(event_voice_channel_id="")
        .exclude(organization__discord_server_id="")
        .exclude(organization__discord_server_id__isnull=True)
        .filter(in_window | in_progress | live_check)
        .distinct()
    )


def watched_channels(now: datetime | None = None) -> list[WatchedChannel]:
    grouped: dict[tuple[str, str], set[int]] = {}
    for event in watched_events(now):
        key = (event.organization.discord_server_id, event.event_voice_channel_id)
        grouped.setdefault(key, set()).add(event.pk)
    return [
        WatchedChannel(
            guild_id=guild_id, channel_id=channel_id, event_ids=tuple(sorted(ids))
        )
        for (guild_id, channel_id), ids in sorted(grouped.items())
    ]


def _feed_key(guild_id: str, channel_id: str | None = None) -> str:
    suffix = f":{channel_id}" if channel_id else ""
    return namespaced_key(f"voice_feed:{guild_id}{suffix}")


def _heartbeat_unavailable(op: str, guild_id: str, exc: redis.RedisError) -> None:
    log.warning(
        "voice_feed_heartbeat_unavailable",
        **_LOG,
        op=op,
        guild_id=guild_id,
        error=type(exc).__name__,
    )


def touch_feed_heartbeat(guild_id: str, channel_ids: Iterable[str]) -> None:
    channels = list(channel_ids)
    if not channels:
        return
    stamp = str(time.time())
    try:
        client = get_redis_client()
        client.set(_feed_key(guild_id), stamp, ex=FEED_HEARTBEAT_TTL_SECONDS)
        for channel_id in channels:
            client.set(
                _feed_key(guild_id, channel_id), stamp, ex=FEED_HEARTBEAT_TTL_SECONDS
            )
    except redis.RedisError as exc:
        _heartbeat_unavailable("touch", guild_id, exc)


def voice_feed_age_seconds(
    guild_id: str, channel_id: str | None = None
) -> float | None:
    try:
        raw = get_redis_client().get(_feed_key(guild_id, channel_id))
    except redis.RedisError as exc:
        _heartbeat_unavailable("age", guild_id, exc)
        return None
    if raw is None:
        return None
    try:
        stamp = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, time.time() - stamp)
