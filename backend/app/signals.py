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

from django.db import transaction
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
def reset_herodraft_on_team_change(sender, instance, **kwargs):
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

    from app.models import DraftTeam, HeroDraft, HeroDraftRound, HeroDraftState

    draft = HeroDraft.objects.filter(game_id=instance.pk).first()
    if not draft:
        return

    teams_cleared = (
        instance.radiant_team_id is None or instance.dire_team_id is None
    )

    log.info(
        "herodraft_deleted_on_team_cleared"
        if teams_cleared
        else "herodraft_reset_on_team_change",
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

    if teams_cleared:
        draft_pk = draft.pk
        draft.delete()
        transaction.on_commit(
            lambda: _broadcast_draft_event(draft_pk, "draft_invalidated", instance.pk)
        )
        return

    # Repoint DraftTeams at the Game's new teams. The Game row hasn't been
    # written yet (we're in pre_save), so the new IDs live on `instance`,
    # not in the DB. Match prior assignments to new slots by the prior
    # tournament_team_id.
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
        dt.reserve_time_remaining = 90000
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
    from app.cache_utils import invalidate_after_commit

    invalidate_after_commit(draft, *updated_draft_teams)

    # Defer the broadcast to commit too. If we fired now, clients would
    # receive draft_reset, immediately refetch from the API, and read the
    # pre-commit rows (or repopulate cacheops with them) — defeating the
    # whole reset for any reader that's faster than the COMMIT.
    draft_pk = draft.pk
    transaction.on_commit(
        lambda: _broadcast_draft_event(draft_pk, "draft_reset", instance.pk)
    )


def _broadcast_draft_event(draft_pk, event_type, game_id):
    """Send a HeroDraftConsumer event to the draft's channel group.

    Best-effort: a missing channel layer (tests, fallback to in-memory)
    or send failure must NOT raise — the data-integrity guarantees are
    the row updates that already committed, not the broadcast.
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
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
            f"Failed to broadcast {event_type} for HeroDraft {draft_pk}: {exc}"
        )
