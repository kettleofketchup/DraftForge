"""HeroDraft tick driver bound to the shared runner in app.tasks.draft_tick.

Diagnostic events and Tempo spans (herodraft.tick.iteration with child
herodraft.tick.<step>) are emitted by draft_tick.run_tick_loop.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import redis
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.utils import timezone

from app.tasks import draft_tick
from app.tasks.draft_tick import (
    HEARTBEAT_STALE_SECONDS,
    LOCK_TIMEOUT,
    TICK_GAP_STALL_THRESHOLD_S,
    TICK_ITERATION_SLOW_THRESHOLD_S,
    TICK_STEP_SLOW_THRESHOLD_S,
    TaskInfo,
    get_redis_client,
)
from telemetry.logging import get_logger

if TYPE_CHECKING:
    from app.models import HeroDraftRound

log = get_logger(__name__)

__all__ = [
    "CAPTAIN_HEARTBEAT_KEY",
    "CONN_COUNT_KEY",
    "HEARTBEAT_STALE_SECONDS",
    "HERO_TICK_DRIVER",
    "LOCK_KEY",
    "LOCK_TIMEOUT",
    "TICK_GAP_STALL_THRESHOLD_S",
    "TICK_ITERATION_SLOW_THRESHOLD_S",
    "TICK_STEP_SLOW_THRESHOLD_S",
    "HeroDraftTickDriver",
    "TaskInfo",
    "broadcast_tick",
    "check_captain_heartbeats",
    "check_resume_countdown",
    "check_timeout",
    "decrement_connection_count",
    "get_connection_count",
    "get_redis_client",
    "increment_connection_count",
    "run_tick_loop",
    "should_continue_ticking",
    "start_tick_broadcaster",
    "stop_all_broadcasters",
    "stop_tick_broadcaster",
]

_lock = draft_tick._lock
_active_tick_tasks: dict[int, TaskInfo] = draft_tick.registry_for("herodraft")

CONN_COUNT_KEY = "herodraft:connections:{draft_id}"
LOCK_KEY = "herodraft:tick_lock:{draft_id}"
# Heartbeat key pattern (must match consumers.py)
CAPTAIN_HEARTBEAT_KEY = "herodraft:{draft_id}:captain:{user_id}:heartbeat"


def increment_connection_count(draft_id: int) -> int:
    """Increment WebSocket connection count for a draft. Returns new count."""
    return draft_tick.increment_connection_count("herodraft", draft_id)


def decrement_connection_count(draft_id: int) -> int:
    """Decrement WebSocket connection count for a draft. Returns new count."""
    return draft_tick.decrement_connection_count("herodraft", draft_id)


def get_connection_count(draft_id: int) -> int:
    """Get current WebSocket connection count for a draft."""
    return draft_tick.get_connection_count("herodraft", draft_id)


async def broadcast_tick(draft_id: int) -> None:
    """Broadcast timing anchors to all connected clients.

    Sends ANCHORS (timestamps + durations) not computed remainders.
    Clients render countdowns locally via requestAnimationFrame using
    `server_time` to compute clock offset. Decouples timer smoothness
    from broadcast cadence and eliminates the "everyone freezes for a
    few seconds" bug class.
    """
    from app.models import HeroDraft, HeroDraftState

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    room_group_name = f"herodraft_{draft_id}"

    @database_sync_to_async
    def get_tick_data():
        try:
            draft = HeroDraft.objects.get(id=draft_id)
        except HeroDraft.DoesNotExist:
            log.warning(
                "tick_skipped",
                system="herodraft",
                subsystem="timer",
                draft_id=draft_id,
                reason="not_found",
            )
            return None

        now = timezone.now()

        if draft.state == HeroDraftState.RESUMING:
            # Include the round anchors too so the client can render the
            # frozen grace + reserve values that the timer will land on
            # when RESUMING completes — server has already pushed
            # round.started_at forward by pause_duration + 3s, so
            # `grace_time_ms - (resuming_until - round_started_at)`
            # equals the grace remaining at the moment of pause.
            current_round = draft.rounds.filter(state="active").first()
            teams = list(draft.draft_teams.all().order_by("id"))
            team_a = teams[0] if teams else None
            team_b = teams[1] if len(teams) > 1 else None
            return {
                "type": "herodraft.tick",
                "draft_state": draft.state,
                "server_time": now.isoformat(),
                "resuming_until": (
                    draft.resuming_until.isoformat() if draft.resuming_until else None
                ),
                "current_round": (
                    current_round.round_number - 1 if current_round else None
                ),
                "active_team_id": (
                    current_round.draft_team_id if current_round else None
                ),
                "round_started_at": (
                    current_round.started_at.isoformat()
                    if current_round and current_round.started_at
                    else None
                ),
                "round_grace_time_ms": (
                    current_round.grace_time_ms if current_round else None
                ),
                "team_a_id": team_a.id if team_a else None,
                "team_a_reserve_ms": team_a.reserve_time_remaining if team_a else None,
                "team_b_id": team_b.id if team_b else None,
                "team_b_reserve_ms": team_b.reserve_time_remaining if team_b else None,
            }

        if draft.state != HeroDraftState.DRAFTING:
            log.info(
                "tick_skipped",
                system="herodraft",
                subsystem="timer",
                draft_id=draft_id,
                reason="wrong_state",
                draft_state=draft.state,
            )
            return None

        current_round = draft.rounds.filter(state="active").first()
        if not current_round:
            log.warning(
                "tick_skipped",
                system="herodraft",
                subsystem="timer",
                draft_id=draft_id,
                reason="no_active_round",
            )
            return None

        # Deterministic team order by ID (matches frontend assumption)
        teams = list(draft.draft_teams.all().order_by("id"))
        team_a = teams[0] if teams else None
        team_b = teams[1] if len(teams) > 1 else None

        log.debug(
            "tick_broadcast",
            system="herodraft",
            subsystem="timer",
            draft_id=draft_id,
            round=current_round.round_number,
            server_time=now.isoformat(),
            round_started_at=(
                current_round.started_at.isoformat()
                if current_round.started_at
                else None
            ),
        )

        return {
            "type": "herodraft.tick",
            "draft_state": draft.state,
            # Clock anchor for client-side rAF countdown
            "server_time": now.isoformat(),
            # Round anchors — client computes elapsed/grace/reserve locally
            "current_round": current_round.round_number - 1,  # 0-indexed
            "active_team_id": current_round.draft_team_id,
            "round_started_at": (
                current_round.started_at.isoformat()
                if current_round.started_at
                else None
            ),
            "round_grace_time_ms": current_round.grace_time_ms,
            # DraftTeam.reserve_time_remaining — the team's cumulative
            # reserve in the DB. Stable between picks; server debits
            # `max(0, round_elapsed - grace)` at pick submission, so the
            # next round's broadcast carries the lower value forward.
            # The client subtracts the IN-ROUND consumption locally for
            # display on the active team only.
            "team_a_id": team_a.id if team_a else None,
            "team_a_reserve_ms": (team_a.reserve_time_remaining if team_a else None),
            "team_b_id": team_b.id if team_b else None,
            "team_b_reserve_ms": (team_b.reserve_time_remaining if team_b else None),
        }

    tick_data = await get_tick_data()
    if tick_data:
        try:
            await channel_layer.group_send(room_group_name, tick_data)
        except Exception as e:
            log.error(
                "tick_broadcast_failed",
                system="herodraft",
                subsystem="timer",
                draft_id=draft_id,
                error=str(e),
            )


async def check_timeout(draft_id: int) -> HeroDraftRound | None:
    """Check if current round has timed out and auto-pick if needed."""
    from django.db import transaction

    from app.broadcast import broadcast_herodraft_state
    from app.functions.herodraft import auto_random_pick
    from app.models import DraftTeam, HeroDraft, HeroDraftState

    @database_sync_to_async
    def check_and_auto_pick():
        # Use transaction with select_for_update to prevent race conditions
        completed_round = None

        with transaction.atomic():
            try:
                draft = HeroDraft.objects.select_for_update().get(id=draft_id)
            except HeroDraft.DoesNotExist:
                return None

            if draft.state != HeroDraftState.DRAFTING:
                return None

            current_round = (
                draft.rounds.select_for_update().filter(state="active").first()
            )
            if not current_round:
                return None

            now = timezone.now()
            if not current_round.started_at:
                return None

            elapsed_ms = int((now - current_round.started_at).total_seconds() * 1000)

            # Lock the team to ensure reserve_time_remaining is consistent
            team = DraftTeam.objects.select_for_update().get(
                id=current_round.draft_team_id
            )
            total_time = current_round.grace_time_ms + team.reserve_time_remaining

            if elapsed_ms >= total_time:
                # Time's up - auto pick
                log.info(
                    "timeout_auto_pick",
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                    round=current_round.round_number,
                    elapsed_ms=elapsed_ms,
                    total_time_ms=total_time,
                )
                completed_round = auto_random_pick(draft, team)

        # Broadcast AFTER transaction commits so clients see the updated state
        # Use broadcast_herodraft_state to avoid creating duplicate events
        # (submit_pick already creates the hero_selected event)
        if completed_round:
            try:
                # Re-fetch draft to get committed state with prefetched relations
                draft = HeroDraft.objects.prefetch_related(
                    "draft_teams__tournament_team__captain",
                    "draft_teams__tournament_team__members",
                    "rounds",
                ).get(id=draft_id)
                broadcast_herodraft_state(draft, "hero_selected")
                log.debug(
                    "timeout_auto_pick_broadcast",
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                )
            except Exception as e:
                log.error(
                    "timeout_auto_pick_broadcast_failed",
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                    error=str(e),
                )

        return completed_round

    return await check_and_auto_pick()


async def check_resume_countdown(draft_id: int) -> bool:
    """Check if RESUMING countdown is complete and transition to DRAFTING."""
    from django.db import transaction

    from app.broadcast import broadcast_herodraft_state
    from app.models import HeroDraft, HeroDraftEvent, HeroDraftState

    @database_sync_to_async
    def check_and_resume():
        transitioned = False

        with transaction.atomic():
            try:
                draft = HeroDraft.objects.select_for_update().get(id=draft_id)
            except HeroDraft.DoesNotExist:
                return False

            if draft.state != HeroDraftState.RESUMING:
                return False

            now = timezone.now()
            if not draft.resuming_until or now < draft.resuming_until:
                return False

            # Countdown complete - transition to DRAFTING
            draft.state = HeroDraftState.DRAFTING
            draft.resuming_until = None
            draft.save()
            HeroDraftEvent.objects.create(
                draft=draft,
                event_type="draft_resumed",
                metadata={},
            )
            log.info(
                "draft_resumed",
                system="herodraft",
                subsystem="timer",
                draft_id=draft_id,
            )
            transitioned = True

        # Broadcast AFTER transaction commits
        if transitioned:
            try:
                draft = HeroDraft.objects.prefetch_related(
                    "draft_teams__tournament_team__captain",
                    "draft_teams__tournament_team__members",
                    "rounds",
                ).get(id=draft_id)
                broadcast_herodraft_state(draft, "draft_resumed")
                log.debug(
                    "draft_resumed_broadcast",
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                )
            except Exception as e:
                log.error(
                    "draft_resumed_broadcast_failed",
                    system="herodraft",
                    subsystem="timer",
                    draft_id=draft_id,
                    error=str(e),
                )

        return transitioned

    return await check_and_resume()


async def check_captain_heartbeats(draft_id: int) -> str | None:
    """Check if any captain's heartbeat is stale and trigger disconnect if so."""
    from django.db import transaction

    from app.broadcast import broadcast_herodraft_state
    from app.models import DraftTeam, HeroDraft, HeroDraftEvent, HeroDraftState

    @database_sync_to_async
    def check_and_handle_stale():
        r = get_redis_client()
        now = time.time()
        stale_captain = None

        try:
            draft = HeroDraft.objects.prefetch_related(
                "draft_teams__tournament_team__captain"
            ).get(id=draft_id)
        except HeroDraft.DoesNotExist:
            return None

        # Only check during DRAFTING (not PAUSED, RESUMING, etc.)
        if draft.state != HeroDraftState.DRAFTING:
            return None

        # Check each captain's heartbeat
        for draft_team in draft.draft_teams.all():
            captain = draft_team.tournament_team.captain
            if not captain:
                continue

            heartbeat_key = CAPTAIN_HEARTBEAT_KEY.format(
                draft_id=draft_id, user_id=captain.id
            )
            last_heartbeat = r.get(heartbeat_key)

            if last_heartbeat is None:
                # No heartbeat recorded - captain may not have connected yet
                # or heartbeat expired (30s TTL)
                if draft_team.is_connected:
                    log.warning(
                        "heartbeat_missing",
                        system="herodraft",
                        subsystem="heartbeat",
                        draft_id=draft_id,
                        user_id=captain.id,
                        username=captain.username,
                        is_connected=True,
                        reason="no_heartbeat_key",
                    )
                    stale_captain = (draft_team, captain)
                    break
            else:
                heartbeat_age = now - float(last_heartbeat)
                if heartbeat_age > HEARTBEAT_STALE_SECONDS:
                    log.warning(
                        "heartbeat_stale",
                        system="herodraft",
                        subsystem="heartbeat",
                        draft_id=draft_id,
                        user_id=captain.id,
                        username=captain.username,
                        heartbeat_age_s=round(heartbeat_age, 1),
                        threshold_s=HEARTBEAT_STALE_SECONDS,
                    )
                    stale_captain = (draft_team, captain)
                    break

        if not stale_captain:
            return None

        draft_team, captain = stale_captain

        # Trigger disconnect handling
        with transaction.atomic():
            draft = HeroDraft.objects.select_for_update().get(id=draft_id)
            if draft.state != HeroDraftState.DRAFTING:
                return None

            draft_team = DraftTeam.objects.select_for_update().get(id=draft_team.id)
            draft_team.is_connected = False
            draft_team.save()

            draft.state = HeroDraftState.PAUSED
            draft.paused_at = timezone.now()
            draft.save()

            HeroDraftEvent.objects.create(
                draft=draft,
                event_type="captain_disconnected",
                draft_team=draft_team,
                metadata={
                    "user_id": captain.id,
                    "username": captain.username,
                    "reason": "heartbeat_stale",
                },
            )
            HeroDraftEvent.objects.create(
                draft=draft,
                event_type="draft_paused",
                draft_team=draft_team,
                metadata={"reason": "heartbeat_stale"},
            )
            log.info(
                "heartbeat_triggered_pause",
                system="herodraft",
                subsystem="heartbeat",
                draft_id=draft_id,
                user_id=captain.id,
                username=captain.username,
            )

        # Broadcast after transaction commits
        try:
            draft = HeroDraft.objects.prefetch_related(
                "draft_teams__tournament_team__captain",
                "draft_teams__tournament_team__members",
                "rounds",
            ).get(id=draft_id)
            broadcast_herodraft_state(draft, "draft_paused", draft_team=draft_team)
        except Exception as e:
            log.error(
                "heartbeat_broadcast_failed",
                system="herodraft",
                subsystem="heartbeat",
                draft_id=draft_id,
                error=str(e),
            )

        return captain.username

    return await check_and_handle_stale()


