"""Functions for Captain's Mode hero draft."""

import logging
import random

from django.db import transaction
from django.utils import timezone

from app.models import (
    DraftTeam,
    HeroDraft,
    HeroDraftEvent,
    HeroDraftRound,
    HeroDraftState,
)

log = logging.getLogger(__name__)


# Updated Captain's Mode sequence (2024 patch)
# F = First pick team, S = Second pick team
# Format: (team_is_first, action_type)
CAPTAINS_MODE_SEQUENCE = [
    # Ban Phase 1: F-F-S-S-F-S-S
    (True, "ban"),  # 1
    (True, "ban"),  # 2
    (False, "ban"),  # 3
    (False, "ban"),  # 4
    (True, "ban"),  # 5
    (False, "ban"),  # 6
    (False, "ban"),  # 7
    # Pick Phase 1: F-S
    (True, "pick"),  # 8
    (False, "pick"),  # 9
    # Ban Phase 2: S-F-S
    (False, "ban"),  # 10
    (True, "ban"),  # 11
    (False, "ban"),  # 12
    # Pick Phase 2: F-S-F-S-F-S
    (True, "pick"),  # 13
    (False, "pick"),  # 14
    (True, "pick"),  # 15
    (False, "pick"),  # 16
    (True, "pick"),  # 17
    (False, "pick"),  # 18
    # Ban Phase 3: F-S-F-S
    (True, "ban"),  # 19
    (False, "ban"),  # 20
    (True, "ban"),  # 21
    (False, "ban"),  # 22
    # Pick Phase 3: F-S
    (True, "pick"),  # 23
    (False, "pick"),  # 24
]


def build_draft_rounds(draft: HeroDraft, first_team: DraftTeam, second_team: DraftTeam):
    """
    Create all 24 HeroDraftRound objects for the draft.

    Args:
        draft: The HeroDraft instance
        first_team: DraftTeam with is_first_pick=True
        second_team: DraftTeam with is_first_pick=False
    """
    rounds_to_create = []

    for i, (is_first, action_type) in enumerate(CAPTAINS_MODE_SEQUENCE):
        team = first_team if is_first else second_team
        rounds_to_create.append(
            HeroDraftRound(
                draft=draft,
                draft_team=team,
                round_number=i + 1,
                action_type=action_type,
                state="planned",
            )
        )

    HeroDraftRound.objects.bulk_create(rounds_to_create)


def trigger_roll(draft: HeroDraft, actor_team: DraftTeam) -> DraftTeam:
    """
    Perform the coin flip to determine who chooses first.

    Returns the winning DraftTeam.
    """
    with transaction.atomic():
        draft = HeroDraft.objects.select_for_update().get(id=draft.id)
        teams = list(draft.draft_teams.all())
        winner = random.choice(teams)

        draft.roll_winner = winner
        draft.state = HeroDraftState.CHOOSING
        draft.save()

        HeroDraftEvent.objects.create(
            draft=draft,
            event_type="roll_result",
            draft_team=winner,
            metadata={
                "triggered_by": actor_team.id,
                "winner_id": winner.id,
                "winner_captain": winner.captain.username if winner.captain else None,
            },
        )

        return winner


def submit_choice(draft: HeroDraft, team: DraftTeam, choice_type: str, value: str):
    """
    Submit a choice for pick order or side.

    Args:
        choice_type: "pick_order" or "side"
        value: "first"/"second" for pick_order, "radiant"/"dire" for side
    """
    with transaction.atomic():
        draft = HeroDraft.objects.select_for_update().get(id=draft.id)
        team = DraftTeam.objects.select_for_update().get(id=team.id)
        other_team = draft.draft_teams.exclude(id=team.id).select_for_update().first()

        if choice_type == "pick_order":
            team.is_first_pick = value == "first"
            other_team.is_first_pick = value != "first"
        elif choice_type == "side":
            team.is_radiant = value == "radiant"
            other_team.is_radiant = value != "radiant"

        team.save()
        other_team.save()

        HeroDraftEvent.objects.create(
            draft=draft,
            event_type="choice_made",
            draft_team=team,
            metadata={
                "choice_type": choice_type,
                "value": value,
            },
        )

        # Check if both choices have been made
        teams = list(draft.draft_teams.all())
        all_choices_made = all(
            t.is_first_pick is not None and t.is_radiant is not None for t in teams
        )

        if all_choices_made:
            # Build the draft rounds now that we know who picks first
            first_team = next(t for t in teams if t.is_first_pick)
            second_team = next(t for t in teams if not t.is_first_pick)
            build_draft_rounds(draft, first_team, second_team)

            draft.state = HeroDraftState.DRAFTING
            draft.save()

            # Activate first round
            first_round = draft.rounds.first()
            first_round.state = "active"
            first_round.started_at = timezone.now()
            first_round.save()


