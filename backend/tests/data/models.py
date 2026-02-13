"""
Pydantic Models for Test Data

All test data models are defined here for consistency.
Individual data files import these models and define specific instances.
"""

from pydantic import BaseModel

# =============================================================================
# User Models
# =============================================================================


class TestPositions(BaseModel):
    """Position preferences (0-5 scale, higher = more preferred)."""

    carry: int = 3
    mid: int = 3
    offlane: int = 3
    soft_support: int = 3
    hard_support: int = 3


class TestUser(BaseModel):
    """Test user configuration."""

    pk: int | None = None  # None for dynamically created users
    username: str | None = None
    nickname: str | None = None
    discord_id: str | None = None
    steam_id: int | None = None  # 32-bit Steam ID (will be converted to 64-bit)
    steam_id_64: int | None = None  # Full 64-bit Steam ID (if already converted)
    mmr: int | None = None
    is_staff: bool = False
    is_superuser: bool = False
    org_id: int | None = None  # For org role users
    league_id: int | None = None  # For league role users
    positions: TestPositions | None = None

    def get_steam_id_64(self) -> int | None:
        """Get 64-bit Steam ID, converting from 32-bit if needed."""
        if self.steam_id_64:
            return self.steam_id_64
        if self.steam_id:
            return 76561197960265728 + self.steam_id
        return None

    def get_steam_account_id(self) -> int | None:
        """Get 32-bit Friend ID (Dotabuff), converting from 64-bit if needed."""
        if self.steam_id:
            return self.steam_id
        if self.steam_id_64:
            return self.steam_id_64 - 76561197960265728
        return None


# =============================================================================
# Organization Models
# =============================================================================


class TestOrganization(BaseModel):
    """Test organization configuration."""

    pk: int | None = None  # Set after creation
    name: str
    description: str = ""
    logo: str = ""
    rules_template: str = ""
    timezone: str = "America/New_York"
    default_league_id: int | None = None
    discord_server_id: str | None = None  # Discord server ID for the organization


class TestLeague(BaseModel):
    """Test league configuration."""

    pk: int | None = None  # Set after creation
    name: str
    steam_league_id: int
    description: str = ""
    rules: str = ""
    prize_pool: str = ""
    timezone: str = "America/New_York"
    organization_names: list[str] = []  # Organizations this league belongs to


# =============================================================================
# Team Models
# =============================================================================


class TestTeam(BaseModel):
    """Test team configuration."""

    pk: int | None = None  # Set after creation
    name: str
    captain: "TestUser"  # Captain user object
    members: list["TestUser"] = []  # Member user objects (including captain)
    draft_order: int | None = None
    tournament_name: str | None = None  # Reference to TestTournament by name


# =============================================================================
# Tournament Models
# =============================================================================


class TestTournament(BaseModel):
    """Test tournament configuration for tournaments with pre-defined teams."""

    pk: int | None = None  # Set after creation
    name: str
    tournament_type: str = "double_elimination"
    state: str = "past"
    steam_league_id: int | None = None
    league_name: str | None = None  # Reference to TestLeague by name
    organization_pk: int = 1  # Organization PK (default: DTX org)
    date_played: str | None = None  # ISO format date string
    teams: list[TestTeam] = []  # Teams in this tournament
    user_usernames: list[str] = []  # All users in tournament (if not using teams)
    # Steam match population settings
    completed_game_count: int | None = None  # Number of bracket games to mark completed
    match_id_base: int | None = None  # Base match ID for mock Steam matches


class DynamicTournamentConfig(BaseModel):
    """Configuration for dynamically created tournaments with mock users/teams.

    These tournaments are created with generated users and teams,
    unlike TestTournament which uses pre-defined TestUser/TestTeam objects.
    """

    pk: int  # Required - used for consistent database access
    name: str
    user_count: int  # Number of mock users to create
    team_count: int  # Number of teams to create
    tournament_type: str = "double_elimination"
    league_name: str = "DTX League"  # Reference to league by name
    organization_pk: int = 1  # Organization PK (default: DTX org)
    # Steam match population settings
    completed_game_count: int | None = None  # Number of bracket games to mark completed
    match_id_base: int | None = None  # Base match ID for mock Steam matches

    def create(self) -> "Tournament":  # noqa: F821
        """Create this tournament in the database.

        Returns:
            Tournament: The created Django Tournament model instance
        """
        from tests.populate.tournaments import create_dynamic_tournament

        return create_dynamic_tournament(self)
