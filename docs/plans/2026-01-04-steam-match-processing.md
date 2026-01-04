# Steam Match Processing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Process Dota 2 league matches from Steam API, store in database with user linking, and auto-link tournament games to Steam matches.

**Architecture:** Extend existing `steam/` module with new models (`LeagueSyncState`, `GameMatchSuggestion`), Steam API methods for match history/live games, sync services with retry logic, and REST endpoints following existing patterns (`@api_view` + serializers).

**Tech Stack:** Django, Django REST Framework, cacheops (Redis), Steam Web API

---

## Task 1: Add LeagueSyncState Model

**Files:**
- Modify: `backend/steam/models.py`
- Create: `backend/steam/tests/test_models.py`

**Step 1: Write the failing test**

Create test file:

```python
# backend/steam/tests/__init__.py
```

```python
# backend/steam/tests/test_models.py
from django.test import TestCase
from django.utils import timezone
from steam.models import LeagueSyncState


class LeagueSyncStateModelTest(TestCase):
    def test_create_sync_state(self):
        state = LeagueSyncState.objects.create(
            league_id=17929,
            last_match_id=123456789,
            is_syncing=False,
        )
        self.assertEqual(state.league_id, 17929)
        self.assertEqual(state.last_match_id, 123456789)
        self.assertEqual(state.failed_match_ids, [])
        self.assertFalse(state.is_syncing)

    def test_unique_league_id(self):
        LeagueSyncState.objects.create(league_id=17929)
        with self.assertRaises(Exception):
            LeagueSyncState.objects.create(league_id=17929)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_models -v 2`

Expected: FAIL with "cannot import name 'LeagueSyncState'"

**Step 3: Write minimal implementation**

Add to `backend/steam/models.py`:

```python
class LeagueSyncState(models.Model):
    league_id = models.IntegerField(unique=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_match_id = models.BigIntegerField(null=True, blank=True)
    failed_match_ids = models.JSONField(default=list)
    is_syncing = models.BooleanField(default=False)

    def __str__(self):
        return f"League {self.league_id} sync state"
```

**Step 4: Create and run migration**

Run:
```bash
cd backend && python manage.py makemigrations steam
cd backend && python manage.py migrate
```

**Step 5: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_models -v 2`

Expected: PASS (2 tests)

**Step 6: Commit**

```bash
git add backend/steam/models.py backend/steam/tests/ backend/steam/migrations/
git commit -m "feat(steam): add LeagueSyncState model for sync tracking"
```

---

## Task 2: Update PlayerMatchStats with User FK

**Files:**
- Modify: `backend/steam/models.py`
- Modify: `backend/steam/tests/test_models.py`

**Step 1: Write the failing test**

Add to `backend/steam/tests/test_models.py`:

```python
from app.models import CustomUser
from steam.models import Match, PlayerMatchStats


class PlayerMatchStatsUserLinkTest(TestCase):
    def setUp(self):
        self.match = Match.objects.create(
            match_id=7000000001,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
        )

    def test_player_stats_without_user(self):
        stats = PlayerMatchStats.objects.create(
            match=self.match,
            steam_id=76561198000000001,
            player_slot=0,
            hero_id=1,
            kills=10,
            deaths=2,
            assists=15,
            gold_per_min=600,
            xp_per_min=700,
            last_hits=200,
            denies=10,
            hero_damage=25000,
            tower_damage=5000,
            hero_healing=0,
        )
        self.assertIsNone(stats.user)

    def test_player_stats_with_user(self):
        user = CustomUser.objects.create_user(
            username="testplayer",
            password="testpass123",
            steamid=76561198000000001,
        )
        stats = PlayerMatchStats.objects.create(
            match=self.match,
            steam_id=76561198000000001,
            player_slot=0,
            hero_id=1,
            kills=10,
            deaths=2,
            assists=15,
            gold_per_min=600,
            xp_per_min=700,
            last_hits=200,
            denies=10,
            hero_damage=25000,
            tower_damage=5000,
            hero_healing=0,
            user=user,
        )
        self.assertEqual(stats.user, user)
        self.assertEqual(stats.user.steamid, stats.steam_id)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_models.PlayerMatchStatsUserLinkTest -v 2`

Expected: FAIL with "unexpected keyword argument 'user'"

**Step 3: Write minimal implementation**

Update `PlayerMatchStats` in `backend/steam/models.py`:

```python
class PlayerMatchStats(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="players")
    steam_id = models.BigIntegerField()
    user = models.ForeignKey(
        'app.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='match_stats'
    )
    player_slot = models.IntegerField()
    hero_id = models.IntegerField()
    kills = models.IntegerField()
    deaths = models.IntegerField()
    assists = models.IntegerField()
    gold_per_min = models.IntegerField()
    xp_per_min = models.IntegerField()
    last_hits = models.IntegerField()
    denies = models.IntegerField()
    hero_damage = models.IntegerField()
    tower_damage = models.IntegerField()
    hero_healing = models.IntegerField()

    class Meta:
        unique_together = ("match", "steam_id")

    def __str__(self):
        return f"Match {self.match.match_id} - Player {self.steam_id}"
```

**Step 4: Create and run migration**

Run:
```bash
cd backend && python manage.py makemigrations steam
cd backend && python manage.py migrate
```

**Step 5: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_models.PlayerMatchStatsUserLinkTest -v 2`

Expected: PASS (2 tests)

**Step 6: Commit**

```bash
git add backend/steam/models.py backend/steam/migrations/
git commit -m "feat(steam): add user FK to PlayerMatchStats for linking"
```

---

## Task 3: Add league_id to Match Model

**Files:**
- Modify: `backend/steam/models.py`
- Modify: `backend/steam/tests/test_models.py`

**Step 1: Write the failing test**

Add to `backend/steam/tests/test_models.py`:

```python
class MatchLeagueIdTest(TestCase):
    def test_match_with_league_id(self):
        match = Match.objects.create(
            match_id=7000000002,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        self.assertEqual(match.league_id, 17929)

    def test_match_without_league_id(self):
        match = Match.objects.create(
            match_id=7000000003,
            radiant_win=False,
            duration=1800,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
        )
        self.assertIsNone(match.league_id)

    def test_filter_by_league(self):
        Match.objects.create(
            match_id=7000000004, radiant_win=True, duration=2400,
            start_time=1704067200, game_mode=22, lobby_type=1, league_id=17929
        )
        Match.objects.create(
            match_id=7000000005, radiant_win=True, duration=2400,
            start_time=1704067200, game_mode=22, lobby_type=1, league_id=12345
        )
        Match.objects.create(
            match_id=7000000006, radiant_win=True, duration=2400,
            start_time=1704067200, game_mode=22, lobby_type=1
        )
        league_matches = Match.objects.filter(league_id=17929)
        self.assertEqual(league_matches.count(), 1)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_models.MatchLeagueIdTest -v 2`

Expected: FAIL with "unexpected keyword argument 'league_id'"

**Step 3: Write minimal implementation**

Update `Match` in `backend/steam/models.py`:

```python
class Match(models.Model):
    match_id = models.BigIntegerField(primary_key=True)
    radiant_win = models.BooleanField()
    duration = models.IntegerField()
    start_time = models.IntegerField()
    game_mode = models.IntegerField()
    lobby_type = models.IntegerField()
    league_id = models.IntegerField(null=True, blank=True, db_index=True)

    def __str__(self):
        return str(self.match_id)
```

**Step 4: Create and run migration**

Run:
```bash
cd backend && python manage.py makemigrations steam
cd backend && python manage.py migrate
```

**Step 5: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_models.MatchLeagueIdTest -v 2`

Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add backend/steam/models.py backend/steam/migrations/
git commit -m "feat(steam): add league_id field to Match model"
```

---

## Task 4: Add GameMatchSuggestion Model