def submit_pick(draft: HeroDraft, team: DraftTeam, hero_id: int) -> HeroDraftRound:
    """
    Submit a hero pick or ban for the current round.

    Returns the completed round.
    """
    with transaction.atomic():
        draft = HeroDraft.objects.select_for_update().get(id=draft.id)
        team = DraftTeam.objects.select_for_update().get(id=team.id)
        current_round = draft.rounds.select_for_update().filter(state="active").first()

        if not current_round:
            raise ValueError("No active round")

        if current_round.draft_team_id != team.id:
            raise ValueError("Not your turn")

        # Check hero not already picked/banned
        used_heroes = draft.rounds.exclude(hero_id=None).values_list(
            "hero_id", flat=True
        )
        if hero_id in used_heroes:
            raise ValueError("Hero already picked or banned")

        # Calculate time spent and update reserve time
        now = timezone.now()
        elapsed_ms = int((now - current_round.started_at).total_seconds() * 1000)
        grace_used = min(elapsed_ms, current_round.grace_time_ms)
        reserve_used = max(0, elapsed_ms - current_round.grace_time_ms)

        team.reserve_time_remaining = max(0, team.reserve_time_remaining - reserve_used)
        team.save()

        # Complete the round
        current_round.hero_id = hero_id
        current_round.state = "completed"
        current_round.completed_at = now
        current_round.save()

        HeroDraftEvent.objects.create(
            draft=draft,
            event_type="hero_selected",
            draft_team=team,
            metadata={
                "round_number": current_round.round_number,
                "hero_id": hero_id,
                "action_type": current_round.action_type,
                "time_elapsed_ms": elapsed_ms,
                "reserve_used_ms": reserve_used,
            },
        )

        # Activate next round or complete draft
        next_round = draft.rounds.filter(state="planned").first()
        if next_round:
            next_round.state = "active"
            next_round.started_at = timezone.now()
            next_round.save()

            HeroDraftEvent.objects.create(
                draft=draft,
                event_type="round_started",
                draft_team=next_round.draft_team,
                metadata={
                    "round_number": next_round.round_number,
                    "action_type": next_round.action_type,
                },
            )
        else:
            draft.state = HeroDraftState.COMPLETED
            draft.save()

            HeroDraftEvent.objects.create(
                draft=draft, event_type="draft_completed", metadata={}
            )

        return current_round


def get_available_heroes(draft: HeroDraft) -> list[int]:
    """Return list of hero IDs not yet picked or banned."""
    # All Dota 2 hero IDs (1-138 with some gaps)
    # This should be synced with dotaconstants on frontend
    ALL_HERO_IDS = list(range(1, 139))  # Simplified; actual list from dotaconstants

    used_heroes = set(
        draft.rounds.exclude(hero_id=None).values_list("hero_id", flat=True)
    )

    return [h for h in ALL_HERO_IDS if h not in used_heroes]


def auto_random_pick(draft: HeroDraft, team: DraftTeam) -> HeroDraftRound:
    """Auto-pick a random available hero when time runs out."""
    available = get_available_heroes(draft)
    if not available:
        raise ValueError("No heroes available")

    hero_id = random.choice(available)

    # Record timeout event
    HeroDraftEvent.objects.create(
        draft=draft,
        event_type="round_timeout",
        draft_team=team,
        metadata={"auto_picked_hero": hero_id},
    )

    # Submit the pick
    return submit_pick(draft, team, hero_id)
