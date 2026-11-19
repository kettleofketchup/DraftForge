"""
Django signals for Team and Tournament member management.

Handles:
- Captain/deputy succession when members are removed
- Empty teams: kept when referenced, deleted otherwise, both audited
- Cascade removal from tournament.users to team.members
- Auto-add tournament users to organization and league
- Purge stale HeroDraft when a Game's teams change (issue #235)
- Mark a tournament past when its bracket final is decided (issue #419)
- Blank an org's Discord server nicknames when its discord_server_id changes
"""

from typing import Any

from asgiref.sync import async_to_sync
from channels import layers
from django.db import transaction
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from app.cache_utils import invalidate_after_commit
from app.models import (
    CustomUser,
    DraftTeam,
    Game,
    HeroDraft,
    HeroDraftRound,
    HeroDraftState,
    Organization,
    Team,
    TeamLogAction,
    TeamLogVia,
    Tournament,
)
from app.services.team_audit import log_snapshot_fields, roster_snapshot, write_team_log
from app.services.team_leadership import successor_after_removal
from app.services.team_management import follow_captain
from app.services.team_references import team_references
from app.services.team_signals import (
    change_from_log,
    send_roster_changed_on_commit,
    team_audit_owner,
)
from app.services.team_signals import team_roster_changed as team_roster_changed
from app.services.tournament_completion import sync_tournament_completion
from league.models import LeagueUser
from org.discord_names import reset_org_guild_nicknames
from org.models import OrgUser
from telemetry.logging import get_logger

log = get_logger(__name__)


@receiver(m2m_changed, sender="app.Team_members")
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


@receiver(m2m_changed, sender="app.Tournament_users")
def handle_tournament_user_removal(
    sender: type,
    instance: Tournament,
    action: str,
    pk_set: set[int] | None,
    **kwargs: object,
) -> None:
    """Cascade removal from tournament.users to team.members."""
    # Handle clear all users
    if action == "post_clear":
        # Clear all teams' members - this triggers team deletion via team signal
        for team in instance.teams.all():
            team.members.clear()
        return

    if action != "post_remove":
        return

    tournament = instance
    removed_pks = pk_set

    # Remove users from all teams in this tournament
    for team in tournament.teams.all():
        members_to_remove = team.members.filter(pk__in=removed_pks)
        if not members_to_remove.exists():
            continue
        # This will trigger handle_team_member_removal signal
        team.members.remove(*members_to_remove)


