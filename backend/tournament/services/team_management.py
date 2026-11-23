"""Staff roster service: every team change runs through one audited pipeline."""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal

from django.db import transaction
from django.db.models import Q

from app.cache_utils import invalidate_after_commit, invalidate_obj
from app.models import CustomUser
from draft.models import (
    Draft,
    DraftRound,
    DraftTeam,
    HeroDraft,
    HeroDraftState,
    TeamDraftState,
)
from draft.services.hero_broadcast import broadcast_herodraft_state
from draft.services.hero_chat import apply_captain_tenure
from draft.services.team import emit_event
from events.eligibility import unmet_codes, unmet_labels
from events.overrides import (
    REASON_MAX_LENGTH,
    OverrideReasonRequired,
    OverrideRequired,
    Violation,
    check_overrides,
)
from league.models import LeagueUser
from org.models import OrgSettings, OrgUser
from org.settings_service import get_org_settings
from telemetry.logging import get_logger
from tournament.models import Team, TeamLog
from tournament.models.team_log import TeamLogAction, TeamLogVia
from tournament.services.team_audit import (
    log_snapshot_fields,
    roster_snapshot,
    source_event,
    write_team_log,
)
from tournament.services.team_leadership import successor_after_removal
from tournament.services.team_signals import (
    change_from_log,
    owning_team_audit,
    send_roster_changed_on_commit,
)

log = get_logger(__name__)

DEFAULT_MAX_STANDINS: int = 2
NAME_MAX_LENGTH: int = 255

PRESENCE_FIELDS: tuple[str, ...] = (
    "draft_is_ready",
    "draft_is_connected",
    "draft_has_connected",
)
_DONE_HERODRAFT_STATES: tuple[str, ...] = (
    HeroDraftState.COMPLETED,
    HeroDraftState.ABANDONED,
)

LeadershipKey = Literal["captain", "deputy_captain"]
Validate = Callable[[Team], Iterable[Violation]]
Mutate = Callable[[Team], dict[str, Any] | None]
UsersOf = Callable[[Team], Iterable[CustomUser | None]]
UserOf = Callable[[Team], CustomUser | None]
TouchedOf = Callable[[Team], Collection[LeadershipKey]]


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


def other_team_user_ids(team: Team) -> set[int]:
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


def _refresh_herodrafts(
    team: Team, drafts: Sequence[HeroDraft], draft_teams: Sequence[DraftTeam]
) -> None:
    for obj in (team, *drafts, *draft_teams):
        invalidate_obj(obj)
    for draft in drafts:
        broadcast_herodraft_state(draft, "team_changed")


