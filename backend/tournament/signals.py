"""
Django signals for Team and Tournament member management.

Handles:
- Captain/deputy succession when members are removed
- Empty teams: kept when referenced, deleted otherwise, both audited
- Cascade removal from tournament.users to the members of teams still playing
- Auto-add tournament users to organization and league
- Mark a tournament past when its bracket final is decided (issue #419)
"""

from typing import Any

from django.db import transaction
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from league.models import LeagueUser
from org.mmr import LEAGUE_GAME, org_mmr_map
from org.models import OrgUser
from telemetry.logging import get_logger
from tournament.broadcast import send_tournament_update
from tournament.models import Game, Team, Tournament
from tournament.models.team_log import TeamLogAction, TeamLogVia
from tournament.services.team_audit import (
    log_snapshot_fields,
    roster_snapshot,
    write_team_log,
)
from tournament.services.team_leadership import successor_after_removal
from tournament.services.team_management import follow_captain
from tournament.services.team_references import team_references
from tournament.services.team_signals import (
    TeamRosterChange,
    change_from_log,
    send_roster_changed_on_commit,
    team_audit_owner,
    team_roster_changed,
)
from tournament.services.tournament_completion import sync_tournament_completion

log = get_logger(__name__)


@receiver(team_roster_changed, dispatch_uid="tournament_broadcast_roster_change")
def broadcast_roster_change(
    sender: type, change: TeamRosterChange, **kwargs: object
) -> None:
    send_tournament_update(change.tournament_id, "team", team_id=change.team_id)


@receiver(m2m_changed, sender="tournament.Team_members")
def handle_team_member_removal(
    sender: type,
    instance: Team | CustomUser,
    action: str,
    pk_set: set[int] | None,
    reverse: bool = False,
    **kwargs: object,
) -> None:
    """Captain/deputy succession and empty-team handling when members leave."""
    if reverse:
        _handle_reverse_member_change(instance, action, pk_set)
        return

    team = instance
    if action == "pre_clear":
        team._members_before_clear = set(  # type: ignore[union-attr]
            team.members.nocache().values_list("pk", flat=True)
        )
        return
    if action == "post_clear":
        removed = getattr(team, "_members_before_clear", set())
        team._members_before_clear = set()  # type: ignore[union-attr]
        _after_members_removed(team, removed)
        return
    if action == "post_remove":
        _after_members_removed(team, set(pk_set or ()))


def _handle_reverse_member_change(
    user: CustomUser, action: str, pk_set: set[int] | None
) -> None:
    if action == "pre_clear":
        user._teams_before_clear = set(  # type: ignore[attr-defined]
            Team.members.through.objects.filter(customuser=user).values_list(
                "team_id", flat=True
            )
        )
        return
    if action == "post_clear":
        team_pks = getattr(user, "_teams_before_clear", set())
        user._teams_before_clear = set()  # type: ignore[attr-defined]
    elif action == "post_remove":
        team_pks = set(pk_set or ())
    else:
        return
    for team in Team.objects.nocache().filter(pk__in=team_pks).order_by("pk"):
        _after_members_removed(team, {user.pk})


def _write_system_log(team: Team, **kwargs: Any) -> None:
    """Write a via=system row, then invalidate and notify like the service does."""
    row = write_team_log(
        team, snapshot=log_snapshot_fields(team), via=TeamLogVia.SYSTEM, **kwargs
    )
    details = row.details or {}
    user_ids = {
        pk
        for snap in (details.get("before") or {}, details.get("after") or {})
        for pk in (snap.get("captain_id"), snap.get("deputy_captain_id"))
        if pk is not None
    }
    to_invalidate: list[Any] = list(
        CustomUser.objects.nocache().filter(pk__in=user_ids)
    )
    if team.pk is not None:
        to_invalidate.append(team)
    if team.tournament_id is not None:
        to_invalidate.append(team.tournament)
    invalidate_after_commit(*to_invalidate)
    send_roster_changed_on_commit(change_from_log(row))


def _before_removal(team: Team, removed_pks: set[int]) -> dict[str, Any]:
    before = roster_snapshot(team)
    before["member_ids"] = sorted(set(before["member_ids"]) | removed_pks)
    return before


def _after_members_removed(team: Team, removed_pks: set[int]) -> None:
    if not team.members.nocache().exists():
        _handle_empty_team(team, removed_pks)
        return

    captain, deputy, how = successor_after_removal(team, removed_pks)
    if how == "unchanged":
        return

    owned = team_audit_owner.get()
    before = None if owned else _before_removal(team, removed_pks)
    old_captain = team.captain
    team.captain = captain
    team.deputy_captain = deputy
    team.save(update_fields=["captain", "deputy_captain"])
    log.info(
        "team_succession_applied",
        system="tournament",
        subsystem="teams",
        team_id=team.pk,
        succession=how,
        owned=owned,
    )
    if before is None:
        return
    follow_up: dict[str, Any] = {}
    if captain is not None and captain.pk != getattr(old_captain, "pk", None):
        follow_up = follow_captain(team, old_captain, captain, actor=None)
    _write_system_log(
        team,
        action=TeamLogAction.SYSTEM_SUCCESSION,
        target_user=captain,
        details={
            "before": before,
            "after": roster_snapshot(team),
            "succession": how,
            **follow_up,
        },
    )