**Files:**
- Modify: `backend/steam/models.py`
- Modify: `backend/steam/tests/test_models.py`

**Step 1: Write the failing test**

Add to `backend/steam/tests/test_models.py`:

```python
from app.models import Game, Team, Tournament
from steam.models import GameMatchSuggestion


class GameMatchSuggestionModelTest(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played="2026-01-04",
        )
        self.team1 = Team.objects.create(name="Team A", tournament=self.tournament)
        self.team2 = Team.objects.create(name="Team B", tournament=self.tournament)
        self.game = Game.objects.create(
            tournament=self.tournament,
            round=1,
            radiant_team=self.team1,
            dire_team=self.team2,
        )
        self.match = Match.objects.create(
            match_id=7000000010,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )

    def test_create_suggestion(self):
        suggestion = GameMatchSuggestion.objects.create(
            game=self.game,
            match=self.match,
            tournament=self.tournament,
            confidence_score=0.85,
            player_overlap=8,
        )
        self.assertEqual(suggestion.confidence_score, 0.85)
        self.assertEqual(suggestion.player_overlap, 8)
        self.assertFalse(suggestion.auto_linked)

    def test_unique_game_match_pair(self):
        GameMatchSuggestion.objects.create(
            game=self.game,
            match=self.match,
            tournament=self.tournament,
            confidence_score=0.85,
            player_overlap=8,
        )
        with self.assertRaises(Exception):
            GameMatchSuggestion.objects.create(
                game=self.game,
                match=self.match,
                tournament=self.tournament,
                confidence_score=0.90,
                player_overlap=9,
            )

    def test_suggestions_by_tournament(self):
        GameMatchSuggestion.objects.create(
            game=self.game,
            match=self.match,
            tournament=self.tournament,
            confidence_score=0.85,
            player_overlap=8,
        )
        suggestions = GameMatchSuggestion.objects.filter(tournament=self.tournament)
        self.assertEqual(suggestions.count(), 1)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_models.GameMatchSuggestionModelTest -v 2`

Expected: FAIL with "cannot import name 'GameMatchSuggestion'"

**Step 3: Write minimal implementation**

Add to `backend/steam/models.py`:

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
    confidence_score = models.FloatField()
    player_overlap = models.IntegerField()
    auto_linked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('game', 'match')

    def __str__(self):
        return f"Game {self.game_id} -> Match {self.match_id} ({self.confidence_score:.0%})"
```

**Step 4: Create and run migration**

Run:
```bash
cd backend && python manage.py makemigrations steam
cd backend && python manage.py migrate
```

**Step 5: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_models.GameMatchSuggestionModelTest -v 2`

Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add backend/steam/models.py backend/steam/migrations/
git commit -m "feat(steam): add GameMatchSuggestion model for match linking"
```

---

## Task 5: Add Steam API Methods

**Files:**
- Modify: `backend/steam/utils/steam_api_caller.py`
- Create: `backend/steam/tests/test_steam_api.py`

**Step 1: Write the failing test**

```python
# backend/steam/tests/test_steam_api.py
from unittest.mock import patch, MagicMock
from django.test import TestCase
from steam.utils.steam_api_caller import SteamAPI