@receiver(m2m_changed, sender="app.Tournament_users")
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

    # Skip if tournament has no league
    if not tournament.league:
        return

    league = tournament.league
    org = league.organization

    # Skip if league has no organization
    if not org:
        return

    # Get the users that were added
    added_users = CustomUser.objects.filter(pk__in=added_pks)

    for user in added_users:
        # Step 1: Create OrgUser if it doesn't exist
        org_user, org_created = OrgUser.objects.get_or_create(
            user=user,
            organization=org,
            defaults={"mmr": 0},
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
                "mmr": org_user.mmr,
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


@receiver(pre_save, sender="app.Game")
def reset_herodraft_on_team_change(
    sender: type[Game], instance: Game, **kwargs: object
) -> None:
    """Issue #235: bracket reset leaves stale HeroDraft with old captains.

    A HeroDraft holds its captains via DraftTeam.tournament_team, captured
    at draft-creation time. When the underlying Game's radiant_team or
    dire_team is rewritten — by ``save_bracket`` (full bracket re-save) or
    ``advance_winner`` (re-advancing a different winner into a downstream
    match) — the Game's teams change but the DraftTeam rows still point at
    the *previous* teams. The draft UI then renders the wrong captains and
    no client reload recovers it.

    Catch every team-mutation path in one place: just before Game.save()
    commits, compare the new (radiant_team_id, dire_team_id) against what
    is still in the DB. If either changed and the game has a HeroDraft,
    reset the draft **in place**:

      - Repoint each DraftTeam.tournament_team at the Game's new team so
        captains resolve correctly.
      - Wipe HeroDraftRound rows (the picks/bans were made by the *wrong*
        captain — carrying them over is worse than starting fresh).
      - Reset DraftTeam state (is_ready / is_connected / reserve_time) and
        HeroDraft scheduling fields (roll_winner / paused_at / resuming_until /
        is_manual_pause) back to defaults, transition to
        WAITING_FOR_CAPTAINS.
      - Keep HeroDraftEvent rows — they're the audit trail of the wrong
        setup; clearing them would hide that it ever happened.

    The HeroDraft PK is preserved, so any external reference (the Discord-
    posted /herodraft/{pk}/ link from notify_herodraft_created, etc.)
    keeps working after the reset.

    Edge case — Game slot cleared to NULL: DraftTeam.tournament_team is
    non-nullable, so the in-place reset can't repoint to None. Fall back
    to deleting the HeroDraft. When the bracket is re-saved with real
    teams create_herodraft rebuilds; the Discord link 404s in this narrow
    window.
    """
    if not instance.pk:
        return

    try:
        prior = sender.objects.only("radiant_team_id", "dire_team_id").get(
            pk=instance.pk
        )
    except sender.DoesNotExist:
        return

    if (
        prior.radiant_team_id == instance.radiant_team_id
        and prior.dire_team_id == instance.dire_team_id
    ):
        return

    draft = HeroDraft.objects.filter(game_id=instance.pk).first()
    if not draft:
        return

    teams_cleared = instance.radiant_team_id is None or instance.dire_team_id is None

    if teams_cleared:
        log.info(
            "herodraft_deleted_on_team_cleared",
            system="app",
            subsystem="signals",
            game_id=instance.pk,
            herodraft_id=draft.pk,
            prior_radiant_team_id=prior.radiant_team_id,
            new_radiant_team_id=instance.radiant_team_id,
            prior_dire_team_id=prior.dire_team_id,
            new_dire_team_id=instance.dire_team_id,
        )
    else:
        log.info(
            "herodraft_reset_on_team_change",
            system="app",
            subsystem="signals",
            game_id=instance.pk,
            herodraft_id=draft.pk,
            prior_radiant_team_id=prior.radiant_team_id,
            new_radiant_team_id=instance.radiant_team_id,
            prior_dire_team_id=prior.dire_team_id,
            new_dire_team_id=instance.dire_team_id,
        )

    if teams_cleared:
        draft_pk = draft.pk
        draft.delete()
        transaction.on_commit(
            lambda: _broadcast_draft_event(draft_pk, "draft_invalidated", instance.pk),
            robust=True,
        )
        return

    # Repoint DraftTeams at the Game's new teams. The Game row hasn't been
    # written yet (we're in pre_save), so the new IDs live on `instance`,
    # not in the DB. Match prior assignments to new slots by the prior
    # tournament_team_id.
    reserve_ms = draft.snapshot_timer_options(instance.tournament)
    updated_draft_teams = []
    for dt in DraftTeam.objects.filter(draft=draft):
        if dt.tournament_team_id == prior.radiant_team_id:
            new_team_id = instance.radiant_team_id
        elif dt.tournament_team_id == prior.dire_team_id:
            new_team_id = instance.dire_team_id
        else:
            # Shouldn't happen — DraftTeam.tournament_team should always
            # match one of the Game's two teams. Skip rather than crash.
            continue
        dt.tournament_team_id = new_team_id
        dt.is_ready = False
        dt.is_connected = False
        # Clear roll-aftermath choices — leaving these set would make
        # do_submit_choice reject the new captains with "already chosen"
        # even though the draft is back at WAITING_FOR_CAPTAINS. Matches
        # what reset_draft does in herodraft_views.py.
        dt.is_first_pick = None
        dt.is_radiant = None
        dt.reserve_time_remaining = reserve_ms
        dt.save()
        updated_draft_teams.append(dt)

    # Wipe picks/bans — they belong to the wrong captain. `app.herodraftround`
    # is NOT in CACHEOPS so the bulk delete doesn't need cache invalidation
    # of its own; the parent HeroDraft invalidation below covers any
    # consumer that re-prefetches rounds.
    HeroDraftRound.objects.filter(draft=draft).delete()

    # Reset HeroDraft scheduling fields and state. Keep HeroDraftEvent rows
    # as the audit trail.
    draft.state = HeroDraftState.WAITING_FOR_CAPTAINS
    draft.roll_winner = None
    draft.paused_at = None
    draft.resuming_until = None
    draft.is_manual_pause = False
    draft.save()

    # Re-invalidate AFTER commit. The .save() calls above already invalidate
    # via Model.save() → invalidate_obj, but those fire immediately while
    # save_bracket's @transaction.atomic is still open — between the
    # immediate invalidate and the commit, a concurrent reader could pull
    # the pre-update rows from the DB and re-cache them with the old
    # captains, defeating the whole reset. `invalidate_after_commit` schedules
    # a second invalidation on transaction.on_commit to close that race.
    invalidate_after_commit(draft, *updated_draft_teams)

    # Defer the broadcast to commit too. If we fired now, clients would
    # receive draft_reset, immediately refetch from the API, and read the
    # pre-commit rows (or repopulate cacheops with them) — defeating the
    # whole reset for any reader that's faster than the COMMIT.
    draft_pk = draft.pk
    transaction.on_commit(
        lambda: _broadcast_draft_event(draft_pk, "draft_reset", instance.pk),
        robust=True,
    )


def _broadcast_draft_event(draft_pk: int, event_type: str, game_id: int) -> None:
    """Send a HeroDraftConsumer event to the draft's channel group.

    Best-effort: a missing channel layer (tests, fallback to in-memory)
    or send failure must NOT raise — the data-integrity guarantees are
    the row updates that already committed, not the broadcast.
    """
    try:
        channel_layer = layers.get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"herodraft_{draft_pk}",
            {
                "type": "herodraft.event",
                "event_type": event_type,
                "event_id": None,
                "draft_team": None,
                "metadata": {
                    "reason": "teams_changed",
                    "game_id": game_id,
                },
                "timestamp": None,
            },
        )
    except Exception as exc:
        log.warning(
            "herodraft_broadcast_failed",
            system="app",
            subsystem="signals",
            event_type=event_type,
            herodraft_id=draft_pk,
            error=str(exc),
        )


