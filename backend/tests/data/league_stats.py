import random

from pydantic import BaseModel

from tests.data.models import TestUser

STRIP_STATS_TOURNAMENT_PK = 250
STRIP_STATS_TOURNAMENT_NAME = "Strip Stats Tournament"
STRIP_STATS_MATCH_ID_BASE = 9200000000
STRIP_STATS_MATCH_ID_MAX = 9200009999
STRIP_STATS_START_TIME_BASE = 1760000000


class StripStatsPlayer(BaseModel):
    user: TestUser
    sequence: str
    org_mmr: int
    league_mmr: int
    captain: bool = False


def _user(pk: int, username: str, nickname: str) -> TestUser:
    return TestUser(
        pk=pk,
        username=username,
        nickname=nickname,
        discord_id=f"72000000000000{pk}",
        steam_id_64=76561199072000000 + pk,
    )


STRIP_STATS_PLAYERS: list[StripStatsPlayer] = [
    StripStatsPlayer(
        user=_user(7000, "strip_ace", "Strip Ace"),
        sequence="WWWWWWLW",
        org_mmr=4200,
        league_mmr=4200,
    ),
    StripStatsPlayer(
        user=_user(7001, "strip_hot", "Strip Hot"),
        sequence="LLWWWW",
        org_mmr=3900,
        league_mmr=3900,
    ),
    StripStatsPlayer(
        user=_user(7002, "strip_tie_a", "Strip Tie A"),
        sequence="WLWLW",
        org_mmr=3500,
        league_mmr=3500,
    ),
    StripStatsPlayer(
        user=_user(7003, "strip_tie_b", "Strip Tie B"),
        sequence="LWWLW",
        org_mmr=3400,
        league_mmr=3400,
    ),
    StripStatsPlayer(
        user=_user(7004, "strip_cold", "Strip Cold"),
        sequence="WWWLLL",
        org_mmr=3300,
        league_mmr=0,
    ),
    StripStatsPlayer(
        user=_user(7005, "strip_mid", "Strip Mid"),
        sequence="LWLLWLL",
        org_mmr=3200,
        league_mmr=0,
    ),
    StripStatsPlayer(
        user=_user(7006, "strip_rookie", "Strip Rookie"),
        sequence="WLW",
        org_mmr=3100,
        league_mmr=0,
    ),
    StripStatsPlayer(
        user=_user(7007, "strip_zero", "Strip Zero"),
        sequence="",
        org_mmr=3000,
        league_mmr=0,
    ),
    StripStatsPlayer(
        user=_user(7008, "strip_capt_a", "Strip Capt A"),
        sequence="LLWLL",
        org_mmr=2900,
        league_mmr=0,
        captain=True,
    ),
    StripStatsPlayer(
        user=_user(7009, "strip_capt_b", "Strip Capt B"),
        sequence="",
        org_mmr=2800,
        league_mmr=0,
        captain=True,
    ),
]


# Showcase league: a seeded, realistic league for demos and manual checks of the
# strip column and the win-rate histogram. Tests assert its shape, not its values.
SHOWCASE_TOURNAMENT_PK = 251
SHOWCASE_TOURNAMENT_NAME = "League Stats Showcase"
SHOWCASE_MATCH_ID_BASE = 9200010000
SHOWCASE_MATCH_ID_MAX = 9200099999
SHOWCASE_START_TIME_BASE = 1750000000
SHOWCASE_SEED = 20261112
SHOWCASE_MATCH_COUNT = 160
SHOWCASE_CAPTAIN_COUNT = 8
SHOWCASE_NEWCOMER_GAMES: tuple[int, ...] = (1, 2, 4)
SHOWCASE_IDLE_COUNT = 3


class ShowcasePlayer(BaseModel):
    user: TestUser
    skill: float
    activity: float
    fixed_games: int | None = None
    org_mmr: int


def _showcase_players() -> list[ShowcasePlayer]:
    rng = random.Random(SHOWCASE_SEED)
    regulars = 60 - len(SHOWCASE_NEWCOMER_GAMES) - SHOWCASE_IDLE_COUNT
    players: list[ShowcasePlayer] = []
    for index in range(60):
        pk = 7100 + index
        skill = rng.gauss(0.0, 1.0)
        if index < regulars:
            activity, fixed = rng.uniform(0.3, 1.5), None
        elif index < regulars + len(SHOWCASE_NEWCOMER_GAMES):
            activity, fixed = 0.0, SHOWCASE_NEWCOMER_GAMES[index - regulars]
        else:
            activity, fixed = 0.0, 0
        players.append(
            ShowcasePlayer(
                user=_user(pk, f"showcase_{index:02d}", f"Showcase {index:02d}"),
                skill=skill,
                activity=activity,
                fixed_games=fixed,
                org_mmr=max(1000, int(round(3500 + skill * 900, -1))),
            )
        )
    return players


SHOWCASE_PLAYERS: list[ShowcasePlayer] = _showcase_players()
