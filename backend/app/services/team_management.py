"""Staff roster service: every team change runs through one audited pipeline."""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from django.db import transaction
from django.db.models import Q

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser, Team, TeamLog, TeamLogAction, TeamLogVia
from app.services.team_audit import (
    log_snapshot_fields,
    roster_snapshot,
    source_event,
    write_team_log,
)
from app.services.team_signals import (
    change_from_log,
    owning_team_audit,
    send_roster_changed_on_commit,
)
from events.overrides import (
    OverrideReasonRequired,
    OverrideRequired,
    Violation,
    check_overrides,
)
from org.models import OrgSettings
from org.settings_service import get_org_settings
from telemetry.logging import get_logger

log = get_logger(__name__)

DEFAULT_MAX_STANDINS: int = 2
NAME_MAX_LENGTH: int = 255

LeadershipKey = Literal["captain", "deputy_captain"]
Validate = Callable[[Team], Iterable[Violation]]
Mutate = Callable[[Team], dict[str, Any] | None]
UsersOf = Callable[[Team], Iterable[CustomUser | None]]
UserOf = Callable[[Team], CustomUser | None]


class TeamManagementError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code: str = code
        self.message: str = message


@dataclass(frozen=True)
class TeamChange:
    team: Team
    log: TeamLog
    overridden: list[str]


def standin_cap(team: Team) -> int:
    cap = getattr(source_event(team.tournament), "team_max_standins", None)
    return cap if cap is not None else DEFAULT_MAX_STANDINS


def _other_team_user_ids(team: Team) -> set[int]:
    if team.tournament_id is None:
        return set()
    others = Team.objects.filter(tournament_id=team.tournament_id).exclude(pk=team.pk)
    return set(
        CustomUser.objects.nocache()
        .filter(Q(teams_as_member__in=others) | Q(teams_as_dropin__in=others))
        .values_list("pk", flat=True)
        .distinct()
    )


def _problem_pairs(snapshot: dict[str, Any]) -> set[tuple[str, str]]:
    problems = Team.leadership_problems(
        set(snapshot["member_ids"]),
        snapshot["captain_id"],
        snapshot["deputy_captain_id"],
    )
    return {(key, str(problem)) for key, problem in problems.items()}


def _org_settings(team: Team) -> OrgSettings | None:
    tournament = team.tournament
    league = tournament.league if tournament is not None else None
    if league is None or league.organization_id is None:
        return None
    return get_org_settings(league.organization_id)


def _is_member(team: Team, user: CustomUser) -> bool:
    return team.members.nocache().filter(pk=user.pk).exists()


def _is_standin(team: Team, user: CustomUser) -> bool:
    return team.dropin_members.nocache().filter(pk=user.pk).exists()


def _is_dropout(team: Team, user: CustomUser) -> bool:
    return team.left_members.nocache().filter(pk=user.pk).exists()


def _apply(
    team: Team,
    action: TeamLogAction,
    *,
    actor: CustomUser | None,
    via: TeamLogVia,
    reason: str,
    acknowledged_codes: Collection[str],
    target_user: UserOf,
    affected_users: UsersOf,
    validate: Validate,
    mutate: Mutate,
    touched: Collection[LeadershipKey],
) -> TeamChange:
    reason = (reason or "").strip()
    fields: dict[str, Any] = {
        "system": "tournament",
        "subsystem": "teams",
        "team_id": team.pk,
        "action": str(action),
        "via": str(via),
        "actor_id": actor.pk if actor is not None else None,
    }
    try:
        with transaction.atomic(), owning_team_audit():
            locked = (
                Team.objects.nocache()
                .select_for_update()
                .select_related("tournament__league")
                .get(pk=team.pk)
            )
            before = roster_snapshot(locked)
            pairs_before = _problem_pairs(before)

            violations = list(validate(locked))
            affected = [u for u in affected_users(locked) if u is not None]
            target = target_user(locked)
            if (
                via != TeamLogVia.SYSTEM
                and not reason
                and any(actor is None or u.pk != actor.pk for u in affected)
            ):
                raise TeamManagementError(
                    "reason_required",
                    "A reason is required when changing another player's team.",
                )
            overridden = check_overrides(
                violations,
                org_settings=_org_settings(locked),
                acknowledged=acknowledged_codes,
                reason=reason,
            )

            extras = mutate(locked) or {}

            changed = (
                Team.objects.nocache()
                .select_related("tournament__league")
                .get(pk=locked.pk)
            )
            after = roster_snapshot(changed)
            pairs_after = _problem_pairs(after)
            new_pairs = pairs_after - pairs_before
            dirty = sorted(key for key, _ in pairs_after if key in set(touched))
            if new_pairs or dirty:
                log.error(
                    "team_change_invariant_failed",
                    **fields,
                    new_problems=sorted(f"{k}:{p}" for k, p in new_pairs),
                    dirty_keys=dirty,
                )
                raise TeamManagementError(
                    "leadership_invariant",
                    "This change would leave the team's captain or deputy invalid.",
                )

            details: dict[str, Any] = {"before": before, "after": after, **extras}
            if overridden:
                details["violations"] = [
                    v.as_dict() for v in violations if v.code in overridden
                ]
            team_log = write_team_log(
                changed,
                snapshot=log_snapshot_fields(changed),
                action=action,
                via=via,
                actor=actor,
                target_user=target,
                reason=reason,
                override_rules=overridden,
                details=details,
            )
            to_invalidate: list[Any] = [changed, *affected]
            if changed.tournament is not None:
                to_invalidate.append(changed.tournament)
            invalidate_after_commit(*to_invalidate)
            send_roster_changed_on_commit(change_from_log(team_log))
    except TeamManagementError as exc:
        log.info("team_change_refused", **fields, code=exc.code)
        raise
    except OverrideRequired as exc:
        log.info(
            "team_override_required",
            **fields,
            codes=[v.code for v in exc.violations],
        )
        raise
    except OverrideReasonRequired:
        log.info("team_change_refused", **fields, code="override_reason_required")
        raise

    log.info(
        "team_change_applied",
        **fields,
        log_id=team_log.pk,
        target_user_id=team_log.target_user_id,
        overridden=overridden,
    )
    return TeamChange(team=changed, log=team_log, overridden=overridden)


