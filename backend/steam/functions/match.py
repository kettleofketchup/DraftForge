from steam.models import Match, PlayerMatchStats
from steam.utils.steam_api_caller import SteamAPI


def update_match_details(match_id):
    """
    Fetches match details from the Steam Web API and updates the database.
    """
    api = SteamAPI()
    data = api.get_match_details(match_id)

    if not data or "result" not in data:
        return None

    result = data["result"]

    match, created = Match.objects.update_or_create(
        match_id=result["match_id"],
        defaults={
            "radiant_win": result.get("radiant_win", False),
            "duration": result.get("duration", 0),
            "start_time": result.get("start_time", 0),
            "game_mode": result.get("game_mode", 0),
            "lobby_type": result.get("lobby_type", 0),
        },
    )

    for player_data in result.get("players", []):
        # Steam API uses 'account_id', but we're mapping it to 'steam_id'
        steam_id_32 = player_data.get("account_id")
        if steam_id_32 is None:
            continue

        # Convert 32-bit steam_id to 64-bit
        steam_id_64 = steam_id_32 + 76561197960265728

        PlayerMatchStats.objects.update_or_create(
            match=match,
            steam_id=steam_id_64,
            defaults={
                "player_slot": player_data.get("player_slot"),
                "hero_id": player_data.get("hero_id"),
                "kills": player_data.get("kills"),
                "deaths": player_data.get("deaths"),
                "assists": player_data.get("assists"),
                "gold_per_min": player_data.get("gold_per_min"),
                "xp_per_min": player_data.get("xp_per_min"),
                "last_hits": player_data.get("last_hits"),
                "denies": player_data.get("denies"),
                "hero_damage": player_data.get("hero_damage"),
                "tower_damage": player_data.get("tower_damage"),
                "hero_healing": player_data.get("hero_healing"),
            },
        )

    return match
