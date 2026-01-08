# League Stats & Auto-Fetch Design

## Overview

Automatically fetch Dota2 league matches from Steam API every minute using Celery, aggregate player statistics into a LeaguePlayerStats model, and calculate a League MMR adjustment based on performance. Display stats on user profiles, a leaderboard page, and user hover popovers.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Backend (Django)                        │
├─────────────────────────────────────────────────────────────┤
│  Celery Worker ──────► Steam API Fetcher (every 1 min)      │
│        │                                                     │
│        ▼                                                     │
│  Match/PlayerMatchStats ──► LeaguePlayerStats (aggregated)  │
│        │                           │                         │
│        ▼                           ▼                         │
│  LeagueSyncState            CustomUser.league_mmr            │
├─────────────────────────────────────────────────────────────┤
│                      Redis                                   │
│  • Celery broker/backend                                    │
│  • Cacheops (existing)                                      │
├─────────────────────────────────────────────────────────────┤
│                    Frontend (React)                          │
│  • UserProfile: League Performance section                  │
│  • LeagueLeaderboard: Rankings by League MMR                │
│  • UserPopover: Hover card with stats                       │
└─────────────────────────────────────────────────────────────┘
```

## Data Models

### New Model: LeaguePlayerStats

Location: `steam/models.py`

```python
class LeaguePlayerStats(models.Model):
    user = models.ForeignKey("app.CustomUser", on_delete=models.CASCADE,
                             related_name="league_stats")
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
```

### CustomUser Additions

```python
# Add to CustomUser model
league_mmr = models.IntegerField(null=True, blank=True)  # Calculated: mmr + adjustment
```

### Configuration

```python
# In settings or constants.py
LEAGUE_MMR_MIN_GAMES = 5  # Configurable threshold
```

## Celery Setup

### File Structure

```
backend/
├── config/
│   └── celery.py          # Celery app configuration
├── steam/
│   └── tasks.py           # Celery tasks
docker/
├── docker-compose.debug.yaml  # Add celery worker + beat services
```

### Celery Configuration

Location: `config/celery.py`

```python
from celery import Celery
from celery.schedules import crontab

app = Celery('dtx')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'sync-league-matches-every-minute': {
        'task': 'steam.tasks.sync_league_matches_task',
        'schedule': 60.0,  # Every 60 seconds
    },
}
```

### Tasks

Location: `steam/tasks.py`

```python
@shared_task
def sync_league_matches_task():
    """Fetch new matches from Steam API."""
    sync_league_matches(LEAGUE_ID, full_sync=False)
    update_all_league_stats.delay()  # Chain stats update

@shared_task
def update_all_league_stats():
    """Recalculate LeaguePlayerStats for users with new matches."""
    # Updates aggregates and mmr_adjustment

@shared_task
def recalculate_user_league_mmr(user_id):
    """Recalculate single user's league_mmr from base mmr + adjustment."""
```

### Docker Services

Add to `docker-compose.debug.yaml`:

```yaml
celery-worker:
  image: ${BACKEND_IMAGE}
  command: celery -A config worker -l info
  depends_on: [redis, backend]

celery-beat:
  image: ${BACKEND_IMAGE}
  command: celery -A config beat -l info
  depends_on: [redis, celery-worker]
```

## League MMR Calculation

### MMR Adjustment Formula

Range: -500 to +500, based on performance relative to league averages.

```python
def calculate_mmr_adjustment(stats: LeaguePlayerStats) -> int:
    """
    Calculate MMR adjustment based on league performance.
    Returns 0 if below minimum games threshold.
    """
    if stats.games_played < settings.LEAGUE_MMR_MIN_GAMES:
        return 0

    # Factors (each contributes portion of adjustment)
    # 1. Win rate: 50% = neutral, 60% = +100, 40% = -100
    win_factor = (stats.win_rate - 0.5) * 200  # Range: -100 to +100

    # 2. KDA vs league average
    kda = (stats.avg_kills + stats.avg_assists) / max(stats.avg_deaths, 1)
    league_avg_kda = get_league_avg_kda(stats.league_id)
    kda_factor = (kda - league_avg_kda) * 50  # ~50 per point above/below avg

    # 3. GPM vs league average
    gpm_diff = stats.avg_gpm - get_league_avg_gpm(stats.league_id)
    gpm_factor = gpm_diff * 0.5  # ~50 per 100 GPM difference

    # Combine and clamp
    adjustment = int(win_factor + kda_factor + gpm_factor)
    return max(-500, min(500, adjustment))