class SteamAPIMethodsTest(TestCase):
    def setUp(self):
        self.api = SteamAPI(api_key="test_key")

    @patch('steam.utils.steam_api_caller.requests.get')
    def test_get_match_history(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "status": 1,
                "matches": [{"match_id": 123}]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.api.get_match_history(league_id=17929)

        self.assertIn("result", result)
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertIn("league_id", call_args.kwargs.get("params", {}))

    @patch('steam.utils.steam_api_caller.requests.get')
    def test_get_match_history_with_pagination(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"matches": []}}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        self.api.get_match_history(league_id=17929, start_at_match_id=123456)

        call_args = mock_get.call_args
        params = call_args.kwargs.get("params", {})
        self.assertEqual(params.get("start_at_match_id"), 123456)

    @patch('steam.utils.steam_api_caller.requests.get')
    def test_get_live_league_games(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "games": [{"match_id": 789}]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = self.api.get_live_league_games(league_id=17929)

        self.assertIn("result", result)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_steam_api -v 2`

Expected: FAIL with "has no attribute 'get_match_history'"

**Step 3: Write minimal implementation**

Update `backend/steam/utils/steam_api_caller.py`:

```python
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
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error calling Steam API: {e}")
            return None

    def get_match_details(self, match_id):
        """Get detailed information about a single match."""
        return self._request(
            "IDOTA2Match_570", "GetMatchDetails", 1, {"match_id": match_id}
        )

    def get_match_history(self, league_id, start_at_match_id=None, matches_requested=100):
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_steam_api -v 2`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/steam/utils/steam_api_caller.py backend/steam/tests/test_steam_api.py
git commit -m "feat(steam): add get_match_history and get_live_league_games API methods"
```

---

## Task 6: Create Retry Utility

**Files:**
- Create: `backend/steam/utils/retry.py`
- Create: `backend/steam/tests/test_retry.py`

**Step 1: Write the failing test**

```python
# backend/steam/tests/test_retry.py
from unittest.mock import MagicMock
from django.test import TestCase
from steam.utils.retry import retry_with_backoff


class RetryUtilityTest(TestCase):
    def test_success_on_first_try(self):
        func = MagicMock(return_value="success")
        success, result = retry_with_backoff(func, max_retries=3, base_delay=0.01)
        self.assertTrue(success)
        self.assertEqual(result, "success")
        self.assertEqual(func.call_count, 1)

    def test_success_after_retry(self):
        func = MagicMock(side_effect=[Exception("fail"), Exception("fail"), "success"])
        success, result = retry_with_backoff(func, max_retries=3, base_delay=0.01)
        self.assertTrue(success)
        self.assertEqual(result, "success")
        self.assertEqual(func.call_count, 3)

    def test_failure_after_max_retries(self):
        func = MagicMock(side_effect=Exception("always fails"))
        success, result = retry_with_backoff(func, max_retries=3, base_delay=0.01)
        self.assertFalse(success)
        self.assertIsInstance(result, Exception)
        self.assertEqual(func.call_count, 3)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_retry -v 2`

Expected: FAIL with "No module named 'steam.utils.retry'"

**Step 3: Write minimal implementation**

```python
# backend/steam/utils/retry.py
import time
import logging

log = logging.getLogger(__name__)


def retry_with_backoff(func, max_retries=3, base_delay=1.0):
    """
    Retry a function with exponential backoff.

    Args:
        func: Callable to execute
        max_retries: Maximum number of attempts
        base_delay: Initial delay in seconds (doubles each retry)

    Returns:
        tuple: (success: bool, result_or_error)
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            result = func()
            return (True, result)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                log.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)

    return (False, last_exception)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_retry -v 2`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/steam/utils/retry.py backend/steam/tests/test_retry.py
git commit -m "feat(steam): add retry_with_backoff utility"
```

---

## Task 7: Create User Linking Function

**Files:**
- Create: `backend/steam/functions/league_sync.py`
- Create: `backend/steam/tests/test_league_sync.py`

**Step 1: Write the failing test**

```python
# backend/steam/tests/test_league_sync.py
from django.test import TestCase
from app.models import CustomUser
from steam.models import Match, PlayerMatchStats
from steam.functions.league_sync import link_user_to_stats, relink_all_users


class UserLinkingTest(TestCase):
    def setUp(self):
        self.match = Match.objects.create(
            match_id=7000000020,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
        )
        self.user = CustomUser.objects.create_user(
            username="linkedplayer",
            password="testpass123",
            steamid=76561198000000001,
        )

    def test_link_user_to_stats_success(self):
        stats = PlayerMatchStats.objects.create(
            match=self.match,
            steam_id=76561198000000001,
            player_slot=0,
            hero_id=1,
            kills=10, deaths=2, assists=15,
            gold_per_min=600, xp_per_min=700,
            last_hits=200, denies=10,
            hero_damage=25000, tower_damage=5000, hero_healing=0,
        )
        linked = link_user_to_stats(stats)
        self.assertTrue(linked)
        stats.refresh_from_db()
        self.assertEqual(stats.user, self.user)

    def test_link_user_to_stats_no_match(self):
        stats = PlayerMatchStats.objects.create(
            match=self.match,
            steam_id=76561198999999999,  # No matching user
            player_slot=0,
            hero_id=1,
            kills=10, deaths=2, assists=15,
            gold_per_min=600, xp_per_min=700,
            last_hits=200, denies=10,
            hero_damage=25000, tower_damage=5000, hero_healing=0,
        )
        linked = link_user_to_stats(stats)
        self.assertFalse(linked)
        stats.refresh_from_db()
        self.assertIsNone(stats.user)

    def test_relink_all_users(self):
        # Create stats without user link
        stats1 = PlayerMatchStats.objects.create(
            match=self.match, steam_id=76561198000000001, player_slot=0,
            hero_id=1, kills=10, deaths=2, assists=15, gold_per_min=600,
            xp_per_min=700, last_hits=200, denies=10, hero_damage=25000,
            tower_damage=5000, hero_healing=0,
        )
        stats2 = PlayerMatchStats.objects.create(
            match=self.match, steam_id=76561198999999999, player_slot=1,
            hero_id=2, kills=5, deaths=5, assists=10, gold_per_min=400,
            xp_per_min=500, last_hits=100, denies=5, hero_damage=15000,
            tower_damage=2000, hero_healing=0,
        )

        linked_count = relink_all_users()

        self.assertEqual(linked_count, 1)
        stats1.refresh_from_db()
        stats2.refresh_from_db()
        self.assertEqual(stats1.user, self.user)
        self.assertIsNone(stats2.user)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_league_sync.UserLinkingTest -v 2`

Expected: FAIL with "No module named 'steam.functions.league_sync'"

**Step 3: Write minimal implementation**

```python
# backend/steam/functions/league_sync.py
import logging
from app.models import CustomUser
from steam.models import PlayerMatchStats

log = logging.getLogger(__name__)


def link_user_to_stats(player_stats):
    """
    Attempt to link a PlayerMatchStats record to a CustomUser via steamid.

    Args:
        player_stats: PlayerMatchStats instance

    Returns:
        bool: True if linked successfully, False otherwise
    """
    if player_stats.user:
        return True  # Already linked

    try:
        user = CustomUser.objects.get(steamid=player_stats.steam_id)
        player_stats.user = user
        player_stats.save(update_fields=['user'])
        log.debug(f"Linked player {player_stats.steam_id} to user {user.username}")
        return True
    except CustomUser.DoesNotExist:
        return False


def relink_all_users():
    """
    Re-scan all PlayerMatchStats and attempt to link unlinked records to users.

    Returns:
        int: Number of successfully linked records
    """
    unlinked_stats = PlayerMatchStats.objects.filter(user__isnull=True)
    linked_count = 0

    for stats in unlinked_stats:
        if link_user_to_stats(stats):
            linked_count += 1

    log.info(f"Relinked {linked_count} player stats to users")
    return linked_count
```

**Step 4: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_league_sync.UserLinkingTest -v 2`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/steam/functions/league_sync.py backend/steam/tests/test_league_sync.py
git commit -m "feat(steam): add user linking functions"
```

---

## Task 8: Create Match Processing Function

**Files:**
- Modify: `backend/steam/functions/league_sync.py`
- Modify: `backend/steam/tests/test_league_sync.py`

**Step 1: Write the failing test**

Add to `backend/steam/tests/test_league_sync.py`:

```python
from unittest.mock import patch, MagicMock
from steam.functions.league_sync import process_match


class ProcessMatchTest(TestCase):
    @patch('steam.functions.league_sync.SteamAPI')
    def test_process_match_success(self, mock_api_class):
        mock_api = MagicMock()
        mock_api.get_match_details.return_value = {
            "result": {
                "match_id": 7000000030,
                "radiant_win": True,
                "duration": 2400,
                "start_time": 1704067200,
                "game_mode": 22,
                "lobby_type": 1,
                "players": [
                    {
                        "account_id": 40000001,
                        "player_slot": 0,
                        "hero_id": 1,
                        "kills": 10, "deaths": 2, "assists": 15,
                        "gold_per_min": 600, "xp_per_min": 700,
                        "last_hits": 200, "denies": 10,
                        "hero_damage": 25000, "tower_damage": 5000, "hero_healing": 0,
                    }
                ]
            }
        }
        mock_api_class.return_value = mock_api

        match = process_match(7000000030, league_id=17929)

        self.assertIsNotNone(match)
        self.assertEqual(match.match_id, 7000000030)
        self.assertEqual(match.league_id, 17929)
        self.assertEqual(match.players.count(), 1)

    @patch('steam.functions.league_sync.SteamAPI')
    def test_process_match_failure(self, mock_api_class):
        mock_api = MagicMock()
        mock_api.get_match_details.return_value = None
        mock_api_class.return_value = mock_api

        match = process_match(7000000031, league_id=17929)

        self.assertIsNone(match)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_league_sync.ProcessMatchTest -v 2`

Expected: FAIL with "cannot import name 'process_match'"

**Step 3: Write minimal implementation**

Add to `backend/steam/functions/league_sync.py`:

```python
from steam.models import Match, PlayerMatchStats, LeagueSyncState
from steam.utils.steam_api_caller import SteamAPI
from steam.utils.retry import retry_with_backoff


def process_match(match_id, league_id=None):
    """
    Fetch single match details from Steam API, store in DB, link users.

    Args:
        match_id: Steam match ID
        league_id: Optional league ID to associate with match

    Returns:
        Match instance or None on failure
    """
    api = SteamAPI()

    def fetch():
        return api.get_match_details(match_id)

    success, result = retry_with_backoff(fetch, max_retries=3, base_delay=1.0)

    if not success or not result or "result" not in result:
        log.warning(f"Failed to fetch match {match_id}")
        return None

    data = result["result"]

    match, _ = Match.objects.update_or_create(
        match_id=data["match_id"],
        defaults={
            "radiant_win": data.get("radiant_win", False),
            "duration": data.get("duration", 0),
            "start_time": data.get("start_time", 0),
            "game_mode": data.get("game_mode", 0),
            "lobby_type": data.get("lobby_type", 0),
            "league_id": league_id,
        },
    )

    for player_data in data.get("players", []):
        account_id = player_data.get("account_id")
        if account_id is None:
            continue

        # Convert 32-bit account_id to 64-bit steam_id
        steam_id_64 = account_id + 76561197960265728

        stats, _ = PlayerMatchStats.objects.update_or_create(
            match=match,
            steam_id=steam_id_64,
            defaults={
                "player_slot": player_data.get("player_slot", 0),
                "hero_id": player_data.get("hero_id", 0),
                "kills": player_data.get("kills", 0),
                "deaths": player_data.get("deaths", 0),
                "assists": player_data.get("assists", 0),
                "gold_per_min": player_data.get("gold_per_min", 0),
                "xp_per_min": player_data.get("xp_per_min", 0),
                "last_hits": player_data.get("last_hits", 0),
                "denies": player_data.get("denies", 0),
                "hero_damage": player_data.get("hero_damage", 0),
                "tower_damage": player_data.get("tower_damage", 0),
                "hero_healing": player_data.get("hero_healing", 0),
            },
        )
        link_user_to_stats(stats)

    return match
```

**Step 4: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_league_sync.ProcessMatchTest -v 2`

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/steam/functions/league_sync.py backend/steam/tests/test_league_sync.py
git commit -m "feat(steam): add process_match function with retry and user linking"
```

---

## Task 9: Create League Sync Function

**Files:**
- Modify: `backend/steam/functions/league_sync.py`
- Modify: `backend/steam/tests/test_league_sync.py`

**Step 1: Write the failing test**

Add to `backend/steam/tests/test_league_sync.py`:

```python
from steam.models import LeagueSyncState
from steam.functions.league_sync import sync_league_matches


class SyncLeagueMatchesTest(TestCase):
    @patch('steam.functions.league_sync.SteamAPI')
    @patch('steam.functions.league_sync.process_match')
    def test_incremental_sync(self, mock_process, mock_api_class):
        # Setup existing sync state
        LeagueSyncState.objects.create(
            league_id=17929,
            last_match_id=7000000100,
        )

        mock_api = MagicMock()
        mock_api.get_match_history.return_value = {
            "result": {
                "status": 1,
                "matches": [
                    {"match_id": 7000000101},
                    {"match_id": 7000000102},
                ]
            }
        }
        mock_api_class.return_value = mock_api
        mock_process.return_value = MagicMock(match_id=7000000101)

        result = sync_league_matches(17929, full_sync=False)

        self.assertEqual(result["synced_count"], 2)
        mock_process.assert_called()

    @patch('steam.functions.league_sync.SteamAPI')
    @patch('steam.functions.league_sync.process_match')
    def test_full_sync(self, mock_process, mock_api_class):
        mock_api = MagicMock()
        # Simulate pagination: first call returns matches, second returns empty
        mock_api.get_match_history.side_effect = [
            {"result": {"status": 1, "matches": [{"match_id": 7000000200}]}},
            {"result": {"status": 1, "matches": []}},
        ]
        mock_api_class.return_value = mock_api
        mock_process.return_value = MagicMock(match_id=7000000200)

        result = sync_league_matches(17929, full_sync=True)

        self.assertIn("synced_count", result)

    @patch('steam.functions.league_sync.SteamAPI')
    @patch('steam.functions.league_sync.process_match')
    def test_sync_tracks_failures(self, mock_process, mock_api_class):
        mock_api = MagicMock()
        mock_api.get_match_history.return_value = {
            "result": {
                "status": 1,
                "matches": [{"match_id": 7000000300}, {"match_id": 7000000301}]
            }
        }
        mock_api_class.return_value = mock_api
        # First succeeds, second fails
        mock_process.side_effect = [MagicMock(match_id=7000000300), None]

        result = sync_league_matches(17929, full_sync=True)

        self.assertEqual(result["synced_count"], 1)
        self.assertEqual(result["failed_count"], 1)

        state = LeagueSyncState.objects.get(league_id=17929)
        self.assertIn(7000000301, state.failed_match_ids)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_league_sync.SyncLeagueMatchesTest -v 2`

Expected: FAIL with "cannot import name 'sync_league_matches'"

**Step 3: Write minimal implementation**

Add to `backend/steam/functions/league_sync.py`:

```python
from django.utils import timezone


def sync_league_matches(league_id, full_sync=False):
    """
    Main sync entry point. Fetches matches from Steam API and stores them.

    Args:
        league_id: Dota 2 league ID
        full_sync: If True, fetch ALL matches. If False, only new matches.

    Returns:
        dict: {synced_count, failed_count, new_last_match_id}
    """
    state, _ = LeagueSyncState.objects.get_or_create(
        league_id=league_id,
        defaults={"failed_match_ids": []}
    )

    if state.is_syncing:
        log.warning(f"Sync already in progress for league {league_id}")
        return {"error": "Sync already in progress", "synced_count": 0, "failed_count": 0}

    state.is_syncing = True
    state.save()

    api = SteamAPI()
    synced_count = 0
    failed_count = 0
    failed_ids = list(state.failed_match_ids)
    start_at_match_id = None if full_sync else state.last_match_id
    new_last_match_id = state.last_match_id

    try:
        while True:
            result = api.get_match_history(
                league_id=league_id,
                start_at_match_id=start_at_match_id,
                matches_requested=100
            )

            if not result or "result" not in result:
                log.error(f"Failed to fetch match history for league {league_id}")
                break

            matches = result["result"].get("matches", [])
            if not matches:
                break

            for match_data in matches:
                match_id = match_data["match_id"]

                # Skip if we've already processed this in incremental sync
                if not full_sync and state.last_match_id and match_id <= state.last_match_id:
                    continue

                match = process_match(match_id, league_id=league_id)

                if match:
                    synced_count += 1
                    if new_last_match_id is None or match_id > new_last_match_id:
                        new_last_match_id = match_id
                else:
                    failed_count += 1
                    if match_id not in failed_ids:
                        failed_ids.append(match_id)

            # Pagination: use the last match_id to get older matches
            start_at_match_id = matches[-1]["match_id"]

            # For incremental sync, stop after first batch if we hit known matches
            if not full_sync:
                break

    finally:
        state.is_syncing = False
        state.last_sync_at = timezone.now()
        state.last_match_id = new_last_match_id
        state.failed_match_ids = failed_ids
        state.save()

    log.info(f"Sync complete for league {league_id}: {synced_count} synced, {failed_count} failed")

    return {
        "synced_count": synced_count,
        "failed_count": failed_count,
        "new_last_match_id": new_last_match_id,
    }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_league_sync.SyncLeagueMatchesTest -v 2`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/steam/functions/league_sync.py backend/steam/tests/test_league_sync.py
git commit -m "feat(steam): add sync_league_matches function with incremental/full sync"
```

---

## Task 10: Create Retry Failed Matches Function

**Files:**
- Modify: `backend/steam/functions/league_sync.py`
- Modify: `backend/steam/tests/test_league_sync.py`

**Step 1: Write the failing test**

Add to `backend/steam/tests/test_league_sync.py`:

```python
from steam.functions.league_sync import retry_failed_matches


class RetryFailedMatchesTest(TestCase):
    @patch('steam.functions.league_sync.process_match')
    def test_retry_clears_successful(self, mock_process):
        LeagueSyncState.objects.create(
            league_id=17929,
            failed_match_ids=[7000000400, 7000000401, 7000000402],
        )

        # First two succeed, third fails
        mock_process.side_effect = [
            MagicMock(match_id=7000000400),
            MagicMock(match_id=7000000401),
            None,
        ]

        result = retry_failed_matches(17929)

        self.assertEqual(result["retried_count"], 2)
        self.assertEqual(result["still_failed_count"], 1)

        state = LeagueSyncState.objects.get(league_id=17929)
        self.assertEqual(state.failed_match_ids, [7000000402])
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_league_sync.RetryFailedMatchesTest -v 2`

Expected: FAIL with "cannot import name 'retry_failed_matches'"

**Step 3: Write minimal implementation**

Add to `backend/steam/functions/league_sync.py`:

```python
def retry_failed_matches(league_id):
    """
    Attempt to re-process matches in failed_match_ids.
    Clears successful ones from the list.

    Args:
        league_id: Dota 2 league ID

    Returns:
        dict: {retried_count, still_failed_count}
    """
    try:
        state = LeagueSyncState.objects.get(league_id=league_id)
    except LeagueSyncState.DoesNotExist:
        return {"retried_count": 0, "still_failed_count": 0}

    failed_ids = list(state.failed_match_ids)
    still_failed = []
    retried_count = 0

    for match_id in failed_ids:
        match = process_match(match_id, league_id=league_id)
        if match:
            retried_count += 1
        else:
            still_failed.append(match_id)

    state.failed_match_ids = still_failed
    state.save()

    log.info(f"Retry complete for league {league_id}: {retried_count} succeeded, {len(still_failed)} still failed")

    return {
        "retried_count": retried_count,
        "still_failed_count": len(still_failed),
    }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_league_sync.RetryFailedMatchesTest -v 2`

Expected: PASS (1 test)

**Step 5: Commit**

```bash
git add backend/steam/functions/league_sync.py backend/steam/tests/test_league_sync.py
git commit -m "feat(steam): add retry_failed_matches function"
```

---

## Task 11: Create Player Matching Utilities

**Files:**
- Modify: `backend/steam/functions/match_utils.py`
- Create: `backend/steam/tests/test_match_utils.py`

**Step 1: Write the failing test**

```python
# backend/steam/tests/test_match_utils.py
from django.test import TestCase
from steam.models import Match, PlayerMatchStats
from steam.functions.match_utils import find_matches_by_players


class FindMatchesByPlayersTest(TestCase):
    def setUp(self):
        # Create match with 3 players
        self.match1 = Match.objects.create(
            match_id=7000000500, radiant_win=True, duration=2400,
            start_time=1704067200, game_mode=22, lobby_type=1, league_id=17929
        )
        for i, steam_id in enumerate([76561198000000001, 76561198000000002, 76561198000000003]):
            PlayerMatchStats.objects.create(
                match=self.match1, steam_id=steam_id, player_slot=i,
                hero_id=i+1, kills=10, deaths=2, assists=15, gold_per_min=600,
                xp_per_min=700, last_hits=200, denies=10, hero_damage=25000,
                tower_damage=5000, hero_healing=0,
            )

        # Create another match with different players
        self.match2 = Match.objects.create(
            match_id=7000000501, radiant_win=False, duration=1800,
            start_time=1704070800, game_mode=22, lobby_type=1, league_id=17929
        )
        for i, steam_id in enumerate([76561198000000004, 76561198000000005]):
            PlayerMatchStats.objects.create(
                match=self.match2, steam_id=steam_id, player_slot=i,
                hero_id=i+1, kills=5, deaths=5, assists=10, gold_per_min=400,
                xp_per_min=500, last_hits=100, denies=5, hero_damage=15000,
                tower_damage=2000, hero_healing=0,
            )

    def test_find_matches_require_all(self):
        steam_ids = [76561198000000001, 76561198000000002]
        matches = find_matches_by_players(steam_ids, require_all=True)
        self.assertEqual(matches.count(), 1)
        self.assertEqual(matches.first(), self.match1)

    def test_find_matches_require_any(self):
        steam_ids = [76561198000000001, 76561198000000004]
        matches = find_matches_by_players(steam_ids, require_all=False)
        self.assertEqual(matches.count(), 2)

    def test_find_matches_with_league_filter(self):
        # Create match in different league
        match3 = Match.objects.create(
            match_id=7000000502, radiant_win=True, duration=2400,
            start_time=1704074400, game_mode=22, lobby_type=1, league_id=12345
        )
        PlayerMatchStats.objects.create(
            match=match3, steam_id=76561198000000001, player_slot=0,
            hero_id=1, kills=10, deaths=2, assists=15, gold_per_min=600,
            xp_per_min=700, last_hits=200, denies=10, hero_damage=25000,
            tower_damage=5000, hero_healing=0,
        )

        steam_ids = [76561198000000001]
        matches = find_matches_by_players(steam_ids, league_id=17929)
        self.assertEqual(matches.count(), 1)
        self.assertEqual(matches.first().league_id, 17929)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_match_utils -v 2`

Expected: FAIL with "cannot import name 'find_matches_by_players'"

**Step 3: Write minimal implementation**

Update `backend/steam/functions/match_utils.py`:

```python
# backend/steam/functions/match_utils.py
import logging
from django.db.models import Count, Q
from steam.models import Match, PlayerMatchStats

log = logging.getLogger(__name__)


def find_matches_by_players(steam_ids, require_all=True, league_id=None):
    """
    Find historical matches where given players participated.

    Args:
        steam_ids: List of Steam IDs to search for
        require_all: If True, all players must be in match. If False, any player.
        league_id: Optional filter to specific league

    Returns:
        QuerySet of Match objects
    """
    if not steam_ids:
        return Match.objects.none()

    queryset = Match.objects.all()

    if league_id:
        queryset = queryset.filter(league_id=league_id)

    if require_all:
        # Match must contain ALL specified players
        for steam_id in steam_ids:
            queryset = queryset.filter(players__steam_id=steam_id)
        queryset = queryset.distinct()
    else:
        # Match must contain ANY of the specified players
        queryset = queryset.filter(
            players__steam_id__in=steam_ids
        ).distinct()

    return queryset.prefetch_related('players')
```

**Step 4: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_match_utils -v 2`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/steam/functions/match_utils.py backend/steam/tests/test_match_utils.py
git commit -m "feat(steam): add find_matches_by_players utility"
```

---

## Task 12: Add Team-Based Match Finding

**Files:**
- Modify: `backend/steam/functions/match_utils.py`
- Modify: `backend/steam/tests/test_match_utils.py`

**Step 1: Write the failing test**

Add to `backend/steam/tests/test_match_utils.py`:

```python
from app.models import CustomUser, Team, Tournament
from steam.functions.match_utils import find_matches_by_team


class FindMatchesByTeamTest(TestCase):
    def setUp(self):
        # Create users with steamids
        self.user1 = CustomUser.objects.create_user(
            username="player1", password="pass", steamid=76561198000000010
        )
        self.user2 = CustomUser.objects.create_user(
            username="player2", password="pass", steamid=76561198000000011
        )
        self.user3 = CustomUser.objects.create_user(
            username="player3", password="pass"  # No steamid
        )

        # Create tournament and team
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played="2026-01-04"
        )
        self.team = Team.objects.create(
            name="Test Team", tournament=self.tournament, captain=self.user1
        )
        self.team.members.add(self.user1, self.user2, self.user3)

        # Create match with team members
        self.match = Match.objects.create(
            match_id=7000000600, radiant_win=True, duration=2400,
            start_time=1704067200, game_mode=22, lobby_type=1, league_id=17929
        )
        PlayerMatchStats.objects.create(
            match=self.match, steam_id=76561198000000010, player_slot=0,
            hero_id=1, kills=10, deaths=2, assists=15, gold_per_min=600,
            xp_per_min=700, last_hits=200, denies=10, hero_damage=25000,
            tower_damage=5000, hero_healing=0,
        )
        PlayerMatchStats.objects.create(
            match=self.match, steam_id=76561198000000011, player_slot=1,
            hero_id=2, kills=5, deaths=3, assists=20, gold_per_min=400,
            xp_per_min=500, last_hits=50, denies=5, hero_damage=10000,
            tower_damage=1000, hero_healing=5000,
        )

    def test_find_matches_by_team(self):
        matches = find_matches_by_team(self.team.id)
        self.assertEqual(matches.count(), 1)
        self.assertEqual(matches.first(), self.match)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_match_utils.FindMatchesByTeamTest -v 2`

Expected: FAIL with "cannot import name 'find_matches_by_team'"

**Step 3: Write minimal implementation**

Add to `backend/steam/functions/match_utils.py`:

```python
from app.models import Team


def find_matches_by_team(team_id):
    """
    Find all matches where members of a Team played together.

    Args:
        team_id: Team primary key

    Returns:
        QuerySet of Match objects
    """
    try:
        team = Team.objects.get(pk=team_id)
    except Team.DoesNotExist:
        return Match.objects.none()

    # Get steamids from team members (excluding those without steamid)
    steam_ids = list(
        team.members.exclude(steamid__isnull=True)
        .values_list('steamid', flat=True)
    )

    if not steam_ids:
        return Match.objects.none()

    # Find matches where any team member played
    return find_matches_by_players(steam_ids, require_all=False)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_match_utils.FindMatchesByTeamTest -v 2`

Expected: PASS (1 test)

**Step 5: Commit**

```bash
git add backend/steam/functions/match_utils.py backend/steam/tests/test_match_utils.py
git commit -m "feat(steam): add find_matches_by_team utility"
```

---

## Task 13: Create Game Linking Functions

**Files:**
- Create: `backend/steam/functions/game_linking.py`
- Create: `backend/steam/tests/test_game_linking.py`

**Step 1: Write the failing test**

```python
# backend/steam/tests/test_game_linking.py
from django.test import TestCase
from app.models import CustomUser, Game, Team, Tournament
from steam.models import Match, PlayerMatchStats, GameMatchSuggestion
from steam.functions.game_linking import (
    get_suggestions_for_game,
    get_suggestions_for_tournament,
    confirm_suggestion,
    dismiss_suggestion,
)


class GameLinkingSuggestionsTest(TestCase):
    def setUp(self):
        # Create tournament, teams, and game
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played="2026-01-04"
        )
        self.team1 = Team.objects.create(name="Team A", tournament=self.tournament)
        self.team2 = Team.objects.create(name="Team B", tournament=self.tournament)
        self.game = Game.objects.create(
            tournament=self.tournament, round=1,
            radiant_team=self.team1, dire_team=self.team2
        )

        # Create match
        self.match = Match.objects.create(
            match_id=7000000700, radiant_win=True, duration=2400,
            start_time=1704067200, game_mode=22, lobby_type=1, league_id=17929
        )

        # Create suggestion
        self.suggestion = GameMatchSuggestion.objects.create(
            game=self.game,
            match=self.match,
            tournament=self.tournament,
            confidence_score=0.85,
            player_overlap=8,
        )

    def test_get_suggestions_for_game(self):
        suggestions = get_suggestions_for_game(self.game.id)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0], self.suggestion)

    def test_get_suggestions_for_tournament(self):
        suggestions = get_suggestions_for_tournament(self.tournament.id)
        self.assertEqual(len(suggestions), 1)

    def test_confirm_suggestion(self):
        result = confirm_suggestion(self.suggestion.id)
        self.assertTrue(result)

        self.game.refresh_from_db()
        self.suggestion.refresh_from_db()

        self.assertEqual(self.game.gameid, self.match.match_id)
        self.assertTrue(self.suggestion.auto_linked)

    def test_dismiss_suggestion(self):
        suggestion_id = self.suggestion.id
        result = dismiss_suggestion(suggestion_id)
        self.assertTrue(result)

        self.assertFalse(
            GameMatchSuggestion.objects.filter(pk=suggestion_id).exists()
        )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_game_linking -v 2`

Expected: FAIL with "No module named 'steam.functions.game_linking'"

**Step 3: Write minimal implementation**

```python
# backend/steam/functions/game_linking.py
import logging
from app.models import Game, Tournament
from steam.models import GameMatchSuggestion

log = logging.getLogger(__name__)


def get_suggestions_for_game(game_id):
    """
    Get all match suggestions for a specific tournament game.

    Args:
        game_id: Game primary key

    Returns:
        List of GameMatchSuggestion objects ordered by confidence
    """
    return list(
        GameMatchSuggestion.objects.filter(game_id=game_id)
        .select_related('match', 'game')
        .prefetch_related('match__players')
        .order_by('-confidence_score')
    )


def get_suggestions_for_tournament(tournament_id):
    """
    Get all match suggestions for a tournament.

    Args:
        tournament_id: Tournament primary key

    Returns:
        List of GameMatchSuggestion objects ordered by confidence
    """
    return list(
        GameMatchSuggestion.objects.filter(tournament_id=tournament_id)
        .select_related('match', 'game')
        .order_by('-confidence_score')
    )


def confirm_suggestion(suggestion_id):
    """
    Confirm a suggestion - link the Game to the Match.

    Args:
        suggestion_id: GameMatchSuggestion primary key

    Returns:
        bool: True if successful
    """
    try:
        suggestion = GameMatchSuggestion.objects.get(pk=suggestion_id)
    except GameMatchSuggestion.DoesNotExist:
        return False

    game = suggestion.game
    game.gameid = suggestion.match.match_id
    game.save(update_fields=['gameid'])

    suggestion.auto_linked = True
    suggestion.save(update_fields=['auto_linked'])

    log.info(f"Confirmed suggestion: Game {game.id} linked to Match {suggestion.match.match_id}")
    return True


def dismiss_suggestion(suggestion_id):
    """
    Dismiss a suggestion - delete the record.

    Args:
        suggestion_id: GameMatchSuggestion primary key

    Returns:
        bool: True if successful
    """
    try:
        suggestion = GameMatchSuggestion.objects.get(pk=suggestion_id)
        suggestion.delete()
        log.info(f"Dismissed suggestion {suggestion_id}")
        return True
    except GameMatchSuggestion.DoesNotExist:
        return False
```

**Step 4: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_game_linking -v 2`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/steam/functions/game_linking.py backend/steam/tests/test_game_linking.py
git commit -m "feat(steam): add suggestion query and confirm/dismiss functions"
```

---

## Task 14: Create Auto-Link Function

**Files:**
- Modify: `backend/steam/functions/game_linking.py`
- Modify: `backend/steam/tests/test_game_linking.py`

**Step 1: Write the failing test**

Add to `backend/steam/tests/test_game_linking.py`:

```python
from datetime import date
from steam.functions.game_linking import auto_link_matches_for_tournament


class AutoLinkMatchesTest(TestCase):
    def setUp(self):
        # Create users with steamids (5 per team = 10 total)
        self.radiant_users = []
        self.dire_users = []

        for i in range(5):
            user = CustomUser.objects.create_user(
                username=f"radiant{i}", password="pass",
                steamid=76561198000001000 + i
            )
            self.radiant_users.append(user)

        for i in range(5):
            user = CustomUser.objects.create_user(
                username=f"dire{i}", password="pass",
                steamid=76561198000002000 + i
            )
            self.dire_users.append(user)

        # Create tournament and teams
        self.tournament = Tournament.objects.create(
            name="Auto Link Tournament", date_played="2026-01-04"
        )
        self.team1 = Team.objects.create(
            name="Radiant Team", tournament=self.tournament,
            captain=self.radiant_users[0]
        )
        self.team1.members.set(self.radiant_users)

        self.team2 = Team.objects.create(
            name="Dire Team", tournament=self.tournament,
            captain=self.dire_users[0]
        )
        self.team2.members.set(self.dire_users)

        # Create game
        self.game = Game.objects.create(
            tournament=self.tournament, round=1,
            radiant_team=self.team1, dire_team=self.team2
        )

        # Create match with all 10 players on tournament date
        self.match = Match.objects.create(
            match_id=7000000800, radiant_win=True, duration=2400,
            start_time=1735948800,  # 2026-01-04 00:00:00 UTC
            game_mode=22, lobby_type=1, league_id=17929
        )

        # Add all 10 players to match
        for i, user in enumerate(self.radiant_users):
            PlayerMatchStats.objects.create(
                match=self.match, steam_id=user.steamid, player_slot=i,
                hero_id=i+1, kills=10, deaths=2, assists=15, gold_per_min=600,
                xp_per_min=700, last_hits=200, denies=10, hero_damage=25000,
                tower_damage=5000, hero_healing=0, user=user
            )

        for i, user in enumerate(self.dire_users):
            PlayerMatchStats.objects.create(
                match=self.match, steam_id=user.steamid, player_slot=128+i,
                hero_id=i+6, kills=5, deaths=5, assists=10, gold_per_min=400,
                xp_per_min=500, last_hits=100, denies=5, hero_damage=15000,
                tower_damage=2000, hero_healing=0, user=user
            )

    def test_auto_link_exact_match(self):
        result = auto_link_matches_for_tournament(self.tournament.id)

        self.assertEqual(result["auto_linked_count"], 1)
        self.assertEqual(result["suggestions_created_count"], 0)

        self.game.refresh_from_db()
        self.assertEqual(self.game.gameid, self.match.match_id)

    def test_auto_link_partial_creates_suggestion(self):
        # Remove some players to make it partial
        PlayerMatchStats.objects.filter(
            match=self.match,
            steam_id__in=[u.steamid for u in self.radiant_users[3:]]
        ).delete()

        result = auto_link_matches_for_tournament(self.tournament.id)

        self.assertEqual(result["auto_linked_count"], 0)
        self.assertEqual(result["suggestions_created_count"], 1)

        suggestion = GameMatchSuggestion.objects.get(game=self.game)
        self.assertLess(suggestion.confidence_score, 1.0)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_game_linking.AutoLinkMatchesTest -v 2`

Expected: FAIL with "cannot import name 'auto_link_matches_for_tournament'"

**Step 3: Write minimal implementation**

Add to `backend/steam/functions/game_linking.py`:

```python
from datetime import datetime, timedelta
from steam.models import Match, PlayerMatchStats
from steam.functions.match_utils import find_matches_by_players


def auto_link_matches_for_tournament(tournament_id):
    """
    Scan all games in tournament, find matching Steam matches.
    Auto-link exact matches (10/10 players + correct date).
    Store suggestions for partial matches.

    Args:
        tournament_id: Tournament primary key

    Returns:
        dict: {auto_linked_count, suggestions_created_count}
    """
    try:
        tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        return {"auto_linked_count": 0, "suggestions_created_count": 0}

    auto_linked_count = 0
    suggestions_created_count = 0

    # Get tournament date range (allow same day)
    tournament_date = tournament.date_played
    start_timestamp = int(datetime.combine(tournament_date, datetime.min.time()).timestamp())
    end_timestamp = start_timestamp + 86400  # +24 hours

    games = Game.objects.filter(
        tournament=tournament,
        gameid__isnull=True  # Only unlinked games
    ).select_related('radiant_team', 'dire_team')

    for game in games:
        # Collect steam IDs from both teams
        radiant_steam_ids = list(
            game.radiant_team.members.exclude(steamid__isnull=True)
            .values_list('steamid', flat=True)
        ) if game.radiant_team else []

        dire_steam_ids = list(
            game.dire_team.members.exclude(steamid__isnull=True)
            .values_list('steamid', flat=True)
        ) if game.dire_team else []

        all_steam_ids = radiant_steam_ids + dire_steam_ids
        expected_player_count = len(all_steam_ids)

        if expected_player_count == 0:
            continue

        # Find candidate matches (any player from game)
        candidate_matches = find_matches_by_players(
            all_steam_ids, require_all=False
        ).filter(
            start_time__gte=start_timestamp,
            start_time__lt=end_timestamp
        )

        for match in candidate_matches:
            # Count how many expected players are in this match
            match_steam_ids = set(
                match.players.values_list('steam_id', flat=True)
            )
            overlap = len(set(all_steam_ids) & match_steam_ids)
            confidence = overlap / max(expected_player_count, 10)  # Normalize to 10 players

            # Check if suggestion already exists
            if GameMatchSuggestion.objects.filter(game=game, match=match).exists():
                continue

            if overlap == expected_player_count and expected_player_count >= 10:
                # Exact match - auto-link
                game.gameid = match.match_id
                game.save(update_fields=['gameid'])

                GameMatchSuggestion.objects.create(
                    game=game, match=match, tournament=tournament,
                    confidence_score=1.0, player_overlap=overlap, auto_linked=True
                )
                auto_linked_count += 1
                log.info(f"Auto-linked Game {game.id} to Match {match.match_id}")
                break  # Move to next game
            else:
                # Partial match - create suggestion
                GameMatchSuggestion.objects.create(
                    game=game, match=match, tournament=tournament,
                    confidence_score=confidence, player_overlap=overlap
                )
                suggestions_created_count += 1

    return {
        "auto_linked_count": auto_linked_count,
        "suggestions_created_count": suggestions_created_count,
    }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_game_linking.AutoLinkMatchesTest -v 2`

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/steam/functions/game_linking.py backend/steam/tests/test_game_linking.py
git commit -m "feat(steam): add auto_link_matches_for_tournament function"
```

---

## Task 15: Create API Serializers

**Files:**
- Modify: `backend/steam/serializers.py`
- Create: `backend/steam/tests/test_serializers.py`

**Step 1: Write the failing test**

```python
# backend/steam/tests/test_serializers.py
from django.test import TestCase
from steam.serializers import (
    SyncLeagueRequestSerializer,
    FindMatchesByPlayersSerializer,
    AutoLinkRequestSerializer,
    GameMatchSuggestionSerializer,
)


class SerializersTest(TestCase):
    def test_sync_league_serializer_defaults(self):
        serializer = SyncLeagueRequestSerializer(data={})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["league_id"], 17929)
        self.assertFalse(serializer.validated_data["full_sync"])

    def test_sync_league_serializer_custom(self):
        serializer = SyncLeagueRequestSerializer(
            data={"league_id": 12345, "full_sync": True}
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["league_id"], 12345)
        self.assertTrue(serializer.validated_data["full_sync"])

    def test_find_matches_serializer(self):
        serializer = FindMatchesByPlayersSerializer(
            data={"steam_ids": [123, 456], "require_all": False}
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["steam_ids"], [123, 456])
        self.assertFalse(serializer.validated_data["require_all"])

    def test_auto_link_serializer(self):
        serializer = AutoLinkRequestSerializer(data={"tournament_id": 1})
        self.assertTrue(serializer.is_valid())
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_serializers -v 2`

Expected: FAIL with import errors

**Step 3: Write minimal implementation**

Update `backend/steam/serializers.py`:

```python
from rest_framework import serializers