def rename(
    team: Team,
    name: str,
    *,
    actor: CustomUser | None,
    via: TeamLogVia,
    reason: str = "",
    acknowledged_codes: Collection[str] = (),
) -> TeamChange:
    new_name = (name or "").strip()

    def validate(locked: Team) -> list[Violation]:
        if not new_name:
            raise TeamManagementError("name_blank", "Enter a team name.")
        if len(new_name) > NAME_MAX_LENGTH:
            raise TeamManagementError(
                "name_too_long",
                f"Team names can be at most {NAME_MAX_LENGTH} characters.",
            )
        if new_name == locked.name:
            raise TeamManagementError(
                "name_unchanged", "The team already has this name."
            )
        return []

    def mutate(locked: Team) -> dict[str, Any]:
        locked.name = new_name
        locked.save(update_fields=["name"])
        return {"fields_changed": ["name"]}

    return _apply(
        team,
        TeamLogAction.RENAME,
        actor=actor,
        via=via,
        reason=reason,
        acknowledged_codes=acknowledged_codes,
        target_user=lambda locked: None,
        affected_users=lambda locked: list(locked.members.nocache().order_by("pk")),
        validate=validate,
        mutate=mutate,
        touched=(),
    )


def set_deputy(
    team: Team,
    user: CustomUser | None,
    *,
    actor: CustomUser | None,
    via: TeamLogVia,
    reason: str = "",
    acknowledged_codes: Collection[str] = (),
) -> TeamChange:
    def validate(locked: Team) -> list[Violation]:
        if user is None:
            if locked.deputy_captain_id is None:
                raise TeamManagementError(
                    "no_deputy", "The team has no deputy captain to clear."
                )
            return []
        if user.pk == locked.captain_id:
            raise TeamManagementError(
                "deputy_is_captain",
                "The captain cannot also be the deputy. Choose another member.",
            )
        if user.pk == locked.deputy_captain_id:
            raise TeamManagementError(
                "already_deputy", "This player is already the deputy captain."
            )
        if not _is_member(locked, user):
            if _is_standin(locked, user):
                raise TeamManagementError(
                    "deputy_is_standin",
                    "Stand-ins cannot be deputy: sub them in first.",
                )
            raise TeamManagementError(
                "deputy_not_member",
                "The deputy must be a member of the team. Add them first.",
            )
        return []

    def mutate(locked: Team) -> dict[str, Any]:
        locked.deputy_captain = user
        locked.save(update_fields=["deputy_captain"])
        return {}

    return _apply(
        team,
        TeamLogAction.SET_DEPUTY,
        actor=actor,
        via=via,
        reason=reason,
        acknowledged_codes=acknowledged_codes,
        target_user=lambda locked: user if user is not None else locked.deputy_captain,
        affected_users=lambda locked: [user, locked.deputy_captain],
        validate=validate,
        mutate=mutate,
        touched=("deputy_captain",),
    )


def remove_standin(
    team: Team,
    user: CustomUser,
    *,
    actor: CustomUser | None,
    via: TeamLogVia,
    reason: str = "",
    acknowledged_codes: Collection[str] = (),
) -> TeamChange:
    def validate(locked: Team) -> list[Violation]:
        if not _is_standin(locked, user):
            raise TeamManagementError(
                "not_standin", "This player is not a stand-in on this team."
            )
        return []

    def mutate(locked: Team) -> dict[str, Any]:
        locked.dropin_members.remove(user)
        return {}

    return _apply(
        team,
        TeamLogAction.REMOVE_STANDIN,
        actor=actor,
        via=via,
        reason=reason,
        acknowledged_codes=acknowledged_codes,
        target_user=lambda locked: user,
        affected_users=lambda locked: [user],
        validate=validate,
        mutate=mutate,
        touched=(),
    )


def restore_member(
    team: Team,
    user: CustomUser,
    *,
    actor: CustomUser | None,
    via: TeamLogVia,
    reason: str = "",
    acknowledged_codes: Collection[str] = (),
) -> TeamChange:
    def validate(locked: Team) -> list[Violation]:
        if not _is_dropout(locked, user):
            raise TeamManagementError(
                "not_dropout",
                "Only players who dropped out of this team can be restored.",
            )
        if user.pk in _other_team_user_ids(locked):
            raise TeamManagementError(
                "on_other_team",
                "This player is on another team in this tournament. "
                "Remove them there first.",
            )
        return []

    def mutate(locked: Team) -> dict[str, Any]:
        locked.members.add(user)
        locked.left_members.remove(user)
        return {}

    return _apply(
        team,
        TeamLogAction.RESTORE_MEMBER,
        actor=actor,
        via=via,
        reason=reason,
        acknowledged_codes=acknowledged_codes,
        target_user=lambda locked: user,
        affected_users=lambda locked: [user],
        validate=validate,
        mutate=mutate,
        touched=(),
    )
