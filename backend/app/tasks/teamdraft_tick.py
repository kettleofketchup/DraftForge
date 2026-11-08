"""Team-draft tick driver bound to the shared runner in app.tasks.draft_tick."""

import time
from datetime import datetime

import redis
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from app.cache_utils import invalidate_after_commit
from app.functions.teamdraft import emit_event, team_for_round, team_payload
from app.functions.teamdraft_timeout import TIMEOUT_ACTIONS
from app.models import Draft, DraftRound, Team, TeamDraftState
from app.tasks import draft_tick
from app.tasks.draft_tick import (
    CAPTAIN_CHANNEL_TTL,
    HEARTBEAT_STALE_SECONDS,
    get_connection_count,
    get_redis_client,
    heartbeat_key,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

PREFIX: str = "teamdraft"

__all__ = [
    "CAPTAIN_CHANNEL_TTL",
    "PREFIX",
    "TEAM_TICK_DRIVER",
    "TeamDraftTickDriver",
    "broadcast_tick",
    "build_tick_payload",
    "captain_conn_key",
    "captain_is_fresh",
    "check_captain_heartbeats",
    "check_resume_countdown",
    "check_timeout",
    "get_connection_count",
    "read_timeout_candidate",
    "should_continue_ticking",
    "start_team_tick_broadcaster_after_commit",
]

_ARMED_STATES: frozenset[str] = frozenset(
    {TeamDraftState.DRAFTING, TeamDraftState.RESUMING}
)


def captain_conn_key(draft_id: int, user_id: int) -> str:
    return f"{PREFIX}:{draft_id}:captain:{user_id}:conns"


def captain_is_fresh(
    r: redis.Redis, draft_id: int, user_id: int, now_ts: float
) -> bool:
    value = r.get(heartbeat_key(PREFIX, draft_id, user_id))
    if value is None:
        return False
    return now_ts - float(value) <= HEARTBEAT_STALE_SECONDS


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def build_tick_payload(draft: Draft, now: datetime, r: redis.Redis) -> dict | None:
    if not draft.clock_armed:
        return None
    active = draft.active_round
    if active is None:
        return None
    active_team = team_for_round(draft, active)
    now_ts = now.timestamp()
    teams = Team.objects.filter(tournament=draft.tournament).order_by("draft_order")
    return {
        "type": "draft.tick",
        "draft_state": draft.state,
        "server_time": now.isoformat(),
        "resuming_until": _iso(draft.resuming_until),
        "active_round_pk": active.pk,
        "active_pick_number": active.pick_number,
        "active_captain_id": active.captain_id,
        "active_team_id": active_team.pk if active_team else None,
        "round_started_at": _iso(active.started_at),
        "round_timed_out_at": _iso(active.timed_out_at),
        "round_grace_time_ms": active.grace_time_ms,
        "teams": [
            {
                "team_id": t.pk,
                "captain_id": t.captain_id,
                "reserve_ms": t.draft_reserve_ms,
                "is_connected": t.captain_id is not None
                and captain_is_fresh(r, draft.pk, t.captain_id, now_ts),
                "is_ready": t.draft_is_ready,
            }
            for t in teams
        ],
    }


def should_continue_ticking(draft_id: int) -> tuple[bool, str]:
    draft = Draft.objects.filter(pk=draft_id).first()
    if draft is None:
        return False, "draft_not_found"
    if draft.state not in _ARMED_STATES:
        return False, f"draft_state_{draft.state}"
    if not draft.clock_armed:
        return False, "clock_unarmed"
    if draft.state == TeamDraftState.RESUMING:
        return True, ""
    if get_connection_count(PREFIX, draft_id) <= 0:
        return False, "no_connections"
    return True, ""


async def broadcast_tick(draft_id: int) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    @database_sync_to_async
    def get_tick_data() -> dict | None:
        draft = Draft.objects.filter(pk=draft_id).first()
        if draft is None:
            return None
        return build_tick_payload(draft, timezone.now(), get_redis_client())

    payload = await get_tick_data()
    if payload is None:
        return
    try:
        await channel_layer.group_send(f"draft_{draft_id}", payload)
        log.debug(
            "tick_broadcast",
            system="teamdraft",
            subsystem="timer",
            draft_id=draft_id,
            server_time=payload["server_time"],
        )
    except Exception as e:
        log.error(
            "tick_broadcast_failed",
            system="teamdraft",
            subsystem="timer",
            draft_id=draft_id,
            error=str(e),
        )


async def check_resume_countdown(draft_id: int) -> bool:
    @database_sync_to_async
    def flip() -> bool:
        with transaction.atomic():
            draft = Draft.objects.select_for_update().filter(pk=draft_id).first()
            if draft is None or draft.state != TeamDraftState.RESUMING:
                return False
            if draft.resuming_until is None or timezone.now() < draft.resuming_until:
                return False
            draft.state = TeamDraftState.DRAFTING
            draft.resuming_until = None
            draft.save(update_fields=["state", "resuming_until"])
            log.info(
                "draft_resumed",
                system="teamdraft",
                subsystem="timer",
                draft_id=draft_id,
            )
            return True

    return await flip()


async def check_captain_heartbeats(draft_id: int) -> str | None:
    @database_sync_to_async
    def check_and_pause() -> str | None:
        draft = (
            Draft.objects.filter(pk=draft_id)
            .prefetch_related("tournament__teams__captain")
            .first()
        )
        if draft is None or draft.state != TeamDraftState.DRAFTING:
            return None
        if not draft.clock_armed:
            return None
        rnd = draft.active_round
        if rnd is None:
            return None
        team = team_for_round(draft, rnd)
        captain = team.captain if team else None
        if team is None or captain is None:
            return None

        value = get_redis_client().get(heartbeat_key(PREFIX, draft_id, captain.pk))
        if value is None:
            if not team.draft_has_connected:
                return None
            log.warning(
                "heartbeat_missing",
                system="teamdraft",
                subsystem="heartbeat",
                draft_id=draft_id,
                user_id=captain.pk,
                reason="no_heartbeat_key",
            )
        else:
            age = time.time() - float(value)
            if age <= HEARTBEAT_STALE_SECONDS or not team.draft_has_connected:
                return None
            log.warning(
                "heartbeat_stale",
                system="teamdraft",
                subsystem="heartbeat",
                draft_id=draft_id,
                user_id=captain.pk,
                heartbeat_age_s=round(age, 1),
                threshold_s=HEARTBEAT_STALE_SECONDS,
            )

        with transaction.atomic():
            locked = Draft.objects.select_for_update().get(pk=draft_id)
            active = locked.lock_active_round()
            options = locked.tournament.get_draft_options(fresh=True)
            armed = (
                options.timer_enabled
                and locked.state in _ARMED_STATES
                and active is not None
                and active.started_at is not None
            )
            if (
                not armed
                or locked.state != TeamDraftState.DRAFTING
                or active is None
                or active.pk != rnd.pk
            ):
                return None
            locked.state = TeamDraftState.PAUSED
            locked.paused_at = timezone.now()
            locked.is_manual_pause = False
            locked.save(update_fields=["state", "paused_at", "is_manual_pause"])
            emit_event(
                locked,
                "draft_paused",
                {
                    "reason": "captain_disconnected",
                    "paused_by_id": None,
                    "paused_by_name": None,
                    **team_payload(team),
                },
            )
            log.info(
                "heartbeat_triggered_pause",
                system="teamdraft",
                subsystem="heartbeat",
                draft_id=draft_id,
                user_id=captain.pk,
            )
        return captain.username

    return await check_and_pause()


def read_timeout_candidate(draft_id: int) -> tuple[int, datetime] | None:
    draft = Draft.objects.filter(pk=draft_id).first()
    if draft is None or not draft.clock_armed:
        return None
    active = draft.active_round
    if active is None or active.timed_out_at is not None or active.started_at is None:
        return None
    return active.pk, active.started_at


def _check_timeout_sync(draft_id: int) -> DraftRound | None:
    seen = read_timeout_candidate(draft_id)
    if seen is None:
        return None
    round_pk_seen, started_at_seen = seen

    with transaction.atomic():
        draft = Draft.objects.select_for_update().filter(pk=draft_id).first()
        if draft is None:
            return None
        rnd = draft.lock_active_round()
        if rnd is None:
            return None
        team = (
            Team.objects.nocache()
            .select_for_update()
            .filter(tournament=draft.tournament, captain_id=rnd.captain_id)
            .first()
        )
        options = draft.tournament.get_draft_options(fresh=True)
        armed = (
            options.timer_enabled
            and draft.state in _ARMED_STATES
            and rnd.started_at is not None
        )
        if (
            team is None
            or not armed
            or rnd.pk != round_pk_seen
            or rnd.choice_id is not None
            or rnd.timed_out_at is not None
            or rnd.started_at != started_at_seen
        ):
            return None

        now = timezone.now()
        pool = (
            team.draft_reserve_ms
            if team.draft_reserve_ms is not None
            else options.reserve_time_ms
        )
        grace = (
            rnd.grace_time_ms
            if rnd.grace_time_ms is not None
            else options.grace_time_ms
        )
        elapsed_ms = int((now - rnd.started_at).total_seconds() * 1000)
        if elapsed_ms < grace + pool:
            return None

        over = max(0, elapsed_ms - grace)
        used = min(over, pool)
        rnd.pick_duration_ms = (rnd.pick_duration_ms or 0) + elapsed_ms
        rnd.reserve_used_ms = (rnd.reserve_used_ms or 0) + used
        rnd.timed_out_at = now
        team.draft_reserve_ms = 0
        team.save(update_fields=["draft_reserve_ms"])
        invalidate_after_commit(team.tournament)
        rnd.save(update_fields=["pick_duration_ms", "reserve_used_ms", "timed_out_at"])
        emit_event(
            draft,
            "pick_timed_out",
            {
                "pick_number": rnd.pick_number,
                **team_payload(team),
                "elapsed_ms": elapsed_ms,
                "reserve_used_ms": used,
            },
        )
        log.info(
            "timeout_skip",
            system="teamdraft",
            subsystem="timer",
            draft_id=draft_id,
            action=options.timeout_action,
            pick_number=rnd.pick_number,
            elapsed_ms=elapsed_ms,
        )
        return TIMEOUT_ACTIONS[options.timeout_action](draft, rnd)


async def check_timeout(draft_id: int) -> DraftRound | None:
    return await database_sync_to_async(_check_timeout_sync)(draft_id)


class TeamDraftTickDriver:
    prefix: str = PREFIX
    system: str = "teamdraft"

    async def check_resume_countdown(self, draft_id: int) -> None:
        await check_resume_countdown(draft_id)

    async def check_captain_heartbeats(self, draft_id: int) -> None:
        await check_captain_heartbeats(draft_id)

    async def broadcast_tick(self, draft_id: int) -> None:
        await broadcast_tick(draft_id)

    async def check_timeout(self, draft_id: int) -> None:
        await check_timeout(draft_id)

    def should_continue(self, draft_id: int) -> tuple[bool, str]:
        return should_continue_ticking(draft_id)


TEAM_TICK_DRIVER: TeamDraftTickDriver = TeamDraftTickDriver()


def start_team_tick_broadcaster_after_commit(draft_id: int) -> None:
    transaction.on_commit(
        lambda: draft_tick.start_tick_broadcaster(TEAM_TICK_DRIVER, draft_id)
    )
