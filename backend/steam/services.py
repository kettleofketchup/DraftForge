import os

import requests

from steam.constants import LEAGUE_ID
from steam.utils import get_steam_api_key

from .models import Match, PlayerMatchStats


def get_match_details(match_id):
    """
    Fetches match details from the Steam Web API and updates the database.
    """
    api_key = get_steam_api_key()

    # This is a mock response for now, based on the Steam API structure.
    # In the future, we will replace this with an actual API call.
    mock_response = {
        "result": {
            "players": [
                {
                    "account_id": 12345,
                    "player_slot": 0,
                    "hero_id": 5,
                    "kills": 10,
                    "deaths": 2,
                    "assists": 15,
                    "gold_per_min": 600,
                    "xp_per_min": 700,
                    "last_hits": 300,
                    "denies": 20,
                    "hero_damage": 25000,
                    "tower_damage": 5000,
                    "hero_healing": 1000,
                }
                # ... more players
            ],
            "radiant_win": True,
            "duration": 2700,
            "start_time": 1678886400,
            "match_id": match_id,
            "game_mode": 22,
            "lobby_type": 7,
        }
    }

    result = mock_response.get("result", {})
    if not result:
        return None

    match, created = Match.objects.update_or_create(
        match_id=result["match_id"],
        defaults={
            "radiant_win": result["radiant_win"],
            "duration": result["duration"],
            "start_time": result["start_time"],
            "game_mode": result["game_mode"],
            "lobby_type": result["lobby_type"],
        },
    )

    for player_data in result.get("players", []):
        PlayerMatchStats.objects.update_or_create(
            match=match,
            steam_id=player_data["account_id"],  # Note: Steam API uses account_id
            defaults={
                "player_slot": player_data["player_slot"],
                "hero_id": player_data["hero_id"],
                "kills": player_data["kills"],
                "deaths": player_data["deaths"],
                "assists": player_data["assists"],
                "gold_per_min": player_data["gold_per_min"],
                "xp_per_min": player_data["xp_per_min"],
                "last_hits": player_data["last_hits"],
                "denies": player_data["denies"],
                "hero_damage": player_data["hero_damage"],
                "tower_damage": player_data["tower_damage"],
                "hero_healing": player_data["hero_healing"],
            },
        )

    return match
