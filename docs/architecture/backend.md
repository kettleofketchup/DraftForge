# Backend Architecture

## Technology Stack

- **Framework**: Django 5.x
- **API**: Django REST Framework
- **Authentication**: django-social-auth (Discord OAuth)
- **Caching**: django-cacheops with Redis
- **Background Tasks**: Celery with Redis broker
- **Database**: SQLite (development), PostgreSQL (production ready)

## Project Structure

```
backend/
├── app/                    # Main application
│   ├── migrations/         # Database migrations
│   ├── templatetags/       # Custom template tags
│   ├── admin.py           # Django admin configuration
│   ├── models.py          # Database models (CustomUser, Tournament, etc.)
│   ├── permissions.py     # DRF permissions
│   ├── serializers.py     # DRF serializers
│   └── views.py           # API views
├── backend/               # Django project settings
│   ├── settings.py        # Main settings
│   ├── urls.py            # URL routing
│   └── wsgi.py            # WSGI application
├── config/                # Celery configuration
│   ├── __init__.py        # Celery app initialization
│   └── celery.py          # Celery settings and beat schedule
├── steam/                 # Steam API integration
│   ├── migrations/        # Steam-specific migrations
│   ├── functions/         # Business logic (MMR calculation, stats)
│   ├── models.py          # SteamMatch, LeaguePlayerStats
│   ├── serializers.py     # Steam API serializers
│   ├── tasks.py           # Celery background tasks
│   ├── urls.py            # Steam API routes
│   └── views.py           # Steam API views
├── common/                # Shared utilities
│   ├── filters.py         # Query filters
│   └── pipeline.py        # Auth pipeline
└── tests/                 # Test suite
    └── urls.py            # Test authentication endpoints
```

## Data Models

### CustomUser
Extended Django user with gaming integrations:

- `discordId` - Discord user ID
- `steamId` - Steam user ID
- `avatar` - Profile avatar URL
- `nickname` - Display nickname
- `discordNickname` - Discord display name
- `guildNickname` - Server-specific nickname
- `mmr` - Base MMR from Steam profile
- `league_mmr` - Calculated league MMR (base + performance adjustment)

### Tournament
Tournament management:

- `name` - Tournament name
- `tournament_type` - Tournament format

### Team
Team organization for tournaments.

### Game
Match records with:

- `dire` - Dire team
- `radiant` - Radiant team
- Tournament association

### LeaguePlayerStats
Aggregated player statistics per league:

- `user` - Foreign key to CustomUser
- `league` - Foreign key to League
- `games_played`, `wins`, `losses` - Match counts
- `total_kills`, `total_deaths`, `total_assists` - Cumulative stats
- `total_gpm`, `total_xpm` - Cumulative economy stats
- Computed properties: `win_rate`, `avg_kda`, `avg_gpm`, `avg_xpm`

## API Endpoints

All API endpoints are prefixed with `/api/`.

### Authentication
- Discord OAuth flow handled by django-social-auth
- Test endpoints in `backend/tests/urls.py` for E2E testing

### REST Patterns
- Standard CRUD operations via DRF ViewSets
- Permission classes defined in `app/permissions.py`

## Caching Strategy

Uses django-cacheops for automatic query caching:

```python
# Disable cache for management commands
DISABLE_CACHE=true python manage.py <command>
```

## Steam API Integration

- All Steam API calls go through the backend
- Results cached to respect rate limits
- Frontend never calls Steam API directly

Use cases:
- Search for Steam ID from username
- Fetch games involving DTX guild users
- Live game statistics
- League match sync and stats aggregation

## Background Tasks (Celery)

Celery handles background task processing with Redis as the message broker.

### Configuration

```python
# backend/config/celery.py
CELERY_BROKER_URL = "redis://redis:6379/1"
CELERY_RESULT_BACKEND = "redis://redis:6379/1"
```

### Scheduled Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `sync_league_matches_task` | Every 60s | Fetch new league matches from Steam API |

### Task Functions

- **`sync_league_matches_task`**: Fetches recent league matches, processes player stats, updates `LeaguePlayerStats` models
- **`update_all_league_stats_task`**: Recalculates all player statistics and league MMR

### League MMR Calculation

League MMR = Base MMR + Performance Adjustment

The performance adjustment ranges from -500 to +500 based on:
- Win rate vs league average (40% weight)
- KDA vs league average (35% weight)
- GPM vs league average (25% weight)

Players must have minimum 5 games to receive a league MMR.
