"""Per-game org MMR E2E test data.

Used by frontend/tests/playwright/e2e/11-org-mmr/04-game-org-mmr.spec.ts and
e2e/16-events/17-deadlock-org-mmr-approve.spec.ts. Created by
tests.populate.game_org_mmr.populate_game_org_mmr_data.

- Org / league 50 "Game MMR Org" / "Game MMR League" (steam league 17944).
- Users 8000-8007, each with a Dota 2 and (except 8007) a Deadlock org MMR;
  Dota and Deadlock orderings differ.
  - 8000-8004: display fixtures, read-only in specs.
  - 8005: owned by 04 (b), which sets its values per test.
  - 8006: owned by 04 (a), the edit user; reset to 3000 / 1500 per test.
  - 8007: the approve user, Deadlock rank "Phantom 4 (e2e)"; no Deadlock MMR.
- "Game MMR Dota Cup" (Dota 2) and "Game MMR Deadlock Cup" (Deadlock, created
  from the "Game MMR Deadlock Night" event), both in league 50, users 8000-8006.
"""

from dataclasses import dataclass
from typing import Final

from tests.data.models import TestLeague, TestOrganization, TestUser

GAME_MMR_ORG: TestOrganization = TestOrganization(
    pk=50,
    name="Game MMR Org",
    description="Isolated organization for the per-game org MMR E2E tests.",
    timezone="America/New_York",
)

GAME_MMR_LEAGUE: TestLeague = TestLeague(
    pk=50,
    name="Game MMR League",
    steam_league_id=17944,
    organization_names=[GAME_MMR_ORG.name],
)

GAME_MMR_DOTA_TOURNAMENT_NAME: Final[str] = "Game MMR Dota Cup"
GAME_MMR_DEADLOCK_EVENT_NAME: Final[str] = "Game MMR Deadlock Night"
GAME_MMR_DEADLOCK_TOURNAMENT_NAME: Final[str] = "Game MMR Deadlock Cup"
GAME_MMR_APPROVE_EVENT_NAME: Final[str] = "Game MMR Deadlock Approve"
GAME_MMR_APPROVE_TOURNAMENT_NAME: Final[str] = "Game MMR Deadlock Approve Cup"
GAME_MMR_APPROVE_RANK: Final[str] = "Phantom 4 (e2e)"
GAME_MMR_APPROVE_DOTA: Final[int] = 3300

GAME_MMR_DISCORD_BASE: Final[int] = 800_000_000_000_000_000


@dataclass(frozen=True)
class GameMmrPlayer:
    user: TestUser
    dota: int
    deadlock: int | None


def _user(pk: int, username: str, nickname: str) -> TestUser:
    return TestUser(
        pk=pk,
        username=username,
        nickname=nickname,
        discord_id=str(GAME_MMR_DISCORD_BASE + pk),
    )


GAME_MMR_EDIT_USER: TestUser = _user(8006, "gom_edit", "GOM Edit")
GAME_MMR_DISPLAY_USER: TestUser = _user(8005, "gom_display", "GOM Display")
GAME_MMR_APPROVE_USER: TestUser = _user(8007, "gom_approve", "GOM Approve")

GAME_MMR_PLAYERS: Final[tuple[GameMmrPlayer, ...]] = (
    GameMmrPlayer(_user(8000, "gom_player_1", "GOM Player 1"), 5200, 1100),
    GameMmrPlayer(_user(8001, "gom_player_2", "GOM Player 2"), 4400, 1900),
    GameMmrPlayer(_user(8002, "gom_player_3", "GOM Player 3"), 3600, 2700),
    GameMmrPlayer(_user(8003, "gom_player_4", "GOM Player 4"), 2800, 3500),
    GameMmrPlayer(_user(8004, "gom_player_5", "GOM Player 5"), 2000, 4300),
    GameMmrPlayer(GAME_MMR_DISPLAY_USER, 3100, 2600),
    GameMmrPlayer(GAME_MMR_EDIT_USER, 3000, 1500),
    GameMmrPlayer(GAME_MMR_APPROVE_USER, GAME_MMR_APPROVE_DOTA, None),
)

GAME_MMR_TOURNAMENT_USERS: Final[tuple[TestUser, ...]] = tuple(
    p.user for p in GAME_MMR_PLAYERS if p.user.pk != GAME_MMR_APPROVE_USER.pk
)
