"""Team-draft timer lifecycle helpers (spec §2)."""

from datetime import datetime

from django.db import transaction

from app.broadcast import broadcast_event
from app.cache_utils import invalidate_after_commit
from app.models import (
    CustomUser,
    Draft,
    DraftEvent,
    DraftOptions,
    DraftRound,
    Team,
    TeamDraftState,
    Tournament,
)
from telemetry.logging import get_logger

log = get_logger(__name__)

RESUME_COUNTDOWN_SECONDS: int = 3

_TIMER_OFF_STATES: frozenset[str] = frozenset(
    {
        TeamDraftState.PENDING,
        TeamDraftState.PAUSED,
        TeamDraftState.RESUMING,
        TeamDraftState.DRAFTING,
    }
)


def team_payload(team: Team | None, role: str = "") -> dict:
    p = f"{role}_" if role else ""
    captain = team.captain if team is not None else None
    if team is None or captain is None:
        return {
            f"{p}captain_id": None,
            f"{p}captain_name": None,
            f"{p}captain_avatar_url": None,
            f"{p}team_id": None,
            f"{p}team_name": None,
        }
    return {
        f"{p}captain_id": captain.pk,
        f"{p}captain_name": captain.username,
        f"{p}captain_avatar_url": captain.avatarUrl,
        f"{p}team_id": team.pk,
        f"{p}team_name": team.name,
    }


def emit_event(
    draft: Draft,
    event_type: str,
    payload: dict,
    actor: CustomUser | None = None,
) -> DraftEvent:
    if "pick_number" not in payload:
        lowest = (
            draft.draft_rounds.nocache()
            .filter(choice__isnull=True)
            .order_by("pick_number")
            .first()
        )
        payload["pick_number"] = lowest.pick_number if lowest else None
    event = DraftEvent.objects.create(
        draft=draft, event_type=event_type, payload=payload, actor=actor
    )
    transaction.on_commit(lambda e=event: broadcast_event(e))
    log.info(
        "draft_event_emitted",
        system="teamdraft",
        subsystem="timer",
        event_type=event_type,
        draft_id=draft.pk,
    )
    return event


def team_for_round(draft: Draft, round: DraftRound) -> Team | None:
    return Team.objects.filter(
        tournament=draft.tournament, captain_id=round.captain_id
    ).first()


def activate_round(
    draft: Draft,
    round: DraftRound,
    options: DraftOptions,
    *,
    now: datetime,
    armed: bool = True,
) -> None:
    round.started_at = now if armed else None
    round.timed_out_at = None
    round.grace_time_ms = options.grace_time_ms
    round.save(update_fields=["started_at", "timed_out_at", "grace_time_ms"])
    if armed:
        team = team_for_round(draft, round)
        emit_event(
            draft,
            "round_started",
            {
                "pick_number": round.pick_number,
                **team_payload(team),
                "started_at": now.isoformat(),
                "grace_time_ms": options.grace_time_ms,
                "reserve_ms": team.draft_reserve_ms if team else None,
            },
        )


def seed_missing_reserve_pools(draft: Draft, options: DraftOptions) -> None:
    for team in Team.objects.select_for_update().filter(
        tournament=draft.tournament, draft_reserve_ms__isnull=True
    ):
        team.draft_reserve_ms = options.reserve_time_ms
        team.save(update_fields=["draft_reserve_ms"])
    invalidate_after_commit(draft.tournament)


def start_draft(draft: Draft, options: DraftOptions, *, now: datetime) -> DraftRound:
    draft.state = TeamDraftState.DRAFTING
    draft.save(update_fields=["state"])
    seed_missing_reserve_pools(draft, options)
    first = draft.lock_active_round()
    activate_round(draft, first, options, now=now, armed=True)
    return first


