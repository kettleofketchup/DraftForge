# Steam Match Processing Design

**Date**: 2026-01-04
**Status**: Approved
**Scope**: Backend only - Steam API integration for Dota 2 league match processing

## Overview

Process matches from Steam Web API for Dota 2 league 17929, store in database, and link to users via steamid. Provides utilities for the frontend to trigger sync operations and find matches by player participation.

## Goals

1. Fetch all matches from league 17929 via Steam API
2. Store match data with player stats in database
3. Link players to `CustomUser` records via steamid
4. Provide incremental sync with failure tracking
5. Enable player-based match lookup for tournament bracket integration
6. Auto-link tournament games to Steam matches based on player/captain overlap and date

## Non-Goals (Future Plans)

- Tournament bracket designer frontend
- Scheduled/automated sync (cron job)

---

## Data Models

### New: `LeagueSyncState`

Tracks sync progress per league with Redis caching.

```python
class LeagueSyncState(models.Model):
    league_id = models.IntegerField(unique=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_match_id = models.BigIntegerField(null=True, blank=True)
    failed_match_ids = models.JSONField(default=list)
    is_syncing = models.BooleanField(default=False)  # Prevent concurrent syncs
```

### Updated: `PlayerMatchStats`

Add optional FK to link players to users.

```python
class PlayerMatchStats(models.Model):
    # ... existing fields ...
    steam_id = models.BigIntegerField()
    user = models.ForeignKey(
        'app.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='match_stats'
    )
```

### Updated: `Match`

Add league reference for filtering.

```python
class Match(models.Model):
    # ... existing fields ...
    league_id = models.IntegerField(null=True, blank=True, db_index=True)
```

### New: `GameMatchSuggestion`

Links tournament games to potential Steam matches with confidence scoring.

```python
class GameMatchSuggestion(models.Model):
    game = models.ForeignKey(
        'app.Game',
        on_delete=models.CASCADE,
        related_name='match_suggestions'
    )
    match = models.ForeignKey(
        Match,
        on_delete=models.CASCADE,
        related_name='game_suggestions'
    )
    tournament = models.ForeignKey(
        'app.Tournament',
        on_delete=models.CASCADE,
        related_name='match_suggestions'
    )
    confidence_score = models.FloatField()  # 0.0 to 1.0
    player_overlap = models.IntegerField()  # Number of matched players
    auto_linked = models.BooleanField(default=False)  # True if auto-linked
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('game', 'match')
```

---

## Steam API Extensions

### `SteamAPI` class additions

Located in `steam/utils/steam_api_caller.py`:

```python
def get_match_history(self, league_id, start_at_match_id=None, matches_requested=100):
    """
    Fetch match history for a league. Returns up to 500 matches per call.
    Use start_at_match_id for pagination (fetches matches BEFORE this ID).
    """
    params = {"league_id": league_id, "matches_requested": matches_requested}
    if start_at_match_id:
        params["start_at_match_id"] = start_at_match_id
    return self._request("IDOTA2Match_570", "GetMatchHistory", 1, params)

def get_live_league_games(self, league_id=None):
    """
    Fetch currently live games. Optionally filter by league.
    """
    params = {}
    if league_id:
        params["league_id"] = league_id
    return self._request("IDOTA2Match_570", "GetLiveLeagueGames", 1, params)
```

### Retry Utility

New file `steam/utils/retry.py`:

```python
def retry_with_backoff(func, max_retries=3, base_delay=1.0):
    """
    Retry a function with exponential backoff.
    Returns (success: bool, result_or_error)
    """
```

---

## Sync Services

Located in `steam/functions/league_sync.py`:

### `sync_league_matches(league_id, full_sync=False)`

Main sync entry point. Fetches matches from Steam API and stores them.

- `full_sync=True`: Fetch ALL matches from beginning
- `full_sync=False`: Fetch only matches after last_match_id

Returns: `{synced_count, failed_count, new_last_match_id}`

### `process_match(match_id, league_id)`

Fetch single match details, store in DB, link users. Uses `retry_with_backoff`. Returns `Match` or `None` on failure.

