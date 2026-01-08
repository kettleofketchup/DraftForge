# League Stats Auto-Fetch Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically fetch Dota2 league matches every minute, aggregate player statistics, and calculate League MMR adjustments displayed on profiles, leaderboards, and user popovers.

**Architecture:** Celery + Redis for background task scheduling, new LeaguePlayerStats model for aggregated stats, additive MMR adjustment formula based on win rate/KDA/GPM vs league averages. Frontend uses React Query for data fetching with shadcn HoverCard for popovers.

**Tech Stack:** Django, Celery, Redis, React, TypeScript, TanStack Query, shadcn/ui

**Design Doc:** `docs/plans/2026-01-07-league-stats-auto-fetch-design.md`

---

## Phase 1: Backend - Celery Setup

### Task 1: Add Celery Dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add celery to dependencies**

Add to `[tool.poetry.dependencies]` section in `pyproject.toml`:

```toml
celery = {extras = ["redis"], version = "^5.3"}
```

**Step 2: Install dependencies**

Run: `poetry install`
Expected: Celery installed successfully

**Step 3: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "chore: add celery dependency"
```

---

### Task 2: Create Celery Configuration

**Files:**
- Create: `backend/config/celery.py`
- Modify: `backend/config/__init__.py`

**Step 1: Create celery.py**

Create `backend/config/celery.py`:

```python
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("dtx")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
```

**Step 2: Update config/__init__.py**

Modify `backend/config/__init__.py` to export celery app:

```python
from .celery import app as celery_app

__all__ = ("celery_app",)
```

**Step 3: Commit**

```bash
git add backend/config/celery.py backend/config/__init__.py
git commit -m "feat: add celery configuration"
```

---

### Task 3: Add Celery Settings to Django

**Files:**
- Modify: `backend/config/settings.py`

**Step 1: Add celery settings**

Add to end of `backend/config/settings.py`:

```python
# Celery Configuration
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300  # 5 minutes

# League Stats Configuration
LEAGUE_MMR_MIN_GAMES = int(os.environ.get("LEAGUE_MMR_MIN_GAMES", "5"))
```

**Step 2: Commit**

```bash
git add backend/config/settings.py
git commit -m "feat: add celery settings to django config"
```

---

### Task 4: Add Celery Services to Docker Compose

**Files:**
- Modify: `docker/docker-compose.debug.yaml`

**Step 1: Read current docker-compose.debug.yaml**

Read the file to understand current structure.

**Step 2: Add celery-worker and celery-beat services**

Add after the existing services:

```yaml
  celery-worker:
    image: ${BACKEND_IMAGE:-ghcr.io/kettleofketchup/dtx-backend:dev}
    command: celery -A config worker -l info
    volumes:
      - ../backend:/app
    env_file:
      - .env.dev
    depends_on:
      - redis
      - backend
    networks:
      - dev-network

  celery-beat:
    image: ${BACKEND_IMAGE:-ghcr.io/kettleofketchup/dtx-backend:dev}
    command: celery -A config beat -l info
    volumes:
      - ../backend:/app
    env_file:
      - .env.dev
    depends_on:
      - redis
      - celery-worker
    networks:
      - dev-network
```

**Step 3: Commit**

```bash
git add docker/docker-compose.debug.yaml
git commit -m "feat: add celery worker and beat services to docker compose"
```

---

## Phase 2: Backend - Data Models

### Task 5: Add LeaguePlayerStats Model

**Files:**
- Modify: `backend/steam/models.py`

**Step 1: Add LeaguePlayerStats model**

Add to `backend/steam/models.py` after `LeagueSyncState`:

```python
class LeaguePlayerStats(models.Model):
    """Aggregated player statistics for a specific league."""

    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="league_stats",
    )
    league_id = models.IntegerField(db_index=True)

    # Core stats
    games_played = models.IntegerField(default=0)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)

    # Aggregated performance (totals for averaging)
    total_kills = models.IntegerField(default=0)
    total_deaths = models.IntegerField(default=0)
    total_assists = models.IntegerField(default=0)
    total_gpm = models.IntegerField(default=0)
    total_xpm = models.IntegerField(default=0)

    # Cached calculations (updated on each match)
    win_rate = models.FloatField(default=0.0)
    avg_kills = models.FloatField(default=0.0)
    avg_deaths = models.FloatField(default=0.0)
    avg_assists = models.FloatField(default=0.0)
    avg_gpm = models.FloatField(default=0.0)
    avg_xpm = models.FloatField(default=0.0)

    # MMR adjustment calculated from performance
    mmr_adjustment = models.IntegerField(default=0)

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "league_id")

    def __str__(self):
        return f"{self.user.username} - League {self.league_id} ({self.games_played} games)"

    def recalculate_averages(self):
        """Recalculate cached average fields from totals."""
        if self.games_played > 0:
            self.win_rate = self.wins / self.games_played
            self.avg_kills = self.total_kills / self.games_played
            self.avg_deaths = self.total_deaths / self.games_played
            self.avg_assists = self.total_assists / self.games_played
            self.avg_gpm = self.total_gpm / self.games_played
            self.avg_xpm = self.total_xpm / self.games_played
        else:
            self.win_rate = 0.0
            self.avg_kills = 0.0
            self.avg_deaths = 0.0
            self.avg_assists = 0.0
            self.avg_gpm = 0.0
            self.avg_xpm = 0.0
```

**Step 2: Commit**

```bash
git add backend/steam/models.py
git commit -m "feat: add LeaguePlayerStats model"
```

---

### Task 6: Add league_mmr Field to CustomUser

**Files:**
- Modify: `backend/app/models.py`

**Step 1: Add league_mmr field to CustomUser**

In `backend/app/models.py`, add after the `mmr` field in `CustomUser`:

```python
    league_mmr = models.IntegerField(null=True, blank=True)
```

**Step 2: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add league_mmr field to CustomUser"
```

---

### Task 7: Create and Run Migrations

**Files:**
- Create: `backend/steam/migrations/0007_leagueplayerstats.py` (auto-generated)
- Create: `backend/app/migrations/XXXX_customuser_league_mmr.py` (auto-generated)

