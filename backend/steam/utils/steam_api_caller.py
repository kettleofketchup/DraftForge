import os

import requests


class SteamAPI:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("STEAM_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Steam API key not provided or found in environment variables."
            )
        self.base_url = "https://api.steampowered.com"

    def _request(self, interface, method, version, params=None):
        if params is None:
            params = {}
        params["key"] = self.api_key
        url = f"{self.base_url}/{interface}/{method}/v{version}/"
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()  # Raise an exception for bad status codes
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error calling Steam API: {e}")
            return None

    def get_match_details(self, match_id):
        """
        Get detailed information about a single match.
        """
        return self._request(
            "IDOTA2Match_570", "GetMatchDetails", 1, {"match_id": match_id}
        )

    def get_match_history(
        self, league_id, start_at_match_id=None, matches_requested=100
    ):
        """
        Fetch match history for a league.
        Use start_at_match_id for pagination (fetches matches BEFORE this ID).
        """
        params = {"league_id": league_id, "matches_requested": matches_requested}
        if start_at_match_id:
            params["start_at_match_id"] = start_at_match_id
        return self._request("IDOTA2Match_570", "GetMatchHistory", 1, params)

    def get_live_league_games(self, league_id=None):
        """Fetch currently live games. Optionally filter by league."""
        params = {}
        if league_id:
            params["league_id"] = league_id
        return self._request("IDOTA2Match_570", "GetLiveLeagueGames", 1, params)