### `link_user_to_stats(player_stats)`

Attempt to link `PlayerMatchStats` to `CustomUser` via steamid. Called during match processing.

### `relink_all_users()`

Re-scan all `PlayerMatchStats` and attempt to link unlinked records to users. For users who added steamid after matches were synced.

### `retry_failed_matches(league_id)`

Attempt to re-process matches in `failed_match_ids`. Clears successful ones from the list.

---

## Player Matching Utilities

Located in `steam/functions/match_utils.py`:

### `find_matches_by_players(steam_ids, require_all=True, league_id=None)`

Find historical matches where given players participated.

- `steam_ids`: list of Steam IDs to search for
- `require_all=True`: All players must be in match
- `require_all=False`: Any of the players in match
- `league_id`: Optional filter to specific league

Returns: QuerySet of Match objects with player stats prefetched

### `find_live_game_by_players(steam_ids, league_id=None)`

Check if any of the given players are in a live game. Calls Steam API `GetLiveLeagueGames` and filters by player list.

Returns: Live game data dict or `None`

### `find_matches_by_team(team_id)`

Find all matches where members of a Team played together. Looks up team members' steamids and calls `find_matches_by_players`.

Returns: QuerySet of Match objects

### `suggest_match_for_game(game_id)`

Given a tournament Game, find Steam matches that could correspond to it. Uses teams' player steamids to find candidate matches.

Returns: List of Match objects ranked by likelihood (player overlap %)

---

## Game-Match Auto-Linking

Located in `steam/functions/game_linking.py`:

### Auto-Link Strategy

- **High confidence only**: Auto-link when all 10 players match AND match date falls within tournament date range
- **Partial matches**: Store as `GameMatchSuggestion` for manual review
- **Triggers**: Runs during sync (for new matches) AND via manual endpoint

### `auto_link_matches_for_tournament(tournament_id)`

Scan all games in tournament, find matching Steam matches. Auto-link exact matches (10/10 players + correct date), store suggestions for partial matches.

Returns: `{auto_linked_count, suggestions_created_count}`

### `check_match_for_games(match)`

Called during sync. Check if new match corresponds to any unlinked tournament games. Auto-link or create suggestion based on confidence.

### `get_suggestions_for_tournament(tournament_id)`

Retrieve all `GameMatchSuggestion` records for a tournament, ordered by confidence score descending.

Returns: QuerySet of GameMatchSuggestion with game and match prefetched

### `get_suggestions_for_game(game_id)`

Get all match suggestions for a specific tournament game, ordered by confidence score descending. Includes match details for frontend display.

Returns: QuerySet of GameMatchSuggestion with match and player stats prefetched

### `confirm_suggestion(suggestion_id)`

Staff confirms a suggestion - sets `Game.gameid` to the match ID and marks suggestion as `auto_linked=True`.

### `dismiss_suggestion(suggestion_id)`

Staff dismisses a suggestion - deletes the `GameMatchSuggestion` record.

---

## REST API Endpoints

### Request Serializers

Located in `steam/serializers.py`:

```python
class SyncLeagueRequestSerializer(serializers.Serializer):
    league_id = serializers.IntegerField(required=False, default=LEAGUE_ID)
    full_sync = serializers.BooleanField(required=False, default=False)

class FindMatchesByPlayersSerializer(serializers.Serializer):
    steam_ids = serializers.ListField(child=serializers.IntegerField())
    require_all = serializers.BooleanField(required=False, default=True)
    league_id = serializers.IntegerField(required=False)

class RelinkUsersSerializer(serializers.Serializer):
    match_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False  # If empty, relink all
    )

class AutoLinkRequestSerializer(serializers.Serializer):
    tournament_id = serializers.IntegerField(required=True)
```

### Endpoint Functions

Located in `steam/functions/api.py`:

