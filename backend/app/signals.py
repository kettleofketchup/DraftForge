"""
Django signals for Team and Tournament member management.

Handles:
- Captain/deputy succession when members are removed
- Team deletion when last member is removed
- Cascade removal from tournament.users to team.members
- Auto-add tournament users to organization and league
- Purge stale HeroDraft when a Game's teams change (issue #235)
"""

import logging

from django.db.models.signals import m2m_changed, pre_save
from django.dispatch import receiver

log = logging.getLogger(__name__)


@receiver(m2m_changed, sender="app.Team_members")
def handle_team_member_removal(sender, instance, action, pk_set, **kwargs):
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
    if team.deputy_captain and not deputy_removed:
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
            from org.models import OrgUser

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
            defaults={"mmr": 0},
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


@receiver(pre_save, sender="app.Game")
def purge_stale_herodraft_on_team_change(sender, instance, **kwargs):
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
    is still in the DB. If either changed, delete the dependent HeroDraft
    (and its DraftTeam / HeroDraftRound / HeroDraftEvent rows via FK
    cascade). The next request to start a draft on that Game rebuilds a
    clean one from the current teams.

    Why this can't be preserved across the team change: any picks/bans
    made before the change were made by the *wrong* captain, so carrying
    them over is worse than starting fresh.
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

    from app.models import HeroDraft

    draft = HeroDraft.objects.filter(game_id=instance.pk).first()
    if not draft:
        return

    log.info(
        "herodraft_purged_on_team_change",
        extra={
            "system": "bracket",
            "subsystem": "herodraft",
            "game_id": instance.pk,
            "herodraft_id": draft.pk,
            "prior_radiant_team_id": prior.radiant_team_id,
            "new_radiant_team_id": instance.radiant_team_id,
            "prior_dire_team_id": prior.dire_team_id,
            "new_dire_team_id": instance.dire_team_id,
        },
    )
    draft.delete()