def follow_captain(
    team: Team,
    old: CustomUser | None,
    new: CustomUser,
    *,
    actor: CustomUser | None,
) -> dict[str, Any]:
    """Move the team's rounds to the new captain, reset presence, refresh live drafts.

    Picked rounds move too: rounds resolve their team by captain, and the
    player_picked DraftEvent keeps who actually picked.
    """
    extras: dict[str, Any] = {}
    if old is None:
        extras["draft_rounds_updated"] = 0
        extras["draft_rounds_skipped_reason"] = "no_previous_captain"
    elif (
        Team.objects.nocache()
        .filter(tournament_id=team.tournament_id, captain_id__in=[old.pk, new.pk])
        .exclude(pk=team.pk)
        .exists()
    ):
        # Rounds have no team FK: with a shared captain they can't be told apart.
        extras["draft_rounds_updated"] = 0
        extras["draft_rounds_skipped_reason"] = "old_captain_leads_other_team"
        log.warning(
            "team_rounds_not_followed",
            system="tournament",
            subsystem="teams",
            team_id=team.pk,
            old_captain_id=old.pk,
            new_captain_id=new.pk,
        )
    else:
        rounds = DraftRound.objects.nocache().filter(
            draft__tournament_id=team.tournament_id, captain=old
        )
        updated = 0
        picked = 0
        for draft_round in rounds.order_by("pk"):
            draft_round.captain = new
            draft_round.save(update_fields=["captain"])
            updated += 1
            picked += draft_round.choice_id is not None
        extras["draft_rounds_updated"] = updated
        extras["draft_picked_rounds_updated"] = picked

    for field in PRESENCE_FIELDS:
        setattr(team, field, False)
    team.save(update_fields=list(PRESENCE_FIELDS))
    extras["presence_reset"] = True

    draft = (
        Draft.objects.nocache()
        .filter(tournament_id=team.tournament_id)
        .exclude(state=TeamDraftState.COMPLETED)
        .first()
        if team.tournament_id is not None
        else None
    )
    if draft is not None:
        emit_event(
            draft,
            "team_changed",
            {"team_id": team.pk, "team_name": team.name, "pick_number": None},
            actor,
        )

    herodrafts = list(
        HeroDraft.objects.nocache()
        .filter(draft_teams__tournament_team=team)
        .exclude(state__in=_DONE_HERODRAFT_STATES)
        .distinct()
        .order_by("pk")
    )
    if herodrafts:
        # Only the ready gate is reset; mid-draft, a stale is_connected makes
        # the heartbeat check pause until the new captain connects.
        waiting = DraftTeam.objects.nocache().filter(
            tournament_team=team,
            draft__in=herodrafts,
            draft__state=HeroDraftState.WAITING_FOR_CAPTAINS,
        )
        reset_ids: list[int] = []
        for draft_team in waiting.order_by("pk"):
            draft_team.is_ready = False
            draft_team.is_connected = False
            draft_team.save(update_fields=["is_ready", "is_connected"])
            reset_ids.append(draft_team.pk)
        extras["herodraft_teams_reset"] = reset_ids
        draft_teams = list(DraftTeam.objects.nocache().filter(draft__in=herodrafts))
        transaction.on_commit(
            partial(_refresh_herodrafts, team, herodrafts, draft_teams)
        )
        transaction.on_commit(
            partial(
                apply_captain_tenure,
                team.pk,
                [d.pk for d in herodrafts],
                old.pk if old is not None else None,
                new.pk,
            ),
            robust=True,
        )

    log.info(
        "team_captain_followed",
        system="tournament",
        subsystem="teams",
        team_id=team.pk,
        old_captain_id=old.pk if old is not None else None,
        new_captain_id=new.pk,
        draft_rounds_updated=extras["draft_rounds_updated"],
        herodraft_ids=[d.pk for d in herodrafts],
    )
    return extras


def _ensure_tournament_user(team: Team, user: CustomUser) -> dict[str, Any]:
    tournament = team.tournament
    if tournament is None or tournament.users.filter(pk=user.pk).exists():
        return {}
    league = tournament.league
    org_id = league.organization_id if league is not None else None
    had_org_user = (
        org_id is not None
        and OrgUser.objects.filter(user=user, organization_id=org_id).exists()
    )
    had_league_user = (
        league is not None
        and LeagueUser.objects.filter(user=user, league=league).exists()
    )
    tournament.users.add(user)
    return {
        "added_to_tournament": True,
        "org_user_created": (
            org_id is not None
            and not had_org_user
            and OrgUser.objects.filter(user=user, organization_id=org_id).exists()
        ),
        "league_user_created": (
            league is not None
            and not had_league_user
            and LeagueUser.objects.filter(user=user, league=league).exists()
        ),
    }


