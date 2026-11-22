"""Shuffle draft logic - lowest MMR picks first."""

import random
from datetime import datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from app.models import CustomUser, Team
from draft.models import Draft, DraftEvent, DraftRound
from draft.services.team_broadcast import broadcast_event_after_commit
from org.mmr import game_for_tournament, org_mmr_for, org_mmr_map
from org.models import Organization

# Maximum team size (captain + 4 drafted players)
MAX_TEAM_SIZE = 5


def get_user_org_mmr(
    user: CustomUser, organization: Organization | None, game_type: int
) -> int:
    """The user's org MMR for ``game_type`` in ``organization``; 0 without one."""
    if organization is None:
        return 0
    return org_mmr_for(organization.pk, user.pk, game_type)


def get_team_total_mmr(team: Team, organization: Organization | None = None) -> int:
    """Total org MMR (captain + members) for the game of the team's tournament."""
    tournament = team.tournament
    if organization is None and tournament and tournament.league:
        organization = tournament.league.organization
    if organization is None:
        return 0

    member_ids = set(team.members.values_list("id", flat=True))
    if team.captain_id:
        member_ids.add(team.captain_id)
    mmrs = org_mmr_map(organization.pk, member_ids, game_for_tournament(tournament))
    return sum(mmrs.get(uid, 0) for uid in member_ids)


def roll_until_winner(teams: list) -> tuple:
    """
    Roll dice until one winner emerges.

    Args:
        teams: List of Team model instances

    Returns:
        Tuple of (winner_team, roll_rounds)
        roll_rounds is list of rounds, each round is list of {"team_id": N, "roll": N}
    """
    roll_rounds = []
    remaining = list(teams)

    while len(remaining) > 1:
        rolls = [{"team_id": t.id, "roll": random.randint(1, 6)} for t in remaining]
        roll_rounds.append(rolls)

        max_roll = max(r["roll"] for r in rolls)
        remaining = [
            t
            for t in remaining
            if next(r["roll"] for r in rolls if r["team_id"] == t.id) == max_roll
        ]

    return remaining[0], roll_rounds


TIE_ROLL_HOLD_MS = 5000


def get_lowest_mmr_team(teams: list) -> tuple:
    """
    Find team with lowest total MMR.

    Args:
        teams: List of Team model instances

    Returns:
        Tuple of (winner_team, tie_resolution_data or None)
    """
    team_mmrs = [(team, get_team_total_mmr(team)) for team in teams]
    min_mmr = min(mmr for _, mmr in team_mmrs)
    tied = [t for t, mmr in team_mmrs if mmr == min_mmr]

    if len(tied) > 1:
        winner, roll_rounds = roll_until_winner(tied)
        tie_data = {
            "tied_teams": [
                {"id": t.id, "name": t.name, "mmr": get_team_total_mmr(t)} for t in tied
            ],
            "roll_rounds": roll_rounds,
            "winner_id": winner.id,
            "hold_ms": TIE_ROLL_HOLD_MS,
        }
        return winner, tie_data

    return tied[0], None


def build_shuffle_rounds(draft: Draft, teams: QuerySet[Team] | None = None) -> None:
    """Create all rounds for a shuffle draft over ``teams`` and assign the first captain."""
    teams = list(draft.teams if teams is None else teams)
    num_teams = len(teams)
    total_picks = num_teams * 4

    # Create all rounds with null captains
    rounds = [
        DraftRound(
            draft=draft,
            captain=None,
            pick_number=i,
            pick_phase=(i - 1) // num_teams + 1,
        )
        for i in range(1, total_picks + 1)
    ]
    DraftRound.objects.bulk_create(rounds)

    # Assign first captain based on lowest captain MMR
    first_team, tie_data = get_lowest_mmr_team(teams)
    first_round = draft.draft_rounds.order_by("pick_number").first()
    first_round.captain = first_team.captain
    if tie_data:
        first_round.was_tie = True
        first_round.tie_roll_data = tie_data
    first_round.save()

    # Create draft_started event
    event = DraftEvent.objects.create(
        draft=draft,
        event_type="draft_started",
        payload={
            "draft_id": draft.pk,
            "draft_style": draft.draft_style,
            "team_count": num_teams,
        },
    )
    broadcast_event_after_commit(event)


def reassign_round_captain(
    draft: Draft,
    round: DraftRound,
    exclude_team_ids: set[int],
    *,
    reason: str | None = None,
    now: datetime | None = None,
) -> dict | None:
    """Assign the lowest-MMR eligible team's captain to `round`; None if no team is eligible.

    A tie carries ``hold_until``: ``now`` plus the hold, which is when the next clock starts.
    """
    eligible_teams = [
        t
        for t in draft.teams
        if t.members.count() < MAX_TEAM_SIZE and t.pk not in exclude_team_ids
    ]
    if not eligible_teams:
        return None

    round.was_tie = False
    round.tie_roll_data = None
    next_team, tie_data = get_lowest_mmr_team(eligible_teams)
    round.captain = next_team.captain
    if tie_data:
        tie_data["pick_number"] = round.pick_number
        hold = timedelta(milliseconds=tie_data["hold_ms"])
        tie_data["hold_until"] = ((now or timezone.now()) + hold).isoformat()
        round.was_tie = True
        round.tie_roll_data = tie_data
    round.save()

    captain = next_team.captain
    payload: dict = {
        "pick_number": round.pick_number,
        "captain_id": captain.pk,
        "captain_name": captain.username,
        "captain_avatar_url": captain.avatarUrl,
        "team_id": next_team.pk,
        "team_name": next_team.name,
        "team_mmr": get_team_total_mmr(next_team),
    }
    if reason is not None:
        payload["reason"] = reason
    captain_event = DraftEvent.objects.create(
        draft=draft, event_type="captain_assigned", payload=payload
    )
    broadcast_event_after_commit(captain_event)

    if tie_data:
        tie_event = DraftEvent.objects.create(
            draft=draft,
            event_type="tie_roll",
            payload={
                "pick_number": round.pick_number,
                "tied_teams": tie_data["tied_teams"],
                "roll_rounds": tie_data["roll_rounds"],
                "winner_id": tie_data["winner_id"],
                "winner_name": captain.username,
                "hold_ms": tie_data["hold_ms"],
                "hold_until": tie_data["hold_until"],
            },
        )
        broadcast_event_after_commit(tie_event)

    return tie_data


def assign_next_shuffle_captain(
    draft: Draft, *, now: datetime | None = None
) -> dict | None:
    """After a pick, assign captain to the next captain-less round.

    Returns tie resolution data if a tie occurred, else None.
    """
    next_round = (
        draft.draft_rounds.filter(captain__isnull=True).order_by("pick_number").first()
    )
    if next_round is None:
        return None
    return reassign_round_captain(draft, next_round, set(), now=now)
