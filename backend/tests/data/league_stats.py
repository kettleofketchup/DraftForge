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
