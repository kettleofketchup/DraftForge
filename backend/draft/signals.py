from asgiref.sync import async_to_sync
from channels import layers
from django.db import transaction
from django.db.models.signals import pre_save
from django.dispatch import receiver

from app.cache_utils import invalidate_after_commit
from app.models import Game
from draft.models import DraftTeam, HeroDraft, HeroDraftRound, HeroDraftState
from telemetry.logging import get_logger

log = get_logger(__name__)


@receiver(
    pre_save,
    sender="app.Game",
    dispatch_uid="draft_reset_herodraft_on_team_change",
)
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
        # what reset_draft does in draft/views/hero.py.
        dt.is_first_pick = None
        dt.is_radiant = None
        dt.reserve_time_remaining = reserve_ms
        dt.save()
        updated_draft_teams.append(dt)

    # Wipe picks/bans — they belong to the wrong captain. `draft.herodraftround`
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

    # Model.save() → invalidate_obj fires while save_bracket's
    # @transaction.atomic is still open, so a concurrent reader could re-cache
    # the pre-update rows (old captains) before COMMIT, defeating the reset.
    # `invalidate_after_commit` invalidates again on transaction.on_commit.
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
