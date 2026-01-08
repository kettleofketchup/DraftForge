"""
Pydantic-based test tournament configuration.

Provides typed, self-documenting configuration for test tournament scenarios.
Each TestTournamentConfig represents a specific test scenario with explicit
typing and documentation of its purpose.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, PrivateAttr

log = logging.getLogger(__name__)


class BracketGameConfig(BaseModel):
    """Configuration for a single bracket game."""

    round: int = Field(description="Round number in bracket")
    bracket_type: Literal["winners", "losers", "grand_finals"] = Field(
        description="Which bracket this game belongs to"
    )
    position: int = Field(default=0, description="Position within round (0-indexed)")
    team_indices: Optional[tuple[int, int]] = Field(
        default=None,
        description="Indices of teams from tournament.teams (None = derive from previous results)",
    )


class TestTournamentConfig(BaseModel):
    """
    Configuration for a test tournament scenario.

    Each config represents a specific test scenario with explicit typing
    and documentation of its purpose.

    Example:
        config = TestTournamentConfig(
            key="draft_captain_turn",
            name="Captain Turn Test",
            description="Draft where test user is captain with pending pick",
            draft_state="in_progress",
            picks_completed=0,
            first_captain_is_test_user=True,
        )
        tournament = config.create()
    """

    key: str = Field(
        description="Unique key for referencing in tests (e.g., 'draft_in_progress')"
    )
    name: str = Field(description="Tournament name displayed in UI and tests")
    description: str = Field(description="What this tournament is used to test")

    # Tournament settings
    num_teams: int = Field(default=4, description="Number of teams to create")
    tournament_type: Literal["single_elimination", "double_elimination", "swiss"] = (
        Field(default="double_elimination")
    )
    tournament_state: Literal["future", "in_progress", "past"] = Field(
        default="in_progress"
    )

    # Draft settings
    draft_state: Literal["not_started", "in_progress", "completed"] = Field(
        default="not_started",
        description="Draft progress: not_started=no draft, in_progress=some picks, completed=all picks",
    )
    draft_style: Literal["snake", "normal", "shuffle"] = Field(default="snake")
    picks_completed: int = Field(
        default=0,
        description="Number of draft picks already made (0 = first captain's turn)",
    )

    # Bracket settings
    bracket_games: List[BracketGameConfig] = Field(
        default_factory=list, description="Bracket games to create with results"
    )
    bracket_games_completed: int = Field(
        default=0, description="How many bracket games should have results"
    )

    # Special test user handling
    first_captain_is_test_user: bool = Field(
        default=False,
        description="Set the test user as first captain (for auth testing)",
    )

    # Private attributes for internal state
    _tournament: Optional[object] = PrivateAttr(default=None)
    _results: List[tuple] = PrivateAttr(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    def create(self):
        """
        Create the tournament with all configured settings.

        Returns:
            Tournament instance with teams, draft, and bracket games configured
        """
        from app.models import Tournament

        self._tournament = Tournament.objects.create(
            name=self.name,
            date_played=date.today(),
            state=self.tournament_state,
            tournament_type=self.tournament_type,
        )

        self._create_teams()

        if self.draft_state != "not_started":
            self._create_draft()

        if self.bracket_games_completed > 0:
            self._create_bracket_games()

        if self.first_captain_is_test_user:
            self._set_test_user_as_captain()

        return self._tournament

    def _create_teams(self) -> None:
        """Create teams with captains and members."""
        from app.models import CustomUser, Team

        users = list(CustomUser.objects.all()[: self.num_teams * 5])
        if len(users) < self.num_teams * 5:
            log.warning(
                f"Not enough users ({len(users)}) for {self.num_teams} teams of 5"
            )

        self._tournament.users.set(users)

        for i in range(self.num_teams):
            captain = users[i * 5] if i * 5 < len(users) else None
            team_members = users[i * 5 : (i + 1) * 5]

            team = Team.objects.create(
                tournament=self._tournament,
                name=f"Team {i + 1}",
                captain=captain,
                draft_order=i + 1,
            )
            team.members.set(team_members)

    def _create_draft(self) -> None:
        """Create draft with rounds and apply picks."""
        from app.models import Draft

        draft = Draft.objects.create(
            tournament=self._tournament,
            draft_style=self.draft_style,
        )
        draft.build_rounds()

        if self.picks_completed > 0:
            captain_pks = list(
                self._tournament.teams.values_list("captain__pk", flat=True)
            )
            available = list(self._tournament.users.exclude(pk__in=captain_pks))

            for round in draft.draft_rounds.all()[: self.picks_completed]:
                if available:
                    player = available.pop(0)
                    round.pick_player(player)

    def _create_bracket_games(self) -> None:
        """Create bracket games with steam match results."""
        from app.models import Game
        from tests.helpers.steam_match import generate_steam_match

        teams = list(self._tournament.teams.all()[:4])
        self._results = []

        # Default 4-team double elim structure if not specified
        bracket_configs = self.bracket_games or self._default_bracket_structure()

        for idx, config in enumerate(bracket_configs[: self.bracket_games_completed]):
            radiant, dire = self._resolve_teams(config, teams, idx)

            if not radiant or not dire:
                continue

            match = generate_steam_match(radiant, dire)
            winner = radiant if match.radiant_win else dire
            loser = dire if match.radiant_win else radiant
            self._results.append((winner, loser))

            Game.objects.create(
                tournament=self._tournament,
                round=config.round,
                bracket_type=config.bracket_type,
                position=config.position,
                radiant_team=radiant,
                dire_team=dire,
                winning_team=winner,
                gameid=match.match_id,
                status="completed",
            )

    def _resolve_teams(self, config: BracketGameConfig, teams: list, idx: int) -> tuple:
        """Resolve teams for a bracket game from config or previous results."""
        if config.team_indices:
            return teams[config.team_indices[0]], teams[config.team_indices[1]]

        # Derive from bracket progression
        if idx == 2 and len(self._results) >= 2:  # Losers R1
            return self._results[0][1], self._results[1][1]
        elif idx == 3 and len(self._results) >= 2:  # Winners Final
            return self._results[0][0], self._results[1][0]
        elif idx == 4 and len(self._results) >= 4:  # Losers Final
            return self._results[2][0], self._results[3][1]
        elif idx == 5 and len(self._results) >= 5:  # Grand Final
            return self._results[3][0], self._results[4][0]

        return None, None

    def _default_bracket_structure(self) -> List[BracketGameConfig]:
        """Default 4-team double elimination bracket."""
        return [
            BracketGameConfig(
                round=1, bracket_type="winners", position=0, team_indices=(0, 1)
            ),
            BracketGameConfig(
                round=1, bracket_type="winners", position=1, team_indices=(2, 3)
            ),
            BracketGameConfig(round=1, bracket_type="losers", position=0),
            BracketGameConfig(round=2, bracket_type="winners", position=0),
            BracketGameConfig(round=2, bracket_type="losers", position=0),
            BracketGameConfig(round=1, bracket_type="grand_finals", position=0),
        ]

    def _set_test_user_as_captain(self) -> None:
        """Make test user the first captain for auth testing."""
        from tests.test_auth import createTestUser

        test_user, _ = createTestUser()
        first_team = self._tournament.teams.order_by("draft_order").first()

        if first_team and first_team.captain:
            old_captain = first_team.captain
            first_team.captain = test_user
            first_team.members.remove(old_captain)
            first_team.members.add(test_user)
            first_team.save()
            self._tournament.users.add(test_user)


# Pre-defined test scenarios
TEST_TOURNAMENTS: List[TestTournamentConfig] = [
    TestTournamentConfig(
        key="draft_not_started",
        name="Draft Not Started",
        description="Tournament with teams but no draft initialized. Tests draft creation UI.",
        draft_state="not_started",
    ),
    TestTournamentConfig(
        key="draft_in_progress",
        name="Draft In Progress",
        description="Active draft with 3 picks made. Tests draft continuation and live view.",
        draft_state="in_progress",
        picks_completed=3,
    ),
    TestTournamentConfig(
        key="draft_captain_turn",
        name="Captain Turn Test",
        description="Draft where test user is captain with pending pick. Tests captain auth flow.",
        draft_state="in_progress",
        picks_completed=0,
        first_captain_is_test_user=True,
    ),
    TestTournamentConfig(
        key="draft_completed",
        name="Draft Completed",
        description="Fully drafted tournament. Tests transition to bracket phase.",
        draft_state="completed",
        picks_completed=16,
    ),
    TestTournamentConfig(
        key="bracket_partial",
        name="Bracket Partial",
        description="Tournament with 2 bracket games completed. Tests bracket progression.",
        draft_state="completed",
        picks_completed=16,
        bracket_games_completed=2,
    ),
    TestTournamentConfig(
        key="bracket_complete",
        name="Bracket Complete",
        description="Fully completed tournament. Tests final standings and history view.",
        draft_state="completed",
        picks_completed=16,
        bracket_games_completed=6,
    ),
    TestTournamentConfig(
        key="shuffle_draft_not_started",
        name="Shuffle Draft Not Started",
        description="Tournament with shuffle draft style ready to start. Tests shuffle draft initialization.",
        draft_state="not_started",
        draft_style="shuffle",
    ),
    TestTournamentConfig(
        key="shuffle_draft_in_progress",
        name="Shuffle Draft In Progress",
        description="Active shuffle draft with 2 picks made. Tests MMR-based pick order and tie resolution.",
        draft_state="in_progress",
        draft_style="shuffle",
        picks_completed=2,
    ),
    TestTournamentConfig(
        key="shuffle_draft_captain_turn",
        name="Shuffle Draft Captain Turn",
        description="Shuffle draft where test user is captain with pending pick. Tests captain auth with shuffle.",
        draft_state="in_progress",
        draft_style="shuffle",
        picks_completed=0,
        first_captain_is_test_user=True,
    ),
]

# Mapping from key to tournament name for lookups
TEST_KEY_TO_NAME = {config.key: config.name for config in TEST_TOURNAMENTS}


def get_tournament_config(key: str) -> TestTournamentConfig:
    """
    Get a tournament config by key.

    Args:
        key: Configuration key (e.g., 'draft_captain_turn')

    Returns:
        TestTournamentConfig for the specified key

    Raises:
        ValueError: If key is not found
    """
    for config in TEST_TOURNAMENTS:
        if config.key == key:
            return config
    raise ValueError(f"Unknown tournament config key: {key}")


def populate_test_tournaments(force: bool = False) -> list:
    """
    Create all test scenario tournaments.

    Args:
        force: If True, delete existing test tournaments and recreate

    Returns:
        List of created Tournament instances
    """
    from app.models import Tournament
    from tests.helpers.steam_match import reset_match_id_tracker

    reset_match_id_tracker()

    existing = Tournament.objects.filter(name__in=[t.name for t in TEST_TOURNAMENTS])

    if existing.exists() and not force:
        print("Test tournaments exist. Use force=True to recreate.")
        return list(existing)

    if force:
        existing.delete()

    created = []
    for config in TEST_TOURNAMENTS:
        tournament = config.create()
        created.append(tournament)
        print(f"Created: {tournament.name} (key: {config.key})")

    print(f"\nCreated {len(created)} test tournaments")
    return created
