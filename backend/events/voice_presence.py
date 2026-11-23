"""Discord voice presence for events: watched channels, presence rows and voice confirms."""

import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

import redis
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone as tz

from app.models import CustomUser
from app.redis_client import get_redis_client
from app.redis_keys import namespaced_key
from events.constants import EventState, VoicePresenceSource
from events.ledger import SignupActor
from events.models import Event, EventSignup, EventVoicePresence, SignupLedgerEntry
from events.ready_check import (
    ConfirmResult,
    confirm_ready,
    live_ready_check,
    lock_event,
)
from events.ready_check_constants import (
    PRESENCE_FRESH,
    ReadyCheckConfirmVia,
    ReadyCheckPhase,
)
from events.ready_check_core import ACCEPTING_PHASES
from telemetry.logging import get_logger

__all__ = [
    "FEED_HEARTBEAT_TTL_SECONDS",
    "PRESENCE_FRESH",
    "PresenceOutcome",
    "SNAPSHOT_GRACE",
    "Transition",
    "WATCH_LOOKAHEAD",
    "WATCH_LOOKBEHIND",
    "WatchedChannel",
    "apply_voice_state",
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


class Transition(StrEnum):
    JOINED = "joined"
    LEFT = "left"
    SEEN = "seen"
    PINNED = "pinned"
    NONE = "none"


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


def _apply_presence(
    event: Event, user: CustomUser, present: bool, now: datetime, *, from_gateway: bool
) -> Transition:
    row = (
        EventVoicePresence.objects.select_for_update()
        .filter(event=event, user=user)
        .first()
    )
    if row is None:
        if not present:
            return Transition.NONE
        row = EventVoicePresence(event=event, user=user)
    manual = row.source == VoicePresenceSource.MANUAL
    if manual and not from_gateway:
        if present and row.present:
            row.last_seen_at = now
            row.save(update_fields=["last_seen_at", "updated_at"])
        return Transition.PINNED
    # A manual pin is not feed evidence, so a gateway report applies in full.
    was_present = row.present and not manual
    row.source = VoicePresenceSource.FEED
    if present and not was_present:
        row.present = True
        if row.first_joined_at is None:
            row.first_joined_at = now
        row.last_joined_at = now
        row.last_seen_at = now
        row.guild_id = event.organization.discord_server_id or ""
        row.channel_id = event.event_voice_channel_id
        transition = Transition.JOINED
    elif not present and (was_present or manual):
        row.present = False
        row.last_left_at = now
        transition = Transition.LEFT
    elif present:
        row.last_seen_at = now
        transition = Transition.SEEN
    else:
        transition = Transition.NONE
    row.save()
    return transition


def _maybe_confirm(
    locked: Event,
    user: CustomUser,
    *,
    actor: SignupActor,
    caused_by: SignupLedgerEntry | None = None,
) -> ConfirmResult | None:
    check = live_ready_check(locked)
    if (
        check is None
        or check.phase not in ACCEPTING_PHASES
        or check.settings_snapshot.get("voice_presence_confirms") is not True
        or not locked.voice_presence_confirms
    ):
        return None
    result = confirm_ready(
        locked,
        user,
        via=ReadyCheckConfirmVia.VOICE,
        actor=actor,
        caused_by=caused_by,
    )
    if result in (ConfirmResult.NOT_IN_CHECK, ConfirmResult.CLOSED):
        log.debug(
            "voice_presence_confirm_skipped",
            **_LOG,
            event_id=locked.pk,
            ready_check_id=check.pk,
            user_id=user.pk,
            outcome=str(result),
        )
    return result


def apply_voice_state(
    *,
    guild_id: str,
    discord_user_id: str,
    before_channel_id: str | None,
    after_channel_id: str | None,
) -> PresenceOutcome:
    outcome = PresenceOutcome()
    before = before_channel_id or None
    after = after_channel_id or None
    if before == after:
        return outcome
    now = tz.now()
    channels = [channel for channel in (before, after) if channel]
    events = list(
        watched_events(now)
        .filter(
            event_voice_channel_id__in=channels,
            organization__discord_server_id=guild_id,
        )
        .order_by("pk")
    )
    if not events:
        outcome.detail = "not_watched"
        return outcome
    user = CustomUser.objects.nocache().filter(discordId=discord_user_id).first()
    if user is None:
        outcome.unknown_users = 1
        outcome.detail = "user_not_linked"
        log.debug(
            "voice_state_user_not_linked",
            **_LOG,
            guild_id=guild_id,
            event_count=len(events),
        )
        return outcome
    for event in events:
        if not EventSignup.objects.nocache().filter(event=event, user=user).exists():
            outcome.not_signed_up += 1
            continue
        outcome.events += 1
        with transaction.atomic():
            locked = lock_event(event)
            channel = locked.event_voice_channel_id
            if channel == after:
                present = True
            elif channel == before:
                present = False
            else:
                continue
            transition = _apply_presence(locked, user, present, now, from_gateway=True)
            if transition == Transition.JOINED:
                outcome.joined += 1
                result = _maybe_confirm(locked, user, actor=SignupActor.voice(user))
                if result == ConfirmResult.CONFIRMED:
                    outcome.confirmed += 1
            elif transition == Transition.LEFT:
                outcome.left += 1
    log.info(
        "voice_state_applied",
        **_LOG,
        guild_id=guild_id,
        user_id=user.pk,
        before_channel_id=before,
        after_channel_id=after,
        events=outcome.events,
        joined=outcome.joined,
        left=outcome.left,
        confirmed=outcome.confirmed,
        not_signed_up=outcome.not_signed_up,
    )
    return outcome