**Step 1: Generate migrations**

Run: `cd backend && DISABLE_CACHE=true python manage.py makemigrations steam app`
Expected: Two migration files created

**Step 2: Review migrations**

Read the generated migration files to verify correctness.

**Step 3: Apply migrations**

Run: `cd backend && DISABLE_CACHE=true python manage.py migrate`
Expected: Migrations applied successfully

**Step 4: Commit**

```bash
git add backend/steam/migrations/ backend/app/migrations/
git commit -m "feat: add migrations for LeaguePlayerStats and league_mmr"
```

---

## Phase 3: Backend - MMR Calculation Logic

### Task 8: Create MMR Calculation Functions

**Files:**
- Create: `backend/steam/functions/mmr_calculation.py`
- Create: `backend/steam/tests/test_mmr_calculation.py`

**Step 1: Write failing tests**

Create `backend/steam/tests/test_mmr_calculation.py`:

```python
import pytest
from django.conf import settings
from django.test import TestCase, override_settings

from app.models import CustomUser, PositionsModel
from steam.functions.mmr_calculation import (
    calculate_mmr_adjustment,
    get_league_avg_kda,
    get_league_avg_gpm,
    update_user_league_mmr,
)
from steam.models import LeaguePlayerStats


class TestMMRCalculation(TestCase):
    def setUp(self):
        self.positions = PositionsModel.objects.create()
        self.user = CustomUser.objects.create_user(
            username="testplayer",
            password="testpass",
            mmr=4000,
            positions=self.positions,
        )

    def test_calculate_mmr_adjustment_below_min_games(self):
        """Should return 0 if below minimum games threshold."""
        stats = LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=12345,
            games_played=2,
            wins=2,
            losses=0,
            win_rate=1.0,
            avg_kills=15,
            avg_deaths=2,
            avg_assists=10,
            avg_gpm=600,
            avg_xpm=700,
        )
        adjustment = calculate_mmr_adjustment(stats)
        self.assertEqual(adjustment, 0)

    @override_settings(LEAGUE_MMR_MIN_GAMES=5)
    def test_calculate_mmr_adjustment_high_performer(self):
        """High win rate and stats should give positive adjustment."""
        stats = LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=12345,
            games_played=20,
            wins=14,
            losses=6,
            win_rate=0.7,
            avg_kills=10,
            avg_deaths=4,
            avg_assists=12,
            avg_gpm=550,
            avg_xpm=600,
        )
        adjustment = calculate_mmr_adjustment(stats)
        self.assertGreater(adjustment, 0)
        self.assertLessEqual(adjustment, 500)

    @override_settings(LEAGUE_MMR_MIN_GAMES=5)
    def test_calculate_mmr_adjustment_low_performer(self):
        """Low win rate and stats should give negative adjustment."""
        stats = LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=12345,
            games_played=20,
            wins=6,
            losses=14,
            win_rate=0.3,
            avg_kills=3,
            avg_deaths=9,
            avg_assists=5,
            avg_gpm=350,
            avg_xpm=400,
        )
        adjustment = calculate_mmr_adjustment(stats)
        self.assertLess(adjustment, 0)
        self.assertGreaterEqual(adjustment, -500)

    @override_settings(LEAGUE_MMR_MIN_GAMES=5)
    def test_calculate_mmr_adjustment_clamped_to_range(self):
        """Adjustment should be clamped between -500 and +500."""
        # Extreme high performer
        stats = LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=12345,
            games_played=50,
            wins=50,
            losses=0,
            win_rate=1.0,
            avg_kills=20,
            avg_deaths=1,
            avg_assists=15,
            avg_gpm=800,
            avg_xpm=900,
        )
        adjustment = calculate_mmr_adjustment(stats)
        self.assertEqual(adjustment, 500)

    def test_update_user_league_mmr(self):
        """Should set league_mmr to base mmr + best adjustment."""
        LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=12345,
            games_played=10,
            mmr_adjustment=150,
        )
        LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=67890,
            games_played=10,
            mmr_adjustment=200,
        )
        update_user_league_mmr(self.user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.league_mmr, 4200)  # 4000 + 200

    def test_update_user_league_mmr_no_base_mmr(self):
        """Should set league_mmr to None if user has no base mmr."""
        self.user.mmr = None
        self.user.save()
        update_user_league_mmr(self.user)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.league_mmr)
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_mmr_calculation -v 2`
Expected: FAIL - ImportError (module doesn't exist yet)

**Step 3: Create mmr_calculation.py**

Create `backend/steam/functions/mmr_calculation.py`:

```python
import logging

from django.conf import settings
from django.db.models import Avg, Max

logger = logging.getLogger(__name__)


def get_league_avg_kda(league_id: int) -> float:
    """Get the average KDA for all players in a league."""
    from steam.models import LeaguePlayerStats

    stats = LeaguePlayerStats.objects.filter(
        league_id=league_id,
        games_played__gte=settings.LEAGUE_MMR_MIN_GAMES,
    ).aggregate(
        avg_kills=Avg("avg_kills"),
        avg_deaths=Avg("avg_deaths"),
        avg_assists=Avg("avg_assists"),
    )

    avg_kills = stats["avg_kills"] or 0
    avg_deaths = stats["avg_deaths"] or 1
    avg_assists = stats["avg_assists"] or 0

    return (avg_kills + avg_assists) / max(avg_deaths, 1)


def get_league_avg_gpm(league_id: int) -> float:
    """Get the average GPM for all players in a league."""
    from steam.models import LeaguePlayerStats

    result = LeaguePlayerStats.objects.filter(
        league_id=league_id,
        games_played__gte=settings.LEAGUE_MMR_MIN_GAMES,
    ).aggregate(avg_gpm=Avg("avg_gpm"))

    return result["avg_gpm"] or 400  # Default to 400 GPM


def calculate_mmr_adjustment(stats) -> int:
    """
    Calculate MMR adjustment based on league performance.
    Returns 0 if below minimum games threshold.
    Range: -500 to +500
    """
    min_games = getattr(settings, "LEAGUE_MMR_MIN_GAMES", 5)

    if stats.games_played < min_games:
        return 0

    # Factor 1: Win rate (50% = neutral)
    # 60% = +20, 40% = -20
    win_factor = (stats.win_rate - 0.5) * 200

    # Factor 2: KDA vs league average
    player_kda = (stats.avg_kills + stats.avg_assists) / max(stats.avg_deaths, 1)
    league_avg_kda = get_league_avg_kda(stats.league_id)
    kda_diff = player_kda - league_avg_kda
    kda_factor = kda_diff * 50  # ~50 per point above/below avg

    # Factor 3: GPM vs league average
    league_avg_gpm = get_league_avg_gpm(stats.league_id)
    gpm_diff = stats.avg_gpm - league_avg_gpm
    gpm_factor = gpm_diff * 0.5  # ~50 per 100 GPM difference

    # Combine and clamp
    adjustment = int(win_factor + kda_factor + gpm_factor)
    return max(-500, min(500, adjustment))


def update_user_league_mmr(user) -> None:
    """
    Set user's league_mmr to base mmr + best league adjustment.
    """
    if not user.mmr:
        user.league_mmr = None
        user.save(update_fields=["league_mmr"])
        return

    best_adjustment = user.league_stats.aggregate(Max("mmr_adjustment"))[
        "mmr_adjustment__max"
    ]

    if best_adjustment is None:
        best_adjustment = 0

    user.league_mmr = user.mmr + best_adjustment
    user.save(update_fields=["league_mmr"])
    logger.debug(
        f"Updated {user.username} league_mmr to {user.league_mmr} "
        f"(base: {user.mmr}, adjustment: {best_adjustment})"
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_mmr_calculation -v 2`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/steam/functions/mmr_calculation.py backend/steam/tests/test_mmr_calculation.py
git commit -m "feat: add MMR calculation functions with tests"
```

---

## Phase 4: Backend - Celery Tasks

### Task 9: Create Stats Update Functions

**Files:**
- Create: `backend/steam/functions/stats_update.py`
- Create: `backend/steam/tests/test_stats_update.py`

**Step 1: Write failing tests**

Create `backend/steam/tests/test_stats_update.py`:

```python
from django.test import TestCase

from app.models import CustomUser, PositionsModel
from steam.functions.stats_update import update_player_league_stats
from steam.models import LeaguePlayerStats, Match, PlayerMatchStats


class TestStatsUpdate(TestCase):
    def setUp(self):
        self.positions = PositionsModel.objects.create()
        self.user = CustomUser.objects.create_user(
            username="testplayer",
            password="testpass",
            steamid=76561198000000001,
            mmr=4000,
            positions=self.positions,
        )
        self.league_id = 12345

    def test_update_player_league_stats_creates_new(self):
        """Should create LeaguePlayerStats if doesn't exist."""
        # Create a match and player stats
        match = Match.objects.create(
            match_id=1001,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=self.league_id,
        )
        PlayerMatchStats.objects.create(
            match=match,
            steam_id=76561198000000001,
            user=self.user,
            player_slot=0,  # Radiant
            hero_id=1,
            kills=10,
            deaths=3,
            assists=15,
            gold_per_min=550,
            xp_per_min=600,
            last_hits=200,
            denies=10,
            hero_damage=25000,
            tower_damage=3000,
            hero_healing=0,
        )

        update_player_league_stats(self.user, self.league_id)

        stats = LeaguePlayerStats.objects.get(user=self.user, league_id=self.league_id)
        self.assertEqual(stats.games_played, 1)
        self.assertEqual(stats.wins, 1)
        self.assertEqual(stats.losses, 0)
        self.assertEqual(stats.total_kills, 10)
        self.assertEqual(stats.avg_kills, 10.0)

    def test_update_player_league_stats_accumulates(self):
        """Should accumulate stats from multiple matches."""
        # Create two matches
        for i, (radiant_win, player_slot) in enumerate([(True, 0), (False, 0)]):
            match = Match.objects.create(
                match_id=1001 + i,
                radiant_win=radiant_win,
                duration=2400,
                start_time=1704067200 + i * 3600,
                game_mode=22,
                lobby_type=1,
                league_id=self.league_id,
            )
            PlayerMatchStats.objects.create(
                match=match,
                steam_id=76561198000000001,
                user=self.user,
                player_slot=player_slot,
                hero_id=1,
                kills=10,
                deaths=5,
                assists=10,
                gold_per_min=500,
                xp_per_min=550,
                last_hits=180,
                denies=8,
                hero_damage=20000,
                tower_damage=2000,
                hero_healing=0,
            )

        update_player_league_stats(self.user, self.league_id)

        stats = LeaguePlayerStats.objects.get(user=self.user, league_id=self.league_id)
        self.assertEqual(stats.games_played, 2)
        self.assertEqual(stats.wins, 1)
        self.assertEqual(stats.losses, 1)
        self.assertEqual(stats.win_rate, 0.5)
        self.assertEqual(stats.total_kills, 20)
        self.assertEqual(stats.avg_kills, 10.0)
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_stats_update -v 2`
Expected: FAIL - ImportError

**Step 3: Create stats_update.py**

Create `backend/steam/functions/stats_update.py`:

```python
import logging

from django.db.models import Sum

from steam.functions.mmr_calculation import calculate_mmr_adjustment, update_user_league_mmr
from steam.models import LeaguePlayerStats, PlayerMatchStats

logger = logging.getLogger(__name__)


def update_player_league_stats(user, league_id: int) -> LeaguePlayerStats:
    """
    Recalculate a player's aggregated stats for a specific league.
    Creates LeaguePlayerStats if it doesn't exist.
    """
    # Get all player's match stats for this league
    match_stats = PlayerMatchStats.objects.filter(
        user=user,
        match__league_id=league_id,
    ).select_related("match")

    if not match_stats.exists():
        logger.debug(f"No match stats found for {user.username} in league {league_id}")
        return None

    # Calculate aggregates
    totals = match_stats.aggregate(
        total_kills=Sum("kills"),
        total_deaths=Sum("deaths"),
        total_assists=Sum("assists"),
        total_gpm=Sum("gold_per_min"),
        total_xpm=Sum("xp_per_min"),
    )

    games_played = match_stats.count()

    # Calculate wins/losses
    wins = 0
    losses = 0
    for stat in match_stats:
        is_radiant = stat.player_slot < 128
        player_won = (is_radiant and stat.match.radiant_win) or (
            not is_radiant and not stat.match.radiant_win
        )
        if player_won:
            wins += 1
        else:
            losses += 1

    # Create or update LeaguePlayerStats
    stats, created = LeaguePlayerStats.objects.update_or_create(
        user=user,
        league_id=league_id,
        defaults={
            "games_played": games_played,
            "wins": wins,
            "losses": losses,
            "total_kills": totals["total_kills"] or 0,
            "total_deaths": totals["total_deaths"] or 0,
            "total_assists": totals["total_assists"] or 0,
            "total_gpm": totals["total_gpm"] or 0,
            "total_xpm": totals["total_xpm"] or 0,
        },
    )

    # Recalculate averages
    stats.recalculate_averages()

    # Calculate MMR adjustment
    stats.mmr_adjustment = calculate_mmr_adjustment(stats)
    stats.save()

    # Update user's league_mmr
    update_user_league_mmr(user)

    logger.info(
        f"Updated league stats for {user.username}: "
        f"{games_played} games, {wins}W-{losses}L, adjustment={stats.mmr_adjustment}"
    )

    return stats


def update_all_league_stats_for_league(league_id: int) -> int:
    """
    Update league stats for all users who have played in a league.
    Returns count of users updated.
    """
    from app.models import CustomUser

    # Find all users with match stats in this league
    user_ids = (
        PlayerMatchStats.objects.filter(match__league_id=league_id, user__isnull=False)
        .values_list("user_id", flat=True)
        .distinct()
    )

    updated_count = 0
    for user_id in user_ids:
        try:
            user = CustomUser.objects.get(pk=user_id)
            update_player_league_stats(user, league_id)
            updated_count += 1
        except CustomUser.DoesNotExist:
            continue

    logger.info(f"Updated league stats for {updated_count} users in league {league_id}")
    return updated_count
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_stats_update -v 2`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/steam/functions/stats_update.py backend/steam/tests/test_stats_update.py
git commit -m "feat: add stats update functions with tests"
```

---

### Task 10: Create Celery Tasks

**Files:**
- Create: `backend/steam/tasks.py`

**Step 1: Create tasks.py**

Create `backend/steam/tasks.py`:

```python
import logging

from celery import shared_task

from steam.constants import LEAGUE_ID
from steam.functions.league_sync import sync_league_matches
from steam.functions.stats_update import update_all_league_stats_for_league

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_league_matches_task(self, league_id: int = None):
    """
    Fetch new matches from Steam API for a league.
    Scheduled to run every minute.
    """
    if league_id is None:
        league_id = LEAGUE_ID

    logger.info(f"Starting league sync for league {league_id}")

    try:
        result = sync_league_matches(league_id, full_sync=False)
        logger.info(
            f"League sync complete: {result['synced_count']} synced, "
            f"{result['failed_count']} failed"
        )

        # If new matches were synced, update stats
        if result["synced_count"] > 0:
            update_league_stats_task.delay(league_id)

        return result
    except Exception as exc:
        logger.error(f"League sync failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True)
def update_league_stats_task(self, league_id: int = None):
    """
    Update LeaguePlayerStats for all users in a league.
    Called after new matches are synced.
    """
    if league_id is None:
        league_id = LEAGUE_ID

    logger.info(f"Updating league stats for league {league_id}")

    try:
        updated_count = update_all_league_stats_for_league(league_id)
        logger.info(f"Updated stats for {updated_count} users")
        return {"updated_count": updated_count}
    except Exception as exc:
        logger.error(f"Stats update failed: {exc}")
        raise


@shared_task
def recalculate_user_league_mmr_task(user_id: int):
    """
    Recalculate a single user's league_mmr.
    Useful for manual recalculation.
    """
    from app.models import CustomUser
    from steam.functions.mmr_calculation import update_user_league_mmr

    try:
        user = CustomUser.objects.get(pk=user_id)
        update_user_league_mmr(user)
        logger.info(f"Recalculated league MMR for {user.username}: {user.league_mmr}")
        return {"user_id": user_id, "league_mmr": user.league_mmr}
    except CustomUser.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return None
```

**Step 2: Commit**

```bash
git add backend/steam/tasks.py
git commit -m "feat: add celery tasks for league sync and stats update"
```

---

### Task 11: Add Celery Beat Schedule

**Files:**
- Modify: `backend/config/celery.py`

**Step 1: Add beat schedule**

Update `backend/config/celery.py` to add the schedule:

```python
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("dtx")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Beat schedule for periodic tasks
app.conf.beat_schedule = {
    "sync-league-matches-every-minute": {
        "task": "steam.tasks.sync_league_matches_task",
        "schedule": 60.0,  # Every 60 seconds
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
```

**Step 2: Commit**

```bash
git add backend/config/celery.py
git commit -m "feat: add celery beat schedule for periodic sync"
```

---

## Phase 5: Backend - API Endpoints

### Task 12: Create Serializers

**Files:**
- Modify: `backend/steam/serializers.py`

**Step 1: Read current serializers.py**

Read the file to understand current structure.

**Step 2: Add LeaguePlayerStats serializers**

Add to `backend/steam/serializers.py`:

```python
class LeaguePlayerStatsSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    avatar = serializers.CharField(source="user.avatar", read_only=True)
    base_mmr = serializers.IntegerField(source="user.mmr", read_only=True)
    league_mmr = serializers.IntegerField(source="user.league_mmr", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = LeaguePlayerStats
        fields = [
            "user_id",
            "username",
            "avatar",
            "base_mmr",
            "league_mmr",
            "league_id",
            "games_played",
            "wins",
            "losses",
            "win_rate",
            "avg_kills",
            "avg_deaths",
            "avg_assists",
            "avg_gpm",
            "avg_xpm",
            "mmr_adjustment",
            "last_updated",
        ]


class LeaderboardSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    avatar = serializers.CharField(source="user.avatar", read_only=True)
    base_mmr = serializers.IntegerField(source="user.mmr", read_only=True)
    league_mmr = serializers.IntegerField(source="user.league_mmr", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    avg_kda = serializers.SerializerMethodField()

    class Meta:
        model = LeaguePlayerStats
        fields = [
            "user_id",
            "username",
            "avatar",
            "base_mmr",
            "league_mmr",
            "mmr_adjustment",
            "games_played",
            "win_rate",
            "avg_kills",
            "avg_deaths",
            "avg_assists",
            "avg_kda",
            "avg_gpm",
            "avg_xpm",
        ]

    def get_avg_kda(self, obj):
        if obj.avg_deaths == 0:
            return obj.avg_kills + obj.avg_assists
        return round((obj.avg_kills + obj.avg_assists) / obj.avg_deaths, 2)
```

**Step 3: Add import for LeaguePlayerStats model**

Ensure `LeaguePlayerStats` is imported at top of file:

```python
from steam.models import LeaguePlayerStats, Match, PlayerMatchStats
```

**Step 4: Commit**

```bash
git add backend/steam/serializers.py
git commit -m "feat: add leaderboard and league stats serializers"
```

---

### Task 13: Create API Views

**Files:**
- Modify: `backend/steam/views.py`

**Step 1: Read current views.py**

Read the file to understand current structure.

**Step 2: Add leaderboard and stats views**

Add to `backend/steam/views.py`:

```python
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from steam.constants import LEAGUE_ID
from steam.models import LeaguePlayerStats
from steam.serializers import LeaderboardSerializer, LeaguePlayerStatsSerializer


class LeaderboardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class LeaderboardView(generics.ListAPIView):
    """
    GET /api/steam/leaderboard/
    Returns paginated leaderboard sorted by league_mmr.

    Query params:
    - sort_by: league_mmr, win_rate, games_played, avg_kda (default: league_mmr)
    - order: desc, asc (default: desc)
    - page: page number
    - page_size: items per page (default: 20, max: 100)
    """
    serializer_class = LeaderboardSerializer
    pagination_class = LeaderboardPagination

    def get_queryset(self):
        queryset = LeaguePlayerStats.objects.filter(
            league_id=LEAGUE_ID,
            games_played__gt=0,
            user__isnull=False,
        ).select_related("user")

        # Sorting
        sort_by = self.request.query_params.get("sort_by", "league_mmr")
        order = self.request.query_params.get("order", "desc")

        sort_fields = {
            "league_mmr": "user__league_mmr",
            "win_rate": "win_rate",
            "games_played": "games_played",
            "avg_kda": "avg_kills",  # Approximate sort
        }

        sort_field = sort_fields.get(sort_by, "user__league_mmr")
        if order == "desc":
            sort_field = f"-{sort_field}"

        return queryset.order_by(sort_field)


class LeagueStatsView(APIView):
    """
    GET /api/steam/league-stats/<user_id>/
    Returns a user's league stats.
    """
    def get(self, request, user_id):
        try:
            stats = LeaguePlayerStats.objects.select_related("user").get(
                user_id=user_id,
                league_id=LEAGUE_ID,
            )
            serializer = LeaguePlayerStatsSerializer(stats)
            return Response(serializer.data)
        except LeaguePlayerStats.DoesNotExist:
            return Response(
                {"error": "No league stats found for this user"},
                status=status.HTTP_404_NOT_FOUND,
            )


class MyLeagueStatsView(APIView):
    """
    GET /api/steam/league-stats/me/
    Returns the authenticated user's league stats.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            stats = LeaguePlayerStats.objects.select_related("user").get(
                user=request.user,
                league_id=LEAGUE_ID,
            )
            serializer = LeaguePlayerStatsSerializer(stats)
            return Response(serializer.data)
        except LeaguePlayerStats.DoesNotExist:
            return Response(
                {"error": "No league stats found"},
                status=status.HTTP_404_NOT_FOUND,
            )
```

**Step 3: Commit**

```bash
git add backend/steam/views.py
git commit -m "feat: add leaderboard and league stats API views"
```

---

### Task 14: Add URL Routes

**Files:**
- Modify: `backend/steam/urls.py`

**Step 1: Read current urls.py**

Read the file to understand current structure.

**Step 2: Add new routes**

Add to `backend/steam/urls.py`:

```python
from steam.views import LeaderboardView, LeagueStatsView, MyLeagueStatsView

urlpatterns = [
    # ... existing routes ...
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("league-stats/me/", MyLeagueStatsView.as_view(), name="my-league-stats"),
    path("league-stats/<int:user_id>/", LeagueStatsView.as_view(), name="league-stats"),
]
```

**Step 3: Commit**

```bash
git add backend/steam/urls.py
git commit -m "feat: add leaderboard and league stats URL routes"
```

---

### Task 15: Write API Tests

**Files:**
- Create: `backend/steam/tests/test_leaderboard_api.py`

**Step 1: Create test file**

Create `backend/steam/tests/test_leaderboard_api.py`:

```python
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, PositionsModel
from steam.constants import LEAGUE_ID
from steam.models import LeaguePlayerStats


class TestLeaderboardAPI(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.positions = PositionsModel.objects.create()

        # Create test users with stats
        self.users = []
        for i in range(5):
            user = CustomUser.objects.create_user(
                username=f"player{i}",
                password="testpass",
                mmr=3000 + i * 200,
                league_mmr=3000 + i * 200 + (i * 50),
                positions=self.positions,
            )
            self.users.append(user)
            LeaguePlayerStats.objects.create(
                user=user,
                league_id=LEAGUE_ID,
                games_played=10 + i,
                wins=5 + i,
                losses=5,
                win_rate=(5 + i) / (10 + i),
                avg_kills=8 + i,
                avg_deaths=5,
                avg_assists=10,
                avg_gpm=450 + i * 20,
                avg_xpm=500 + i * 20,
                mmr_adjustment=i * 50,
            )

    def test_leaderboard_returns_sorted_by_league_mmr(self):
        response = self.client.get(reverse("leaderboard"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 5)
        # Should be sorted by league_mmr descending
        mmrs = [r["league_mmr"] for r in results]
        self.assertEqual(mmrs, sorted(mmrs, reverse=True))

    def test_leaderboard_pagination(self):
        response = self.client.get(reverse("leaderboard"), {"page_size": 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])

    def test_leaderboard_sort_by_win_rate(self):
        response = self.client.get(
            reverse("leaderboard"),
            {"sort_by": "win_rate", "order": "desc"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        win_rates = [r["win_rate"] for r in results]
        self.assertEqual(win_rates, sorted(win_rates, reverse=True))

    def test_league_stats_returns_user_stats(self):
        user = self.users[0]
        response = self.client.get(
            reverse("league-stats", kwargs={"user_id": user.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], user.username)
        self.assertEqual(response.data["games_played"], 10)

    def test_league_stats_404_for_unknown_user(self):
        response = self.client.get(
            reverse("league-stats", kwargs={"user_id": 99999})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_my_league_stats_requires_auth(self):
        response = self.client.get(reverse("my-league-stats"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_my_league_stats_returns_authenticated_user_stats(self):
        user = self.users[0]
        self.client.force_authenticate(user=user)
        response = self.client.get(reverse("my-league-stats"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], user.username)
```

**Step 2: Run tests**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam.tests.test_leaderboard_api -v 2`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add backend/steam/tests/test_leaderboard_api.py
git commit -m "test: add leaderboard API tests"
```

---

## Phase 6: Frontend - Components

### Task 16: Create TypeScript Types

**Files:**
- Create: `frontend/app/features/leaderboard/types.ts`

**Step 1: Create types file**

Create `frontend/app/features/leaderboard/types.ts`:

```typescript
export interface LeagueStats {
  user_id: number;
  username: string;
  avatar: string | null;
  base_mmr: number | null;
  league_mmr: number | null;
  league_id: number;
  games_played: number;
  wins: number;
  losses: number;
  win_rate: number;
  avg_kills: number;
  avg_deaths: number;
  avg_assists: number;
  avg_gpm: number;
  avg_xpm: number;
  mmr_adjustment: number;
  last_updated: string;
}

export interface LeaderboardEntry {
  user_id: number;
  username: string;
  avatar: string | null;
  base_mmr: number | null;
  league_mmr: number | null;
  mmr_adjustment: number;
  games_played: number;
  win_rate: number;
  avg_kills: number;
  avg_deaths: number;
  avg_assists: number;
  avg_kda: number;
  avg_gpm: number;
  avg_xpm: number;
}

export interface LeaderboardResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: LeaderboardEntry[];
}

export type SortField = "league_mmr" | "win_rate" | "games_played" | "avg_kda";
export type SortOrder = "asc" | "desc";
```

**Step 2: Commit**

```bash
git add frontend/app/features/leaderboard/types.ts
git commit -m "feat: add leaderboard TypeScript types"
```

---

### Task 17: Create API Queries

**Files:**
- Create: `frontend/app/features/leaderboard/queries.ts`

**Step 1: Create queries file**

Create `frontend/app/features/leaderboard/queries.ts`:

```typescript
import { useQuery } from "@tanstack/react-query";
import {
  LeaderboardResponse,
  LeagueStats,
  SortField,
  SortOrder,
} from "./types";

const API_BASE = "/api/steam";

interface LeaderboardParams {
  page?: number;
  pageSize?: number;
  sortBy?: SortField;
  order?: SortOrder;
}

async function fetchLeaderboard(
  params: LeaderboardParams
): Promise<LeaderboardResponse> {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set("page", String(params.page));
  if (params.pageSize) searchParams.set("page_size", String(params.pageSize));
  if (params.sortBy) searchParams.set("sort_by", params.sortBy);
  if (params.order) searchParams.set("order", params.order);

  const response = await fetch(`${API_BASE}/leaderboard/?${searchParams}`);
  if (!response.ok) {
    throw new Error("Failed to fetch leaderboard");
  }
  return response.json();
}

async function fetchUserLeagueStats(userId: number): Promise<LeagueStats> {
  const response = await fetch(`${API_BASE}/league-stats/${userId}/`);
  if (!response.ok) {
    throw new Error("Failed to fetch league stats");
  }
  return response.json();
}

async function fetchMyLeagueStats(): Promise<LeagueStats> {
  const response = await fetch(`${API_BASE}/league-stats/me/`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error("Failed to fetch league stats");
  }
  return response.json();
}

export function useLeaderboard(params: LeaderboardParams = {}) {
  return useQuery({
    queryKey: ["leaderboard", params],
    queryFn: () => fetchLeaderboard(params),
  });
}

export function useUserLeagueStats(userId: number | null) {
  return useQuery({
    queryKey: ["league-stats", userId],
    queryFn: () => fetchUserLeagueStats(userId!),
    enabled: userId !== null,
  });
}

export function useMyLeagueStats() {
  return useQuery({
    queryKey: ["league-stats", "me"],
    queryFn: fetchMyLeagueStats,
  });
}
```

**Step 2: Commit**

```bash
git add frontend/app/features/leaderboard/queries.ts
git commit -m "feat: add leaderboard React Query hooks"
```

---

### Task 18: Create LeagueStatsCard Component

**Files:**
- Create: `frontend/app/components/user/LeagueStatsCard.tsx`

**Step 1: Create component file**

Create `frontend/app/components/user/LeagueStatsCard.tsx`:

```tsx
import { cn } from "~/lib/utils";

interface LeagueStatsCardProps {
  stats: {
    games_played: number;
    win_rate: number;
    avg_kills: number;
    avg_deaths: number;
    avg_assists: number;
    avg_gpm: number;
    avg_xpm: number;
    mmr_adjustment: number;
  };
  baseMmr: number | null;
  leagueMmr: number | null;
  compact?: boolean;
}

export function LeagueStatsCard({
  stats,
  baseMmr,
  leagueMmr,
  compact = false,
}: LeagueStatsCardProps) {
  const adjustment = stats.mmr_adjustment;
  const adjustmentColor =
    adjustment > 0
      ? "text-green-500"
      : adjustment < 0
        ? "text-red-500"
        : "text-gray-500";
  const adjustmentText =
    adjustment > 0 ? `+${adjustment}` : String(adjustment);

  const winRatePercent = Math.round(stats.win_rate * 100);
  const winRateColor =
    winRatePercent >= 55
      ? "text-green-500"
      : winRatePercent <= 45
        ? "text-red-500"
        : "text-gray-300";

  if (compact) {
    return (
      <div className="space-y-1 text-sm">
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold">
            {leagueMmr ?? baseMmr ?? "—"}
          </span>
          <span className={cn("text-xs", adjustmentColor)}>
            ({adjustmentText})
          </span>
        </div>
        <div className="text-gray-400">
          {stats.games_played} games •{" "}
          <span className={winRateColor}>{winRatePercent}% WR</span>
        </div>
        <div className="text-gray-400">
          KDA: {stats.avg_kills.toFixed(1)} / {stats.avg_deaths.toFixed(1)} /{" "}
          {stats.avg_assists.toFixed(1)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 rounded-lg border border-gray-700 bg-gray-800 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-200">
          League Performance
        </h3>
        <div className="text-right">
          <div className="text-2xl font-bold text-white">
            {leagueMmr ?? baseMmr ?? "—"}
          </div>
          <div className={cn("text-sm", adjustmentColor)}>
            {adjustmentText} from base
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 text-center">
        <div>
          <div className="text-2xl font-bold text-white">
            {stats.games_played}
          </div>
          <div className="text-xs text-gray-400">Games</div>
        </div>
        <div>
          <div className={cn("text-2xl font-bold", winRateColor)}>
            {winRatePercent}%
          </div>
          <div className="text-xs text-gray-400">Win Rate</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-white">
            {(
              (stats.avg_kills + stats.avg_assists) /
              Math.max(stats.avg_deaths, 1)
            ).toFixed(2)}
          </div>
          <div className="text-xs text-gray-400">KDA</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 border-t border-gray-700 pt-4">
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Avg Kills</span>
            <span className="text-white">{stats.avg_kills.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Avg Deaths</span>
            <span className="text-white">{stats.avg_deaths.toFixed(1)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Avg Assists</span>
            <span className="text-white">{stats.avg_assists.toFixed(1)}</span>
          </div>
        </div>
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Avg GPM</span>
            <span className="text-white">{Math.round(stats.avg_gpm)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Avg XPM</span>
            <span className="text-white">{Math.round(stats.avg_xpm)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/user/LeagueStatsCard.tsx
git commit -m "feat: add LeagueStatsCard component"
```

---

### Task 19: Create UserPopover Component

**Files:**
- Create: `frontend/app/components/user/UserPopover.tsx`

**Step 1: Create component file**

Create `frontend/app/components/user/UserPopover.tsx`:

```tsx
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "~/components/ui/hover-card";
import { useUserLeagueStats } from "~/features/leaderboard/queries";
import { LeagueStatsCard } from "./LeagueStatsCard";

interface UserPopoverProps {
  userId: number;
  username: string;
  avatar?: string | null;
  children?: React.ReactNode;
}

export function UserPopover({
  userId,
  username,
  avatar,
  children,
}: UserPopoverProps) {
  const { data: stats, isLoading } = useUserLeagueStats(userId);

  return (
    <HoverCard>
      <HoverCardTrigger asChild>
        {children ?? (
          <button className="cursor-pointer hover:underline">{username}</button>
        )}
      </HoverCardTrigger>
      <HoverCardContent className="w-64 border-gray-700 bg-gray-800">
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            {avatar && (
              <img
                src={`https://cdn.discordapp.com/avatars/${userId}/${avatar}.png`}
                alt={username}
                className="h-10 w-10 rounded-full"
              />
            )}
            <div className="font-semibold text-white">{username}</div>
          </div>
          {isLoading ? (
            <div className="text-sm text-gray-400">Loading stats...</div>
          ) : stats ? (
            <LeagueStatsCard
              stats={stats}
              baseMmr={stats.base_mmr}
              leagueMmr={stats.league_mmr}
              compact
            />
          ) : (
            <div className="text-sm text-gray-400">No league stats</div>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/user/UserPopover.tsx
git commit -m "feat: add UserPopover component with hover card"
```

---

### Task 20: Create LeaderboardPage

**Files:**
- Create: `frontend/app/features/leaderboard/LeaderboardPage.tsx`
- Create: `frontend/app/features/leaderboard/LeaderboardTable.tsx`
- Create: `frontend/app/features/leaderboard/index.ts`

**Step 1: Create LeaderboardTable component**

Create `frontend/app/features/leaderboard/LeaderboardTable.tsx`:

```tsx
import { useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table";
import { UserPopover } from "~/components/user/UserPopover";
import { cn } from "~/lib/utils";
import { LeaderboardEntry, SortField, SortOrder } from "./types";

interface LeaderboardTableProps {
  entries: LeaderboardEntry[];
  sortBy: SortField;
  order: SortOrder;
  onSort: (field: SortField) => void;
}

export function LeaderboardTable({
  entries,
  sortBy,
  order,
  onSort,
}: LeaderboardTableProps) {
  const SortableHeader = ({
    field,
    children,
  }: {
    field: SortField;
    children: React.ReactNode;
  }) => (
    <TableHead
      className="cursor-pointer select-none hover:bg-gray-700"
      onClick={() => onSort(field)}
    >
      <div className="flex items-center gap-1">
        {children}
        {sortBy === field && (
          <span className="text-xs">{order === "desc" ? "▼" : "▲"}</span>
        )}
      </div>
    </TableHead>
  );

  return (
    <Table>
      <TableHeader>
        <TableRow className="border-gray-700">
          <TableHead className="w-12">#</TableHead>
          <TableHead>Player</TableHead>
          <SortableHeader field="league_mmr">League MMR</SortableHeader>
          <SortableHeader field="games_played">Games</SortableHeader>
          <SortableHeader field="win_rate">Win Rate</SortableHeader>
          <SortableHeader field="avg_kda">KDA</SortableHeader>
          <TableHead>GPM</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((entry, index) => {
          const winRatePercent = Math.round(entry.win_rate * 100);
          const winRateColor =
            winRatePercent >= 55
              ? "text-green-500"
              : winRatePercent <= 45
                ? "text-red-500"
                : "";

          return (
            <TableRow key={entry.user_id} className="border-gray-700">
              <TableCell className="font-medium text-gray-400">
                {index + 1}
              </TableCell>
              <TableCell>
                <UserPopover
                  userId={entry.user_id}
                  username={entry.username}
                  avatar={entry.avatar}
                >
                  <span className="cursor-pointer font-medium hover:underline">
                    {entry.username}
                  </span>
                </UserPopover>
              </TableCell>
              <TableCell>
                <div className="flex items-baseline gap-1">
                  <span className="font-bold">{entry.league_mmr ?? "—"}</span>
                  <span
                    className={cn(
                      "text-xs",
                      entry.mmr_adjustment > 0
                        ? "text-green-500"
                        : entry.mmr_adjustment < 0
                          ? "text-red-500"
                          : "text-gray-500"
                    )}
                  >
                    ({entry.mmr_adjustment > 0 ? "+" : ""}
                    {entry.mmr_adjustment})
                  </span>
                </div>
              </TableCell>
              <TableCell>{entry.games_played}</TableCell>
              <TableCell className={winRateColor}>{winRatePercent}%</TableCell>
              <TableCell>{entry.avg_kda.toFixed(2)}</TableCell>
              <TableCell>{Math.round(entry.avg_gpm)}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
```

**Step 2: Create LeaderboardPage component**

Create `frontend/app/features/leaderboard/LeaderboardPage.tsx`:

```tsx
import { useState } from "react";
import { Button } from "~/components/ui/button";
import { useLeaderboard } from "./queries";
import { LeaderboardTable } from "./LeaderboardTable";
import { SortField, SortOrder } from "./types";

export function LeaderboardPage() {
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<SortField>("league_mmr");
  const [order, setOrder] = useState<SortOrder>("desc");

  const { data, isLoading, error } = useLeaderboard({
    page,
    pageSize: 20,
    sortBy,
    order,
  });

  const handleSort = (field: SortField) => {
    if (field === sortBy) {
      setOrder(order === "desc" ? "asc" : "desc");
    } else {
      setSortBy(field);
      setOrder("desc");
    }
    setPage(1);
  };

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-gray-400">Loading leaderboard...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-red-500">Failed to load leaderboard</div>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8">
      <h1 className="mb-6 text-3xl font-bold text-white">League Leaderboard</h1>

      <div className="rounded-lg border border-gray-700 bg-gray-800">
        <LeaderboardTable
          entries={data?.results ?? []}
          sortBy={sortBy}
          order={order}
          onSort={handleSort}
        />
      </div>

      {data && (
        <div className="mt-4 flex items-center justify-between">
          <div className="text-sm text-gray-400">
            Showing {data.results.length} of {data.count} players
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(page - 1)}
              disabled={!data.previous}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(page + 1)}
              disabled={!data.next}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 3: Create index.ts**

Create `frontend/app/features/leaderboard/index.ts`:

```typescript
export { LeaderboardPage } from "./LeaderboardPage";
export { LeaderboardTable } from "./LeaderboardTable";
export * from "./queries";
export * from "./types";
```

**Step 4: Commit**

```bash
git add frontend/app/features/leaderboard/
git commit -m "feat: add leaderboard page and table components"
```

---

### Task 21: Add Leaderboard Route

**Files:**
- Create: `frontend/app/routes/leaderboard.tsx`
- Modify: Navigation component to add leaderboard link

**Step 1: Create route file**

Create `frontend/app/routes/leaderboard.tsx`:

```tsx
import { LeaderboardPage } from "~/features/leaderboard";

export default function LeaderboardRoute() {
  return <LeaderboardPage />;
}
```

**Step 2: Commit**

```bash
git add frontend/app/routes/leaderboard.tsx
git commit -m "feat: add leaderboard route"
```

---

## Phase 7: Integration & Testing

### Task 22: Run Full Test Suite

**Step 1: Run backend tests**

Run: `cd backend && DISABLE_CACHE=true python manage.py test steam -v 2`
Expected: All tests PASS

**Step 2: Run type checking**

Run: `cd frontend && npm run typecheck`
Expected: No type errors

**Step 3: Commit any fixes if needed**

---

### Task 23: Update Docker Compose for Test Environment

**Files:**
- Modify: `docker/docker-compose.test.yaml`

**Step 1: Add celery services to test compose**

Add the same celery-worker and celery-beat services to test environment.

**Step 2: Commit**

```bash
git add docker/docker-compose.test.yaml
git commit -m "feat: add celery services to test docker compose"
```

---

### Task 24: Final Integration Commit

**Step 1: Verify all changes**

Run: `git status`
Expected: Working tree clean

**Step 2: Create summary commit if needed**

If there are uncommitted changes, commit them with an appropriate message.

---

## Summary

This plan implements:

1. **Celery + Redis** background task system for automatic match fetching
2. **LeaguePlayerStats model** for aggregated per-user league statistics
3. **MMR calculation** with additive adjustment based on win rate, KDA, and GPM
4. **REST API** endpoints for leaderboard and individual stats
5. **Frontend components**: LeagueStatsCard, UserPopover, LeaderboardPage
6. **Full test coverage** for backend logic and API endpoints

Total tasks: 24
Estimated commits: ~20