```

### League MMR Update

```python
def update_user_league_mmr(user):
    """Set league_mmr = base mmr + best league adjustment."""
    if not user.mmr:
        user.league_mmr = None
        return

    best_adjustment = user.league_stats.aggregate(
        Max('mmr_adjustment')
    )['mmr_adjustment__max'] or 0

    user.league_mmr = user.mmr + best_adjustment
    user.save(update_fields=['league_mmr'])
```

## API Endpoints

### Leaderboard

```
GET /api/steam/leaderboard/
    ?page=1&page_size=20
    ?sort_by=league_mmr|win_rate|games_played|avg_kda
    ?order=desc|asc

    Response: {
      results: [
        {
          user_id, username, avatar,
          base_mmr, league_mmr, mmr_adjustment,
          games_played, win_rate,
          avg_kills, avg_deaths, avg_assists,
          avg_gpm, avg_xpm
        }
      ],
      count, next, previous
    }
```

### User League Stats

```
GET /api/steam/league-stats/{user_id}/
    Response: {
      user: { id, username, avatar, base_mmr, league_mmr },
      stats: {
        games_played, wins, losses, win_rate,
        avg_kills, avg_deaths, avg_assists,
        avg_gpm, avg_xpm, mmr_adjustment
      },
      recent_matches: [...]  # Optional: last 5 matches
    }

GET /api/steam/league-stats/me/
    # Same as above but for authenticated user
```

### Serializers

```python
class LeaguePlayerStatsSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username')
    avatar = serializers.CharField(source='user.avatar')
    base_mmr = serializers.IntegerField(source='user.mmr')
    league_mmr = serializers.IntegerField(source='user.league_mmr')

    class Meta:
        model = LeaguePlayerStats
        fields = [...]
```

## Frontend Components

### File Structure

```
frontend/app/
├── components/
│   └── user/
│       ├── LeagueStatsCard.tsx      # Reusable stats display
│       └── UserPopover.tsx          # Hover card with stats
├── features/
│   └── leaderboard/
│       ├── LeaderboardPage.tsx      # Rankings page
│       ├── LeaderboardTable.tsx     # Sortable table
│       └── queries.ts               # React Query hooks
├── routes/
│   └── leaderboard.tsx              # Route definition
```

### LeagueStatsCard

```tsx
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
  baseMmr: number;
  leagueMmr: number;
  compact?: boolean;  // For popover
}

// Displays:
// League MMR: 4200 (+200)
// 45 games | 58% WR
// KDA: 8.2 / 5.1 / 12.3
// GPM: 485 | XPM: 520
```

### UserPopover

```tsx
<HoverCard>
  <HoverCardTrigger>{username}</HoverCardTrigger>
  <HoverCardContent>
    <LeagueStatsCard stats={...} compact />
  </HoverCardContent>
</HoverCard>
```

### LeaderboardPage

- Sortable columns: League MMR, Win Rate, Games, KDA
- Search/filter by username
- Pagination (20 per page)

## Implementation Tasks

### Backend

1. Add Celery to requirements + Django settings
2. Create `config/celery.py` configuration
3. Add `LeaguePlayerStats` model + migration
4. Add `league_mmr` field to `CustomUser` + migration
5. Create `steam/tasks.py` with sync + calculation tasks
6. Add API endpoints + serializers
7. Update Docker Compose with celery-worker + celery-beat services

### Frontend

1. Create `LeagueStatsCard` component
2. Create `UserPopover` component with HoverCard
3. Create `LeaderboardPage` + route
4. Add league stats section to user profile
5. Add React Query hooks for new endpoints

### Configuration

- `CELERY_BROKER_URL` = Redis URL (existing)
- `LEAGUE_MMR_MIN_GAMES` = 5 (default)
- `STEAM_API_KEY` (existing)
- `LEAGUE_ID` (existing)

### Testing

- Unit tests for MMR calculation logic
- Task tests with mocked Steam API
- API endpoint tests
- Cypress E2E for leaderboard + popover
