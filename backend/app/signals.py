"""
Django signals for Team and Tournament member management.

Handles:
- Captain/deputy succession when members are removed
- Team deletion when last member is removed
- Cascade removal from tournament.users to team.members
- Auto-add tournament users to organization and league
- Mark a tournament past when its bracket final is decided (issue #419)
- Blank an org's Discord server nicknames when its discord_server_id changes
"""

from django.db import transaction
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from app.models import (
    CustomUser,
    Game,
    Organization,
    Team,
    Tournament,
)
from app.services.tournament_completion import sync_tournament_completion
from league.models import LeagueUser
from org.discord_names import reset_org_guild_nicknames
from org.models import OrgUser
from telemetry.logging import get_logger

log = get_logger(__name__)


@receiver(m2m_changed, sender="app.Team_members")
def handle_team_member_removal(
    sender: type, instance: Team, action: str, pk_set: set[int] | None, **kwargs: object
) -> None:
    """Handle captain/deputy succession when members are removed."""
    team = instance

    # Handle post_clear - delete team if empty
    if action == "post_clear":
        if team.members.count() == 0:
            team.delete()
        return

    # Only handle post_remove for removal logic
    if action != "post_remove":
        return

    removed_pks = pk_set

    # Guard: Team is now empty → delete it
    if team.members.count() == 0:
        team.delete()
        return

    # Guard: Captain wasn't removed
    captain_removed = team.captain and team.captain.pk in removed_pks
    deputy_removed = team.deputy_captain and team.deputy_captain.pk in removed_pks

    if not captain_removed and not deputy_removed:
        return

    # Handle deputy removal (simple case)
    if not captain_removed and deputy_removed:
        team.deputy_captain = None
        team.save(update_fields=["deputy_captain"])
        return

    # Captain was removed - need succession
    # Try deputy first if they weren't also removed
    if (
        team.deputy_captain
        and not deputy_removed
        and team.members.filter(pk=team.deputy_captain.pk).exists()
    ):
        team.captain = team.deputy_captain
        team.deputy_captain = None
        team.save(update_fields=["captain", "deputy_captain"])
        return

    # Fallback: promote remaining member (by OrgUser MMR if available, else by pk)
    remaining = team.members.all()
    highest_mmr_member = remaining.order_by("pk").first()
    if (
        team.tournament
        and hasattr(team.tournament, "league")
        and team.tournament.league
    ):
        org = team.tournament.league.organization
        if org:
            best = (
                OrgUser.objects.filter(user__in=remaining, organization=org)
                .order_by("-mmr")
                .first()
            )
            if best:
                highest_mmr_member = best.user
    team.captain = highest_mmr_member
    team.deputy_captain = None
    team.save(update_fields=["captain", "deputy_captain"])


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