def _handle_empty_team(team: Team, removed_pks: set[int]) -> None:
    """Keep an emptied team that other rows still point at; delete it otherwise."""
    owned = team_audit_owner.get()
    references = team_references([team])
    if references:
        log.warning(
            "empty_team_kept",
            system="tournament",
            subsystem="teams",
            team_id=team.pk,
            tournament_id=team.tournament_id,
            references=references,
        )
        if not owned:
            _write_system_log(
                team,
                action=TeamLogAction.EMPTY_TEAM_KEPT,
                details={
                    "before": _before_removal(team, removed_pks),
                    "after": roster_snapshot(team),
                    "references": references,
                },
            )
        return

    if not owned:
        _write_system_log(
            team,
            action=TeamLogAction.TEAM_DELETED,
            details={"before": _before_removal(team, removed_pks)},
        )
    log.info(
        "empty_team_deleted",
        system="tournament",
        subsystem="teams",
        team_id=team.pk,
        tournament_id=team.tournament_id,
        owned=owned,
    )
    team.delete()


@receiver(m2m_changed, sender="tournament.Tournament_users")
def handle_tournament_user_removal(
    sender: type,
    instance: Tournament,
    action: str,
    pk_set: set[int] | None,
    **kwargs: object,
) -> None:
    """Cascade removal from tournament.users into the rosters of teams still playing."""
    if action not in ("post_clear", "post_remove"):
        return

    live_teams = instance.teams.nocache().filter(placement__isnull=True).order_by("pk")
    if action == "post_clear":
        for team in live_teams:
            team.members.clear()
        return

    for team in live_teams:
        members_to_remove = team.members.filter(pk__in=pk_set or ())
        if not members_to_remove.exists():
            continue
        team.members.remove(*members_to_remove)


@receiver(m2m_changed, sender="tournament.Tournament_users")
def handle_tournament_user_addition(
    sender: type,
    instance: Tournament,
    action: str,
    pk_set: set[int] | None,
    **kwargs: object,
) -> None:
    """
    Auto-add users to organization and league when added to a tournament.

    When users are added to a tournament:
    1. Create OrgUser for the league's organization (if not exists)
    2. Create LeagueUser for the league (if not exists)
    """
    if action != "post_add":
        return

    tournament = instance
    added_pks = pk_set

    if not tournament.league:
        return

    league = tournament.league
    org = league.organization

    if not org:
        return

    added_users = CustomUser.objects.filter(pk__in=added_pks)
    seeded = set(
        LeagueUser.objects.filter(league=league, user_id__in=added_pks).values_list(
            "user_id", flat=True
        )
    )
    league_mmrs = org_mmr_map(org.pk, set(added_pks or ()) - seeded, LEAGUE_GAME)

    for user in added_users:
        # Step 1: Create OrgUser if it doesn't exist
        org_user, org_created = OrgUser.objects.get_or_create(
            user=user,
            organization=org,
        )
        if org_created:
            log.info(
                "org_user_created",
                system="app",
                subsystem="signals",
                username=user.username,
                user_id=user.pk,
                tournament_id=tournament.pk,
            )

        # Step 2: Create LeagueUser if it doesn't exist
        league_user, league_created = LeagueUser.objects.get_or_create(
            user=user,
            league=league,
            defaults={
                "org_user": org_user,
                "mmr": league_mmrs.get(user.pk, 0),
            },
        )
        if league_created:
            log.info(
                "league_user_created",
                system="app",
                subsystem="signals",
                username=user.username,
                user_id=user.pk,
                tournament_id=tournament.pk,
            )


@receiver(pre_save, sender="tournament.Game", dispatch_uid="game_track_winner_change")
def track_game_winner_change(
    sender: type[Game], instance: Game, raw: bool = False, **kwargs: object
) -> None:
    update_fields = kwargs.get("update_fields")
    if raw or (update_fields is not None and "winning_team" not in update_fields):
        instance._prior_winning_team_id = instance.winning_team_id
        return
    prior = (
        sender.objects.nocache()
        .filter(pk=instance.pk)
        .values_list("winning_team_id", flat=True)
        .first()
        if instance.pk
        else None
    )
    instance._prior_winning_team_id = prior


@receiver(
    post_save, sender="tournament.Game", dispatch_uid="game_sync_tournament_completion"
)
def sync_tournament_on_game_result(
    sender: type[Game], instance: Game, raw: bool = False, **kwargs: object
) -> None:
    """Issue #419: re-check the tournament state when a game's winner changes."""
    if raw or not instance.tournament_id:
        return
    prior = getattr(instance, "_prior_winning_team_id", instance.winning_team_id)
    if prior == instance.winning_team_id:
        return
    tournament_id = instance.tournament_id
    cleared_game_id = instance.pk if instance.winning_team_id is None else None
    transaction.on_commit(
        lambda: sync_tournament_completion(
            tournament_id, cleared_game_id=cleared_game_id
        ),
        robust=True,
    )
