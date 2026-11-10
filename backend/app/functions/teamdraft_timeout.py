"""Team-draft timeout actions (spec §2)."""

from collections.abc import Callable

from django.utils import timezone

from app.functions.shuffle_draft import reassign_round_captain
from app.functions.teamdraft import (
    activate_round,
    emit_event,
    team_for_round,
    team_payload,
)
from app.models import Draft, DraftRound, Team, TimeoutAction
from telemetry.logging import get_logger

log = get_logger(__name__)

TimeoutActionFn = Callable[[Draft, DraftRound], DraftRound | None]


def recompute_pick_phase(pick_number: int, num_teams: int) -> int:
    return (pick_number - 1) // num_teams + 1


def find_swap_target(draft: Draft, round: DraftRound) -> DraftRound | None:
    return (
        draft.draft_rounds.select_for_update()
        .nocache()
        .filter(choice__isnull=True, pick_number__gt=round.pick_number)
        .exclude(captain_id=round.captain_id)
        .order_by("pick_number")
        .first()
    )


def _unavailable(draft: Draft, round: DraftRound, team: Team | None) -> None:
    emit_event(
        draft,
        "pick_skip_unavailable",
        {"pick_number": round.pick_number, **team_payload(team)},
    )
    log.info(
        "timeout_skip_unavailable",
        system="teamdraft",
        subsystem="timer",
        draft_id=draft.pk,
        pick_number=round.pick_number,
    )


def skip_turn(draft: Draft, round: DraftRound) -> DraftRound | None:
    team = team_for_round(draft, round)
    options = draft.tournament.get_draft_options(fresh=True)
    skipped: dict[str, int] = {
        "pick_duration_ms": round.pick_duration_ms or 0,
        "reserve_used_ms": round.reserve_used_ms or 0,
    }
    old_number = round.pick_number

    if draft.draft_style == "shuffle":
        if team is None:
            _unavailable(draft, round, team)
            return None
        reassign_round_captain(draft, round, {team.pk}, reason="timeout_skip")
        if round.captain_id == team.captain_id:
            _unavailable(draft, round, team)
            return None
        round.skip_count += 1
        round.pick_duration_ms = 0
        round.reserve_used_ms = 0
        round.timed_out_at = None
        round.save(
            update_fields=[
                "skip_count",
                "pick_duration_ms",
                "reserve_used_ms",
                "timed_out_at",
            ]
        )
        emit_event(
            draft,
            "pick_skipped",
            {
                "pick_number": old_number,
                **team_payload(team, "skipped"),
                **team_payload(team_for_round(draft, round), "next"),
                "from_pick_number": old_number,
                "to_pick_number": old_number,
                "deferred_to_pick_number": None,
                **skipped,
            },
        )
        activate_round(draft, round, options, now=timezone.now(), armed=True)
        log.info(
            "timeout_skip",
            system="teamdraft",
            subsystem="timer",
            draft_id=draft.pk,
            pick_number=old_number,
            style="shuffle",
        )
        return round

    target = find_swap_target(draft, round)
    if target is None:
        _unavailable(draft, round, team)
        return None
    num_teams = draft.tournament.teams.count()
    round.pick_number, target.pick_number = target.pick_number, round.pick_number
    round.pick_phase = recompute_pick_phase(round.pick_number, num_teams)
    target.pick_phase = recompute_pick_phase(target.pick_number, num_teams)
    round.skip_count += 1
    round.started_at = round.timed_out_at = None
    round.save()
    target.save()
    emit_event(
        draft,
        "pick_skipped",
        {
            "pick_number": round.pick_number,
            **team_payload(team, "skipped"),
            **team_payload(team_for_round(draft, target), "next"),
            "from_pick_number": old_number,
            "to_pick_number": target.pick_number,
            "deferred_to_pick_number": round.pick_number,
            **skipped,
        },
    )
    activate_round(draft, target, options, now=timezone.now(), armed=True)
    log.info(
        "timeout_skip",
        system="teamdraft",
        subsystem="timer",
        draft_id=draft.pk,
        from_pick_number=old_number,
        deferred_to_pick_number=round.pick_number,
        style="snake",
    )
    return target


TIMEOUT_ACTIONS: dict[str, TimeoutActionFn] = {
    TimeoutAction.SKIP_TURN.value: skip_turn
}
