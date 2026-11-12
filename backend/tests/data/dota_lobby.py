"""Dota lobby E2E test data: the DraftForge <-> dota_lobby integration.

Used by frontend/tests/playwright/e2e/18-dota-lobby/ against the simulated
dota_lobby in the test stack (docker/dota-lobby/simulator.yaml, whose bots
administer LOBBY_STEAM_LEAGUE_ID). populate_dota_lobby_data creates it and
reset_dota_lobby_data puts it back between spec files.

- "Lobby Test Org" and "Lobby Test League" (steam league 17940).
- "Lobby Test Series": a paused series in fixed password mode
  (LOBBY_FIXED_PASSWORD) with one upcoming, on-schedule event and its
  tournament (four teams, single elimination).
- "Lobby Random Event": a one-off event in random password mode with its
  tournament (two teams).
- "Lobby Lifecycle Tournament": a standalone in-progress tournament (two
  teams) for the lobby lifecycle spec.

Every tournament hosts lobbies in manual mode, so nothing creates a lobby
until a spec asks for one. Every rostered player has a Steam account ID.

Users (pk 7200-7299):

- 7200 lobby_staff: admin of the Lobby Test Org
- 7201 lobby_rostered: captain of "Lobby Gamma" in the series tournament
- 7202 lobby_registered: approved signup for the series event, on no team
- 7203 lobby_unregistered: no signup, no team
- 7204 lobby_league_staff: staff of the Lobby Test League only
- 7210-7216, 7220-7223, 7230-7233: the other rostered players
"""

from tests.data.models import TestLeague, TestOrganization, TestUser

LOBBY_ORG: TestOrganization = TestOrganization(
    name="Lobby Test Org",
    description="Isolated organization for the dota_lobby E2E tests.",
    timezone="America/New_York",
)

LOBBY_STEAM_LEAGUE_ID = 17940

LOBBY_LEAGUE: TestLeague = TestLeague(
    name="Lobby Test League",
    steam_league_id=LOBBY_STEAM_LEAGUE_ID,
    organization_names=[LOBBY_ORG.name],
)

LOBBY_SERIES_NAME = "Lobby Test Series"
LOBBY_SERIES_TOURNAMENT_NAME = "Lobby Test Series Tournament"
# dota_lobby accepts 1-32 printable ASCII characters.
LOBBY_FIXED_PASSWORD = "LobbyTest-Fixed1"

LOBBY_RANDOM_EVENT_NAME = "Lobby Random Event"
LOBBY_RANDOM_TOURNAMENT_NAME = "Lobby Random Tournament"

LOBBY_LIFECYCLE_TOURNAMENT_NAME = "Lobby Lifecycle Tournament"

LOBBY_TOURNAMENT_NAMES = (
    LOBBY_SERIES_TOURNAMENT_NAME,
    LOBBY_RANDOM_TOURNAMENT_NAME,
    LOBBY_LIFECYCLE_TOURNAMENT_NAME,
)

# account_id = LOBBY_STEAM_ACCOUNT_BASE + (pk - 7200): unique 32-bit IDs.
LOBBY_STEAM_ACCOUNT_BASE = 307_000_000


def _user(pk: int, username: str, nickname: str) -> TestUser:
    return TestUser(
        pk=pk,
        username=username,
        nickname=nickname,
        discord_id=str(710_000_000_000_000_000 + pk),
        steam_id=LOBBY_STEAM_ACCOUNT_BASE + (pk - 7200),
    )


LOBBY_STAFF_USER = _user(7200, "lobby_staff", "Lobby Staff")
LOBBY_ROSTERED_USER = _user(7201, "lobby_rostered", "Lobby Rostered")
LOBBY_REGISTERED_USER = _user(7202, "lobby_registered", "Lobby Registered")
LOBBY_UNREGISTERED_USER = _user(7203, "lobby_unregistered", "Lobby Unregistered")
LOBBY_LEAGUE_STAFF_USER = _user(7204, "lobby_league_staff", "Lobby League Staff")

# Login roles for /api/tests/login-dota-lobby/<role>/.
LOBBY_ROLE_USERS: dict[str, TestUser] = {
    "staff": LOBBY_STAFF_USER,
    "rostered": LOBBY_ROSTERED_USER,
    "registered": LOBBY_REGISTERED_USER,
    "unregistered": LOBBY_UNREGISTERED_USER,
    "league-staff": LOBBY_LEAGUE_STAFF_USER,
}

# (team name, [captain, member]) per tournament, in bracket order: teams 1
# and 2 meet in the first game, 3 and 4 in the second.
LOBBY_SERIES_TEAMS: list[tuple[str, list[TestUser]]] = [
    (
        "Lobby Alpha",
        [
            _user(7210, "lobby_alpha_1", "Alpha One"),
            _user(7211, "lobby_alpha_2", "Alpha Two"),
        ],
    ),
    (
        "Lobby Beta",
        [
            _user(7212, "lobby_beta_1", "Beta One"),
            _user(7213, "lobby_beta_2", "Beta Two"),
        ],
    ),
    ("Lobby Gamma", [LOBBY_ROSTERED_USER, _user(7214, "lobby_gamma_2", "Gamma Two")]),
    (
        "Lobby Delta",
        [
            _user(7215, "lobby_delta_1", "Delta One"),
            _user(7216, "lobby_delta_2", "Delta Two"),
        ],
    ),
]
LOBBY_LIFECYCLE_TEAMS: list[tuple[str, list[TestUser]]] = [
    (
        "Lifecycle Ravens",
        [
            _user(7220, "lobby_ravens_1", "Ravens One"),
            _user(7221, "lobby_ravens_2", "Ravens Two"),
        ],
    ),
    (
        "Lifecycle Wolves",
        [
            _user(7222, "lobby_wolves_1", "Wolves One"),
            _user(7223, "lobby_wolves_2", "Wolves Two"),
        ],
    ),
]
LOBBY_RANDOM_TEAMS: list[tuple[str, list[TestUser]]] = [
    (
        "Random Herons",
        [
            _user(7230, "lobby_herons_1", "Herons One"),
            _user(7231, "lobby_herons_2", "Herons Two"),
        ],
    ),
    (
        "Random Foxes",
        [
            _user(7232, "lobby_foxes_1", "Foxes One"),
            _user(7233, "lobby_foxes_2", "Foxes Two"),
        ],
    ),
]

LOBBY_USERS: list[TestUser] = [
    *LOBBY_ROLE_USERS.values(),
    *(
        user
        for teams in (LOBBY_SERIES_TEAMS, LOBBY_LIFECYCLE_TEAMS, LOBBY_RANDOM_TEAMS)
        for _name, players in teams
        for user in players
        if user.pk != LOBBY_ROSTERED_USER.pk
    ),
]
