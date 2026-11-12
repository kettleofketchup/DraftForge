from app.models import CustomUser, PositionsModel
from steam.functions.stats_update import player_won
from steam.models import Match, PlayerMatchStats


def make_player(username: str, steamid: int | None) -> CustomUser:
    return CustomUser.objects.create_user(
        username=username,
        password="testpass",
        steamid=steamid,
        positions=PositionsModel.objects.create(),
    )


def record_game(
    user: CustomUser | None,
    *,
    league_id: int,
    match_id: int,
    start_time: int,
    won: bool,
    steam_id: int | None = None,
    radiant_win: bool = True,
) -> PlayerMatchStats:
    if steam_id is None:
        if user is None or user.steamid is None:
            raise ValueError("steam_id is required when the user has no steamid")
        steam_id = user.steamid
    match, _ = Match.objects.get_or_create(
        match_id=match_id,
        defaults={
            "radiant_win": radiant_win,
            "duration": 2400,
            "start_time": start_time,
            "game_mode": 2,
            "lobby_type": 1,
            "league_id": league_id,
        },
    )
    player_slot = 0 if won == match.radiant_win else 128
    assert player_won(player_slot, match.radiant_win) is won
    return PlayerMatchStats.objects.create(
        match=match,
        steam_id=steam_id,
        user=user,
        player_slot=player_slot,
        hero_id=1,
        kills=5,
        deaths=5,
        assists=5,
        gold_per_min=500,
        xp_per_min=500,
        last_hits=100,
        denies=5,
        hero_damage=10000,
        tower_damage=1000,
        hero_healing=0,
    )


def record_series(
    user: CustomUser,
    results: str,
    *,
    league_id: int,
    first_match_id: int,
    first_start_time: int = 1_700_000_000,
) -> None:
    for i, result in enumerate(results):
        record_game(
            user,
            league_id=league_id,
            match_id=first_match_id + i,
            start_time=first_start_time + i * 3600,
            won=result == "W",
        )