from steam.constants import LEAGUE_ID
from steam.models import Match, PlayerMatchStats, GameMatchSuggestion


class PlayerMatchStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerMatchStats
        fields = "__all__"


class MatchSerializer(serializers.ModelSerializer):
    players = PlayerMatchStatsSerializer(many=True, read_only=True)

    class Meta:
        model = Match
        fields = "__all__"


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
        required=False
    )


class AutoLinkRequestSerializer(serializers.Serializer):
    tournament_id = serializers.IntegerField(required=True)


class GameMatchSuggestionSerializer(serializers.ModelSerializer):
    match = MatchSerializer(read_only=True)

    class Meta:
        model = GameMatchSuggestion
        fields = [
            'id', 'game', 'match', 'tournament',
            'confidence_score', 'player_overlap', 'auto_linked', 'created_at'
        ]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_serializers -v 2`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/steam/serializers.py backend/steam/tests/test_serializers.py
git commit -m "feat(steam): add API request/response serializers"
```

---

## Task 16: Create API Endpoints

**Files:**
- Create: `backend/steam/functions/api.py`
- Create: `backend/steam/tests/test_api.py`

**Step 1: Write the failing test**

```python
# backend/steam/tests/test_api.py
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from app.models import CustomUser


class SteamAPIEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = CustomUser.objects.create_user(
            username="staffuser", password="pass", is_staff=True
        )
        self.regular_user = CustomUser.objects.create_user(
            username="regularuser", password="pass"
        )

    @patch('steam.functions.api.sync_league_matches')
    def test_sync_league_staff_only(self, mock_sync):
        mock_sync.return_value = {"synced_count": 5, "failed_count": 0}

        # Anonymous - should fail
        response = self.client.post('/api/steam/sync/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Regular user - should fail
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post('/api/steam/sync/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Staff user - should succeed
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post('/api/steam/sync/', {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["synced_count"], 5)

    def test_sync_status_public(self):
        response = self.client.get('/api/steam/sync-status/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('steam.functions.api.find_matches_by_players')
    def test_find_by_players_public(self, mock_find):
        from steam.models import Match
        mock_find.return_value = Match.objects.none()

        response = self.client.post(
            '/api/steam/find-by-players/',
            {"steam_ids": [123, 456]},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_api -v 2`

