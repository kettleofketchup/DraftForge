"""
Django signals for Team and Tournament member management.

Handles:
- Captain/deputy succession when members are removed
- Team deletion when last member is removed
- Cascade removal from tournament.users to team.members
- Auto-add tournament users to organization and league
"""

import logging

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

log = logging.getLogger(__name__)


@receiver(m2m_changed, sender="app.Team_members")
def handle_team_member_removal(sender, instance, action, pk_set, **kwargs):
    """Handle captain/deputy succession when members are removed."""
    # Only handle post_remove - skip post_clear to allow rebuild_teams() to work
    # (rebuild_teams calls clear() then add(), and we don't want deletion between)
    if action != "post_remove":
        return

    team = instance
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
    if team.deputy_captain and not deputy_removed:
        team.captain = team.deputy_captain
        team.deputy_captain = None
        team.save(update_fields=["captain", "deputy_captain"])
        return

    # Fallback: promote highest MMR member
    highest_mmr_member = team.members.order_by("-mmr").first()
    team.captain = highest_mmr_member
    team.deputy_captain = None
    team.save(update_fields=["captain", "deputy_captain"])


@receiver(m2m_changed, sender="app.Tournament_users")
def handle_tournament_user_removal(sender, instance, action, pk_set, **kwargs):
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
def handle_tournament_user_addition(sender, instance, action, pk_set, **kwargs):
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

    # Import models here to avoid circular imports
    from league.models import LeagueUser
    from org.models import OrgUser

    from .models import CustomUser

    # Get the users that were added
    added_users = CustomUser.objects.filter(pk__in=added_pks)

    for user in added_users:
        # Step 1: Create OrgUser if it doesn't exist
        org_user, org_created = OrgUser.objects.get_or_create(
            user=user,
            organization=org,
            defaults={"mmr": user.mmr or 0},
        )
        if org_created:
            log.info(
                f"Created OrgUser for {user.username} in org {org.name} "
                f"(via tournament {tournament.name})"
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
                f"Created LeagueUser for {user.username} in league {league.name} "
                f"(via tournament {tournament.name})"
            )