@receiver(pre_save, sender="app.Game", dispatch_uid="game_track_winner_change")
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


@receiver(post_save, sender="app.Game", dispatch_uid="game_sync_tournament_completion")
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


@receiver(
    pre_save, sender="app.Organization", dispatch_uid="org_track_discord_server_id"
)
def track_org_discord_server_id(
    sender: type[Organization],
    instance: Organization,
    raw: bool = False,
    **kwargs: object,
) -> None:
    update_fields = kwargs.get("update_fields")
    if (
        raw
        or not instance.pk
        or (update_fields is not None and "discord_server_id" not in update_fields)
    ):
        instance._prior_discord_server_id = instance.discord_server_id
        return
    instance._prior_discord_server_id = (
        sender.objects.nocache()
        .filter(pk=instance.pk)
        .values_list("discord_server_id", flat=True)
        .first()
    )


@receiver(
    post_save, sender="app.Organization", dispatch_uid="org_reset_guild_nicknames"
)
def reset_guild_nicknames_on_server_change(
    sender: type[Organization],
    instance: Organization,
    created: bool = False,
    raw: bool = False,
    **kwargs: object,
) -> None:
    if raw or created:
        return
    prior = getattr(instance, "_prior_discord_server_id", instance.discord_server_id)
    current = instance.discord_server_id or None
    if (prior or None) == current:
        return
    reset_org_guild_nicknames(instance, enqueue=current is not None)
