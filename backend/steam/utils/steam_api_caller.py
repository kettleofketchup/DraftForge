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