Expected: FAIL (endpoints don't exist yet)

**Step 3: Write minimal implementation**

```python
# backend/steam/functions/api.py
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from app.permissions import IsStaff
from steam.constants import LEAGUE_ID
from steam.models import LeagueSyncState, Match
from steam.serializers import (
    SyncLeagueRequestSerializer,
    FindMatchesByPlayersSerializer,
    RelinkUsersSerializer,
    AutoLinkRequestSerializer,
    MatchSerializer,
    GameMatchSuggestionSerializer,
)
from steam.functions.league_sync import (
    sync_league_matches,
    retry_failed_matches,
    relink_all_users,
)
from steam.functions.match_utils import find_matches_by_players
from steam.functions.game_linking import (
    auto_link_matches_for_tournament,
    get_suggestions_for_tournament,
    get_suggestions_for_game,
    confirm_suggestion,
    dismiss_suggestion,
)

log = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsStaff])
def sync_league(request):
    """POST /api/steam/sync/ - Trigger league sync (full or incremental)"""
    serializer = SyncLeagueRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    league_id = serializer.validated_data["league_id"]
    full_sync = serializer.validated_data["full_sync"]

    result = sync_league_matches(league_id, full_sync=full_sync)
    return Response(result, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsStaff])
def retry_failed(request):
    """POST /api/steam/retry-failed/ - Retry failed match fetches"""
    league_id = request.data.get("league_id", LEAGUE_ID)
    result = retry_failed_matches(league_id)
    return Response(result, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsStaff])
def relink_users(request):
    """POST /api/steam/relink-users/ - Re-link users to match stats"""
    linked_count = relink_all_users()
    return Response({"linked_count": linked_count}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def find_matches_by_players_view(request):
    """POST /api/steam/find-by-players/ - Find matches by player steam IDs"""
    serializer = FindMatchesByPlayersSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    matches = find_matches_by_players(
        steam_ids=serializer.validated_data["steam_ids"],
        require_all=serializer.validated_data.get("require_all", True),
        league_id=serializer.validated_data.get("league_id"),
    )
    return Response(MatchSerializer(matches, many=True).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_live_games(request):
    """GET /api/steam/live/ - Get live league games"""
    from steam.utils.steam_api_caller import SteamAPI

    league_id = request.query_params.get("league_id", LEAGUE_ID)
    try:
        api = SteamAPI()
        result = api.get_live_league_games(league_id=int(league_id))
        return Response(result, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_sync_status(request):
    """GET /api/steam/sync-status/ - Get current sync state"""
    league_id = request.query_params.get("league_id", LEAGUE_ID)
    try:
        state = LeagueSyncState.objects.get(league_id=league_id)
        return Response({
            "league_id": state.league_id,
            "last_sync_at": state.last_sync_at,
            "last_match_id": state.last_match_id,
            "is_syncing": state.is_syncing,
            "failed_count": len(state.failed_match_ids),
        }, status=status.HTTP_200_OK)
    except LeagueSyncState.DoesNotExist:
        return Response({
            "league_id": int(league_id),
            "last_sync_at": None,
            "last_match_id": None,
            "is_syncing": False,
            "failed_count": 0,
        }, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsStaff])
def auto_link_tournament(request):
    """POST /api/steam/auto-link/ - Trigger auto-linking for a tournament"""
    serializer = AutoLinkRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    result = auto_link_matches_for_tournament(
        serializer.validated_data["tournament_id"]
    )
    return Response(result, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_tournament_suggestions(request, tournament_id):
    """GET /api/steam/suggestions/tournament/<id>/ - Get suggestions for tournament"""
    suggestions = get_suggestions_for_tournament(tournament_id)
    return Response(
        GameMatchSuggestionSerializer(suggestions, many=True).data,
        status=status.HTTP_200_OK
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def get_game_suggestions(request, game_id):
    """GET /api/steam/suggestions/game/<id>/ - Get suggestions for a game"""
    suggestions = get_suggestions_for_game(game_id)
    return Response(
        GameMatchSuggestionSerializer(suggestions, many=True).data,
        status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([IsStaff])
def confirm_suggestion_view(request, suggestion_id):
    """POST /api/steam/suggestions/<id>/confirm/ - Confirm a suggestion"""
    success = confirm_suggestion(suggestion_id)
    if success:
        return Response({"status": "confirmed"}, status=status.HTTP_200_OK)
    return Response({"error": "Suggestion not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([IsStaff])
def dismiss_suggestion_view(request, suggestion_id):
    """POST /api/steam/suggestions/<id>/dismiss/ - Dismiss a suggestion"""
    success = dismiss_suggestion(suggestion_id)
    if success:
        return Response({"status": "dismissed"}, status=status.HTTP_200_OK)
    return Response({"error": "Suggestion not found"}, status=status.HTTP_404_NOT_FOUND)
```

**Step 4: Update URLs**

Update `backend/steam/urls.py`:

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
    path("find-by-players/", steam_api.find_matches_by_players_view, name="steam_find_by_players"),
    path("live/", steam_api.get_live_games, name="steam_live_games"),
    path("sync-status/", steam_api.get_sync_status, name="steam_sync_status"),

    # Game-Match Auto-Linking
    path("auto-link/", steam_api.auto_link_tournament, name="steam_auto_link"),
    path("suggestions/tournament/<int:tournament_id>/", steam_api.get_tournament_suggestions, name="steam_tournament_suggestions"),
    path("suggestions/game/<int:game_id>/", steam_api.get_game_suggestions, name="steam_game_suggestions"),
    path("suggestions/<int:suggestion_id>/confirm/", steam_api.confirm_suggestion_view, name="steam_confirm_suggestion"),
    path("suggestions/<int:suggestion_id>/dismiss/", steam_api.dismiss_suggestion_view, name="steam_dismiss_suggestion"),
]
```

**Step 5: Run test to verify it passes**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_api -v 2`

Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add backend/steam/functions/api.py backend/steam/urls.py backend/steam/tests/test_api.py
git commit -m "feat(steam): add REST API endpoints for sync, matching, and suggestions"
```

---

## Task 17: Run Full Test Suite

**Step 1: Run all steam tests**

```bash
cd backend && DISABLE_CACHE=true python manage.py test steam -v 2
```

Expected: All tests pass

**Step 2: Run full backend tests**

```bash
cd backend && DISABLE_CACHE=true python manage.py test -v 2
```

Expected: No regressions

**Step 3: Commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address test failures"
```