def _change_captain(
    team: Team, new: CustomUser, *, actor: CustomUser | None
) -> dict[str, Any]:
    old = team.captain
    extras = _ensure_tournament_user(team, new)
    team.captain = new
    team.save(update_fields=["captain"])
    extras.update(follow_captain(team, old, new, actor=actor))
    return extras


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
    touched: Collection[LeadershipKey] | TouchedOf,
) -> TeamChange:
    reason = (reason or "").strip()
    if len(reason) > REASON_MAX_LENGTH:
        raise TeamManagementError(
            "reason_too_long",
            f"Reasons can be at most {REASON_MAX_LENGTH} characters.",
        )
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
            touched_keys = set(touched(locked) if callable(touched) else touched)
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
            dirty = sorted(key for key, _ in pairs_after if key in touched_keys)
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
            user_ids = {
                pk
                for snap in (before, after)
                for key in ("member_ids", "dropin_ids", "left_ids")
                for pk in snap[key]
            } | {
                pk
                for snap in (before, after)
                for pk in (snap["captain_id"], snap["deputy_captain_id"])
                if pk is not None
            }
            to_invalidate: list[Any] = [
                changed,
                *affected,
                *CustomUser.objects.nocache().filter(pk__in=user_ids),
            ]
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
        affected_users=lambda locked: [],
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


def _standin_violations(team: Team, user: CustomUser) -> list[Violation]:
    violations: list[Violation] = []
    cap = standin_cap(team)
    count = team.dropin_members.nocache().count()
    if count + 1 > cap:
        violations.append(
            Violation(
                code="team_standin_cap",
                rule="override-warning",
                message=f"The team already has {count} stand-ins (limit {cap}).",
                category="team",
            )
        )
    event = source_event(team.tournament)
    if event is not None:
        codes = unmet_codes(event, user)
        violations.extend(
            Violation(
                code=code, rule="staff-override", message=label, category="eligibility"
            )
            for code, label in zip(codes, unmet_labels(codes), strict=True)
        )
    return violations