| Endpoint | Method | Permission | Description |
|----------|--------|------------|-------------|
| `/api/steam/sync/` | POST | IsStaff | Trigger league sync (full or incremental) |
| `/api/steam/retry-failed/` | POST | IsStaff | Retry failed match fetches |
| `/api/steam/relink-users/` | POST | IsStaff | Re-link users to match stats |
| `/api/steam/find-by-players/` | POST | AllowAny | Find matches by player steam IDs |
| `/api/steam/live/` | GET | AllowAny | Get live league games |
| `/api/steam/sync-status/` | GET | AllowAny | Get current sync state |
| `/api/steam/auto-link/` | POST | IsStaff | Trigger auto-linking for a tournament |
| `/api/steam/suggestions/tournament/<id>/` | GET | AllowAny | Get match suggestions for tournament |
| `/api/steam/suggestions/game/<id>/` | GET | AllowAny | Get match suggestions for a specific game |
| `/api/steam/suggestions/<id>/confirm/` | POST | IsStaff | Confirm a suggestion (link game to match) |
| `/api/steam/suggestions/<id>/dismiss/` | POST | IsStaff | Dismiss a suggestion |

---

## URL Routing

Updated `steam/urls.py`:

```python
from django.urls import path
from . import views
from .functions import api as steam_api

urlpatterns = [
    # Existing
    path("match/<int:match_id>/", views.MatchDetailView.as_view(), name="match_detail"),

    # Sync operations (Staff only)
    path("sync/", steam_api.sync_league, name="steam_sync"),
    path("retry-failed/", steam_api.retry_failed, name="steam_retry_failed"),
    path("relink-users/", steam_api.relink_users, name="steam_relink_users"),

    # Query endpoints (Public)
    path("find-by-players/", steam_api.find_matches_by_players, name="steam_find_by_players"),
    path("live/", steam_api.get_live_games, name="steam_live_games"),
    path("sync-status/", steam_api.get_sync_status, name="steam_sync_status"),

    # Game-Match Auto-Linking
    path("auto-link/", steam_api.auto_link_tournament, name="steam_auto_link"),
    path("suggestions/tournament/<int:tournament_id>/", steam_api.get_tournament_suggestions, name="steam_tournament_suggestions"),
    path("suggestions/game/<int:game_id>/", steam_api.get_game_suggestions, name="steam_game_suggestions"),
    path("suggestions/<int:suggestion_id>/confirm/", steam_api.confirm_suggestion, name="steam_confirm_suggestion"),
    path("suggestions/<int:suggestion_id>/dismiss/", steam_api.dismiss_suggestion, name="steam_dismiss_suggestion"),
]
```

---

## File Structure

```
backend/steam/
├── models.py              # Add LeagueSyncState, GameMatchSuggestion, update Match & PlayerMatchStats
├── serializers.py         # Add request/response serializers
├── views.py               # Existing MatchDetailView
├── urls.py                # Updated with new routes
├── constants.py           # LEAGUE_ID = 17929 (existing)
├── functions/
│   ├── match.py           # Existing update_match_details
│   ├── league_sync.py     # NEW: sync_league_matches, process_match, etc.
│   ├── match_utils.py     # UPDATE: player matching utilities
│   ├── game_linking.py    # NEW: auto-linking, suggestions, confirm/dismiss
│   └── api.py             # NEW: API endpoint functions
└── utils/
    ├── steam_api_caller.py    # UPDATE: add get_match_history, get_live_league_games
    └── retry.py               # NEW: retry_with_backoff utility
```

---

## Error Handling Strategy

1. **Simple retry**: Failed API requests retry up to 3 times with exponential backoff
2. **Track failures**: Failed match IDs stored in `LeagueSyncState.failed_match_ids`
3. **Continue processing**: Sync continues even if individual matches fail
4. **Retry endpoint**: Dedicated endpoint to retry failed matches later

---

## Caching Strategy

- `LeagueSyncState` cached with `@cached_as` decorator
- Cache invalidated after sync completion
- Follows existing cacheops patterns in the codebase

---

## User Linking Behavior

1. **Auto-link during processing**: When match is processed, attempt to link each player's `steam_id` to `CustomUser.steamid`
2. **Re-link endpoint**: For users who add their steamid after matches are synced, call `/api/steam/relink-users/` to populate missing links