---

## Task 18: Final Review and Cleanup

**Step 1: Verify all imports work**

```bash
cd backend && python -c "
from steam.models import LeagueSyncState, GameMatchSuggestion
from steam.functions.league_sync import sync_league_matches, process_match, relink_all_users
from steam.functions.match_utils import find_matches_by_players, find_matches_by_team
from steam.functions.game_linking import auto_link_matches_for_tournament, confirm_suggestion
from steam.functions.api import sync_league, get_sync_status
print('All imports successful!')
"
```

**Step 2: Check for any linting issues**

```bash
cd backend && python -m py_compile steam/models.py steam/serializers.py steam/functions/*.py
```

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup and import verification"
```

---

## Summary

This plan implements:

1. **Models** (Tasks 1-4): `LeagueSyncState`, updated `PlayerMatchStats` with user FK, `Match` with league_id, `GameMatchSuggestion`

2. **Steam API** (Task 5): `get_match_history`, `get_live_league_games` methods

3. **Utilities** (Task 6): `retry_with_backoff` for resilient API calls

4. **Sync Services** (Tasks 7-10): User linking, match processing, league sync, retry failed

5. **Player Matching** (Tasks 11-12): Find matches by players/team

6. **Game Linking** (Tasks 13-14): Suggestions, confirm/dismiss, auto-link

7. **API Layer** (Tasks 15-16): Serializers and REST endpoints

8. **Testing** (Tasks 17-18): Full test suite and cleanup

All 18 tasks follow TDD with bite-sized steps and frequent commits.
