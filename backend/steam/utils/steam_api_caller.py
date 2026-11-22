import os
from typing import Any

import requests

from steam.utils.retry import throttle_request
from telemetry.logging import get_logger

log = get_logger(__name__)


class SteamAPI:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("STEAM_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Steam API key not provided or found in environment variables."
            )
        self.base_url = "https://api.steampowered.com"

    @throttle_request(min_delay=0.5)
    def _request(
        self,
        interface: str,
        method: str,
        version: int,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return self._request_unthrottled(interface, method, version, params)

    def _request_unthrottled(
        self,
        interface: str,
        method: str,
        version: int,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | tuple[float, float] = 10,
    ) -> dict[str, Any] | None:
        params = dict(params or {})
        params["key"] = self.api_key
        url = f"{self.base_url}/{interface}/{method}/v{version}/"
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Steam returns useful detail in the body for 401/403/429/5xx;
            # capture status code + body snippet so the warning is actually
            # debuggable instead of just "fetch_failed".
            log.warning(
                "steam_api_request_failed",
                system="steam",
                subsystem="api",
                interface=interface,
                method=method,
                status_code=e.response.status_code if e.response is not None else None,
                body=(e.response.text[:200] if e.response is not None else None),
            )
            return None
        except requests.exceptions.RequestException as e:
            log.warning(
                "steam_api_request_failed",
                system="steam",
                subsystem="api",
                interface=interface,
                method=method,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    def get_player_summaries(
        self,
        steamids: int | list[int],
        *,
        timeout: float | tuple[float, float] = 10,
    ) -> dict[str, Any] | None:
        ids = steamids if isinstance(steamids, list) else [steamids]
        return self._request_unthrottled(
            "ISteamUser",
            "GetPlayerSummaries",
            2,
            {"steamids": ",".join(str(i) for i in ids)},
            timeout=timeout,
        )

    def get_match_details(self, match_id: int) -> dict[str, Any] | None:
        """
        Get detailed information about a single match.
        """
        return self._request(
            "IDOTA2Match_570", "GetMatchDetails", 1, {"match_id": match_id}
        )

    def get_match_history(
        self,
        league_id: int,
        start_at_match_id: int | None = None,
        matches_requested: int = 100,
    ) -> dict[str, Any] | None:
        """
        Fetch match history for a league.
        Use start_at_match_id for pagination (fetches matches BEFORE this ID).
        """
        params: dict[str, Any] = {
            "league_id": league_id,
            "matches_requested": matches_requested,
        }
        if start_at_match_id:
            params["start_at_match_id"] = start_at_match_id
        return self._request("IDOTA2Match_570", "GetMatchHistory", 1, params)

    def get_live_league_games(
        self, league_id: int | None = None
    ) -> dict[str, Any] | None:
        """Fetch currently live games. Optionally filter by league."""
        params: dict[str, Any] = {}
        if league_id:
            params["league_id"] = league_id
        return self._request("IDOTA2Match_570", "GetLiveLeagueGames", 1, params)

    def get_match_history_by_seq_num(
        self, start_at_match_seq_num: int, matches_requested: int = 1
    ) -> dict[str, Any] | None:
        """
        Get detailed match information using match sequence number.
        This is more reliable than GetMatchDetails for getting full player stats.

        Args:
            start_at_match_seq_num: The match sequence number to start from
            matches_requested: Number of matches to fetch (default 1)

        Returns:
            API response with detailed match data including player stats
        """
        params = {
            "start_at_match_seq_num": start_at_match_seq_num,
            "matches_requested": matches_requested,
        }
        return self._request(
            "IDOTA2Match_570", "GetMatchHistoryBySequenceNum", 1, params
        )