def record_pick_timing(
    round: DraftRound,
    team: Team,
    *,
    completed_at: datetime,
    effective_pick_time: datetime,
    default_reserve_ms: int = 0,
) -> None:
    if round.started_at is None:
        return
    if round.timed_out_at is not None:
        round.completed_at = completed_at
        round.save(update_fields=["completed_at"])
        log.info(
            "pick_after_timeout",
            system="teamdraft",
            subsystem="timer",
            draft_id=round.draft_id,
            pick_number=round.pick_number,
        )
        return
    if team.draft_reserve_ms is not None:
        pool = team.draft_reserve_ms
    else:
        pool = default_reserve_ms
        log.warning(
            "reserve_pool_missing",
            system="teamdraft",
            subsystem="timer",
            team_id=team.pk,
        )
    duration = max(
        0, int((effective_pick_time - round.started_at).total_seconds() * 1000)
    )
    grace = round.grace_time_ms or 0
    over = min(max(0, duration - grace), pool)
    round.pick_duration_ms = (round.pick_duration_ms or 0) + duration
    round.reserve_used_ms = (round.reserve_used_ms or 0) + over
    round.completed_at = completed_at
    team.draft_reserve_ms = pool - over
    round.save(update_fields=["pick_duration_ms", "reserve_used_ms", "completed_at"])
    team.save(update_fields=["draft_reserve_ms"])
    invalidate_after_commit(team.tournament)
    log.info(
        "pick_timed",
        system="teamdraft",
        subsystem="timer",
        draft_id=round.draft_id,
        pick_number=round.pick_number,
        pick_duration_ms=duration,
        reserve_used_ms=over,
        reserve_left_ms=team.draft_reserve_ms,
    )


def complete_draft(draft: Draft) -> None:
    draft.state = TeamDraftState.COMPLETED
    draft.paused_at = None
    draft.resuming_until = None
    draft.save(update_fields=["state", "paused_at", "resuming_until"])
    emit_event(
        draft,
        "draft_completed",
        {
            "draft_id": draft.pk,
            "draft_style": draft.draft_style,
            "team_count": draft.tournament.teams.count(),
        },
    )


def advance_after_pick(
    draft: Draft, options: DraftOptions, *, now: datetime, activate: bool
) -> DraftRound | None:
    nxt = draft.lock_active_round()
    if nxt is None:
        complete_draft(draft)
        return None
    if activate:
        activate_round(
            draft,
            nxt,
            options,
            now=now,
            armed=draft.state == TeamDraftState.DRAFTING,
        )
    return nxt


def apply_draft_options(tournament: Tournament, data: dict) -> DraftOptions:
    with transaction.atomic():
        draft = Draft.objects.select_for_update().filter(tournament=tournament).first()
        opts = tournament.get_draft_options(fresh=True)
        was_enabled = opts.timer_enabled
        for key, value in data.items():
            setattr(opts, key, value)
        opts.save()
        if draft is None:
            return opts
        if draft.state == TeamDraftState.PENDING and (
            "grace_time_ms" in data or "reserve_time_ms" in data
        ):
            for team in Team.objects.select_for_update().filter(tournament=tournament):
                team.draft_reserve_ms = opts.reserve_time_ms
                team.save(update_fields=["draft_reserve_ms"])
        if (
            was_enabled
            and not opts.timer_enabled
            and draft.state in _TIMER_OFF_STATES
        ):
            from_state = draft.state
            was_paused = from_state in (TeamDraftState.PAUSED, TeamDraftState.RESUMING)
            draft.state = TeamDraftState.DRAFTING
            draft.paused_at = None
            draft.resuming_until = None
            draft.is_manual_pause = False
            draft.save(
                update_fields=["state", "paused_at", "resuming_until", "is_manual_pause"]
            )
            rnd = draft.lock_active_round()
            if rnd is not None:
                rnd.started_at = None
                rnd.timed_out_at = None
                rnd.save(update_fields=["started_at", "timed_out_at"])
            if was_paused:
                emit_event(
                    draft,
                    "draft_resumed",
                    {
                        "resumed_by_id": None,
                        "resumed_by_name": None,
                        "resuming_until": None,
                    },
                )
            log.info(
                "timer_disabled_transition",
                system="teamdraft",
                subsystem="timer",
                draft_id=draft.pk,
                from_state=from_state,
            )
        invalidate_after_commit(tournament, draft)
        return opts