def add_standin(
    team: Team,
    user: CustomUser,
    *,
    actor: CustomUser | None,
    via: TeamLogVia,
    reason: str = "",
    acknowledged_codes: Collection[str] = (),
) -> TeamChange:
    def validate(locked: Team) -> list[Violation]:
        if (
            _is_member(locked, user)
            or _is_standin(locked, user)
            or _is_dropout(locked, user)
        ):
            raise TeamManagementError(
                "already_on_team",
                "This player is already on this team as a member, stand-in or dropout.",
            )
        if user.pk in other_team_user_ids(locked):
            raise TeamManagementError(
                "on_other_team",
                "This player is on another team in this tournament. "
                "Remove them there first.",
            )
        return _standin_violations(locked, user)

    def mutate(locked: Team) -> dict[str, Any]:
        locked.dropin_members.add(user)
        return {}

    return _apply(
        team,
        TeamLogAction.ADD_STANDIN,
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
        if user.pk in other_team_user_ids(locked):
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


def set_captain(
    team: Team,
    user: CustomUser,
    *,
    actor: CustomUser | None,
    via: TeamLogVia,
    reason: str = "",
    acknowledged_codes: Collection[str] = (),
) -> TeamChange:
    def is_reseat(locked: Team) -> bool:
        return user.pk == locked.captain_id and not _is_member(locked, user)

    def validate(locked: Team) -> list[Violation]:
        if is_reseat(locked):
            if user.pk in other_team_user_ids(locked):
                raise TeamManagementError(
                    "on_other_team",
                    "This player is on another team in this tournament. "
                    "Remove them there first.",
                )
            return []
        if user.pk == locked.captain_id:
            raise TeamManagementError(
                "already_captain", "This player is already the captain."
            )
        if not (_is_member(locked, user) or _is_standin(locked, user)):
            raise TeamManagementError(
                "captain_not_member",
                "The captain must be a member or stand-in of the team. Add them first.",
            )
        return []

    def mutate(locked: Team) -> dict[str, Any]:
        reseat = is_reseat(locked)
        if not _is_member(locked, user):
            locked.members.add(user)
            locked.dropin_members.remove(user)
            locked.left_members.remove(user)
        if locked.deputy_captain_id == user.pk:
            locked.deputy_captain = None
            locked.save(update_fields=["deputy_captain"])
        if reseat:
            return {}
        return _change_captain(locked, user, actor=actor)

    return _apply(
        team,
        TeamLogAction.SET_CAPTAIN,
        actor=actor,
        via=via,
        reason=reason,
        acknowledged_codes=acknowledged_codes,
        target_user=lambda locked: user,
        affected_users=lambda locked: [user, locked.captain],
        validate=validate,
        mutate=mutate,
        touched=("captain",),
    )


def _dropout_mutation(
    team: Team, user: CustomUser, *, actor: CustomUser | None
) -> dict[str, Any]:
    """Leadership first, then add to left_members before removing from members."""
    captain, deputy, how = successor_after_removal(team, {user.pk})
    extras: dict[str, Any] = {"succession": how}
    if team.deputy_captain_id != getattr(deputy, "pk", None):
        team.deputy_captain = deputy
        team.save(update_fields=["deputy_captain"])
    if captain is not None and captain.pk != team.captain_id:
        extras.update(_change_captain(team, captain, actor=actor))
    team.left_members.add(user)
    team.members.remove(user)
    return extras


def _leadership_touched_by(user: CustomUser | None) -> TouchedOf:
    def touched(locked: Team) -> tuple[LeadershipKey, ...]:
        if user is not None and user.pk == locked.captain_id:
            return ("captain", "deputy_captain")
        return ()

    return touched


def mark_dropout(
    team: Team,
    user: CustomUser,
    *,
    actor: CustomUser | None,
    via: TeamLogVia,
    reason: str = "",
    acknowledged_codes: Collection[str] = (),
) -> TeamChange:
    def validate(locked: Team) -> list[Violation]:
        if not _is_member(locked, user):
            raise TeamManagementError(
                "not_member", "Only members of this team can be marked as dropouts."
            )
        if not locked.members.nocache().exclude(pk=user.pk).exists():
            raise TeamManagementError(
                "last_member",
                "This is the team's last member. Sub in a stand-in to replace them.",
            )
        return []

    return _apply(
        team,
        TeamLogAction.MARK_DROPOUT,
        actor=actor,
        via=via,
        reason=reason,
        acknowledged_codes=acknowledged_codes,
        target_user=lambda locked: user,
        affected_users=lambda locked: [user],
        validate=validate,
        mutate=lambda locked: _dropout_mutation(locked, user, actor=actor),
        touched=_leadership_touched_by(user),
    )


def sub_in(
    team: Team,
    standin: CustomUser,
    replacing: CustomUser | None = None,
    *,
    actor: CustomUser | None,
    via: TeamLogVia,
    reason: str = "",
    acknowledged_codes: Collection[str] = (),
) -> TeamChange:
    def validate(locked: Team) -> list[Violation]:
        if not _is_standin(locked, standin):
            raise TeamManagementError(
                "not_standin",
                "Only stand-ins can be subbed in: add them as a stand-in first.",
            )
        if replacing is not None and not _is_member(locked, replacing):
            raise TeamManagementError(
                "replacing_not_member",
                "The player being replaced must be a member of this team.",
            )
        return []

    def mutate(locked: Team) -> dict[str, Any]:
        extras: dict[str, Any] = {
            "replacing_user_id": replacing.pk if replacing is not None else None,
            **_ensure_tournament_user(locked, standin),
        }
        locked.members.add(standin)
        locked.dropin_members.remove(standin)
        if replacing is not None:
            extras.update(_dropout_mutation(locked, replacing, actor=actor))
        return extras

    return _apply(
        team,
        TeamLogAction.SUB_IN,
        actor=actor,
        via=via,
        reason=reason,
        acknowledged_codes=acknowledged_codes,
        target_user=lambda locked: standin,
        affected_users=lambda locked: [standin, replacing],
        validate=validate,
        mutate=mutate,
        touched=_leadership_touched_by(replacing),
    )
