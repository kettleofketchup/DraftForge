"""Discord voice presence for events: watched channels, presence rows and voice confirms."""

import time
from collections.abc import Iterable, Mapping, Sequence
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
from events.constants import EventState, SignupAction, VoicePresenceSource
from events.ledger import SignupActor, snapshot
from events.models import (
    Event,
    EventSignup,
    EventVoicePresence,
    ReadyCheck,
    SignupLedgerEntry,
)
from events.ready_check import (
    ConfirmResult,
    confirm_ready,
    live_ready_check,
    lock_event,
    trusted_present_user_ids,
)
from events.ready_check_constants import (
    PRESENCE_FRESH,
    ReadyCheckConfirmVia,
    ReadyCheckEntryState,
    ReadyCheckPhase,
)
from events.ready_check_core import ACCEPTING_PHASES
from events.services import _record_leaf
from telemetry.logging import get_logger

__all__ = [
    "FEED_HEARTBEAT_TTL_SECONDS",
    "ManualPresenceResult",
    "PRESENCE_FRESH",
    "PresenceOutcome",
    "SNAPSHOT_GRACE",
    "Transition",
    "WATCH_LOOKAHEAD",
    "WATCH_LOOKBEHIND",
    "WatchedChannel",
    "apply_voice_snapshot",
    "apply_voice_state",
    "set_presence_manually",
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


@dataclass(frozen=True)
class ManualPresenceResult:
    presence: EventVoicePresence
    ledger_entry_id: int
    confirm: ConfirmResult | None


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


def _matches_channel(row: EventVoicePresence, event: Event) -> bool:
    return (
        row.guild_id == (event.organization.discord_server_id or "")
        and row.channel_id == event.event_voice_channel_id
    )


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
    was_present = row.present and not manual and _matches_channel(row, event)
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
    elif not present and (row.present or manual):
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


def _voice_confirm_check(event: Event) -> ReadyCheck | None:
    check = live_ready_check(event)
    if (
        check is None
        or check.phase not in ACCEPTING_PHASES
        or check.settings_snapshot.get("voice_presence_confirms") is not True
        or not event.voice_presence_confirms
    ):
        return None
    return check


def _maybe_confirm(
    locked: Event,
    user: CustomUser,
    *,
    actor: SignupActor,
    caused_by: SignupLedgerEntry | None = None,
) -> ConfirmResult | None:
    check = _voice_confirm_check(locked)
    if check is None:
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


def _trusted_rows(event: Event, now: datetime) -> QuerySet[EventVoicePresence]:
    return EventVoicePresence.objects.filter(
        event=event,
        present=True,
        source=VoicePresenceSource.FEED,
        guild_id=event.organization.discord_server_id or "",
        channel_id=event.event_voice_channel_id,
        last_seen_at__gte=now - PRESENCE_FRESH,
    )


def _reconcile_has_work(event: Event, now: datetime) -> bool:
    check = _voice_confirm_check(event)
    if check is None:
        return False
    return check.entries.filter(
        state=ReadyCheckEntryState.PENDING,
        user_id__in=_trusted_rows(event, now).values("user_id"),
    ).exists()


def _reconcile_pending(locked: Event, now: datetime) -> int:
    check = _voice_confirm_check(locked)
    if check is None:
        return 0
    trusted = trusted_present_user_ids(locked, now)
    if not trusted:
        return 0
    entries = (
        check.entries.filter(state=ReadyCheckEntryState.PENDING, user_id__in=trusted)
        .select_related("user")
        .order_by("pk")
    )
    confirmed = 0
    for entry in entries:
        result = confirm_ready(
            locked,
            entry.user,
            via=ReadyCheckConfirmVia.VOICE,
            actor=SignupActor.voice(entry.user),
        )
        if result == ConfirmResult.CONFIRMED:
            confirmed += 1
    return confirmed


def _recent(at: datetime | None, cutoff: datetime) -> bool:
    return at is not None and at >= cutoff


def _snapshot_target(
    row: EventVoicePresence | None, listed: bool, cutoff: datetime, event: Event
) -> bool | None:
    """Presence the snapshot should apply to a row, or None to leave it alone."""
    if row is None:
        return True if listed else None
    if row.source == VoicePresenceSource.MANUAL:
        return None
    if not _matches_channel(row, event):
        return listed if listed or row.present else None
    if row.present == listed:
        return None
    if _recent(row.last_joined_at, cutoff) or _recent(row.last_left_at, cutoff):
        return None
    return listed


def _snapshot_event(
    event: Event,
    listed_ids: set[int],
    users: dict[int, CustomUser],
    now: datetime,
    outcome: PresenceOutcome,
) -> None:
    signed = set(
        EventSignup.objects.nocache()
        .filter(event=event, user_id__in=listed_ids)
        .values_list("user_id", flat=True)
    )
    outcome.not_signed_up += len(listed_ids - signed)
    outcome.events += 1
    cutoff = now - SNAPSHOT_GRACE
    rows = {
        row.user_id: row
        for row in EventVoicePresence.objects.filter(event=event).filter(
            Q(user_id__in=signed) | Q(present=True)
        )
    }
    changes: dict[int, bool] = {}
    seen: list[int] = []
    for user_id in signed | rows.keys():
        row = rows.get(user_id)
        listed = user_id in signed
        target = _snapshot_target(row, listed, cutoff, event)
        if target is not None:
            changes[user_id] = target
        elif row is not None and listed and row.present:
            seen.append(row.pk)
    if seen:
        EventVoicePresence.objects.filter(pk__in=seen).update(last_seen_at=now)
    if not changes and not _reconcile_has_work(event, now):
        return
    with transaction.atomic():
        locked = lock_event(event)
        fresh = {
            row.user_id: row
            for row in EventVoicePresence.objects.filter(
                event=locked, user_id__in=changes.keys()
            )
        }
        for user_id in sorted(changes):
            listed = changes[user_id]
            if _snapshot_target(fresh.get(user_id), listed, cutoff, locked) is None:
                continue
            user = users.get(user_id) or CustomUser.objects.nocache().get(pk=user_id)
            transition = _apply_presence(locked, user, listed, now, from_gateway=False)
            if transition == Transition.JOINED:
                outcome.joined += 1
            elif transition == Transition.LEFT:
                outcome.left += 1
        outcome.confirmed += _reconcile_pending(locked, now)


def apply_voice_snapshot(
    *,
    guild_id: str,
    channels: Mapping[str, Sequence[str]],
    missing_channel_ids: Sequence[str] = (),
) -> PresenceOutcome:
    outcome = PresenceOutcome()
    now = tz.now()
    missing = set(missing_channel_ids)
    listed = {
        channel: set(members)
        for channel, members in channels.items()
        if channel not in missing
    }
    discord_ids = set().union(*listed.values()) if listed else set()
    by_discord = {
        user.discordId: user
        for user in CustomUser.objects.nocache().filter(discordId__in=discord_ids)
    }
    outcome.unknown_users = len(discord_ids - by_discord.keys())
    users = {user.pk: user for user in by_discord.values()}
    blocks: dict[str, list[Event]] = {}
    unseen: set[str] = set()
    for event in (
        watched_events(now)
        .filter(organization__discord_server_id=guild_id)
        .order_by("pk")
    ):
        channel = event.event_voice_channel_id
        if channel in listed:
            blocks.setdefault(channel, []).append(event)
        else:
            unseen.add(channel)
    for channel in sorted(unseen):
        log.warning(
            "voice_presence_channel_missing",
            **_LOG,
            guild_id=guild_id,
            channel_id=channel,
        )
    visible: list[str] = []
    failure: Exception | None = None
    for channel, events in blocks.items():
        listed_ids = {
            by_discord[member].pk for member in listed[channel] if member in by_discord
        }
        try:
            for event in events:
                _snapshot_event(event, listed_ids, users, now, outcome)
        except Exception as exc:
            failure = failure or exc
            continue
        visible.append(channel)
    touch_feed_heartbeat(guild_id, visible)
    log.info(
        "voice_snapshot_applied",
        **_LOG,
        guild_id=guild_id,
        channels=len(blocks),
        visible=len(visible),
        missing=len(unseen),
        events=outcome.events,
        joined=outcome.joined,
        left=outcome.left,
        confirmed=outcome.confirmed,
        unknown_users=outcome.unknown_users,
        not_signed_up=outcome.not_signed_up,
    )
    if failure is not None:
        raise failure
    return outcome


def set_presence_manually(
    event: Event,
    user: CustomUser,
    *,
    present: bool,
    reason: str,
    actor: SignupActor,
) -> ManualPresenceResult:
    with transaction.atomic():
        locked = lock_event(event)
        signup = EventSignup.objects.nocache().filter(event=locked, user=user).first()
        if signup is None:
            raise ValueError("not_signed_up")
        row = (
            EventVoicePresence.objects.select_for_update()
            .filter(event=locked, user=user)
            .first()
        ) or EventVoicePresence(event=locked, user=user)
        previous = row.present
        row.present = present
        row.source = VoicePresenceSource.MANUAL
        row.save()
        entry = _record_leaf(
            signup,
            event=locked,
            actor=actor,
            action=SignupAction.VOICE_PRESENCE_SET,
            before=snapshot(signup),
            extra={
                "voice": {
                    "present": present,
                    "previous": previous,
                    "source": str(VoicePresenceSource.MANUAL),
                }
            },
            reason=reason,
            correlation_id=f"vp{locked.pk}:{user.pk}",
        )
        confirm = (
            _maybe_confirm(locked, user, actor=actor, caused_by=entry)
            if present
            else None
        )
    log.info(
        "voice_presence_set_manually",
        **_LOG,
        event_id=locked.pk,
        user_id=user.pk,
        actor_user_id=actor.user.pk if actor.user else None,
        present=present,
        previous=previous,
        ledger_entry_id=entry.pk,
        confirm=str(confirm) if confirm else None,
    )
    return ManualPresenceResult(presence=row, ledger_entry_id=entry.pk, confirm=confirm)