def should_continue_ticking(draft_id: int, r: redis.Redis) -> tuple[bool, str]:
    """
    Check if tick loop should continue.

    Returns:
        tuple: (should_continue, reason_if_stopping)
    """
    from app.models import HeroDraft, HeroDraftState

    # Check draft state first - allow DRAFTING and RESUMING (countdown before resume)
    try:
        draft = HeroDraft.objects.get(id=draft_id)
        if draft.state not in (HeroDraftState.DRAFTING, HeroDraftState.RESUMING):
            return False, f"draft_state_{draft.state}"
    except HeroDraft.DoesNotExist:
        return False, "draft_not_found"

    # RESUMING countdown must complete regardless of connection count,
    # because admins resume via REST API and clients may reconnect after.
    if draft.state == HeroDraftState.RESUMING:
        return True, ""

    # For DRAFTING, stop if no WebSocket clients are connected
    conn_count = get_connection_count(draft_id)
    if conn_count <= 0:
        return False, "no_connections"

    return True, ""


class HeroDraftTickDriver:
    prefix: str = "herodraft"
    system: str = "herodraft"

    async def check_resume_countdown(self, draft_id: int) -> None:
        await check_resume_countdown(draft_id)

    async def check_captain_heartbeats(self, draft_id: int) -> None:
        await check_captain_heartbeats(draft_id)

    async def broadcast_tick(self, draft_id: int) -> None:
        await broadcast_tick(draft_id)

    async def check_timeout(self, draft_id: int) -> None:
        await check_timeout(draft_id)

    def should_continue(self, draft_id: int) -> tuple[bool, str]:
        return should_continue_ticking(draft_id, get_redis_client())


HERO_TICK_DRIVER: HeroDraftTickDriver = HeroDraftTickDriver()


async def run_tick_loop(draft_id: int, stop_event: threading.Event) -> None:
    await draft_tick.run_tick_loop(HERO_TICK_DRIVER, draft_id, stop_event)


def start_tick_broadcaster(draft_id: int) -> bool:
    return draft_tick.start_tick_broadcaster(HERO_TICK_DRIVER, draft_id)


def stop_tick_broadcaster(draft_id: int) -> None:
    draft_tick.stop_tick_broadcaster("herodraft", draft_id)


def stop_all_broadcasters() -> None:
    draft_tick.stop_all_broadcasters()
