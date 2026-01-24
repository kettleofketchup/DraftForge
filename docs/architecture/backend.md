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

### Draft
Draft configuration for tournaments:

- `tournament` - Associated tournament
- `draft_style` - Style: `snake`, `normal`, or `shuffle`

### DraftRound
Individual picks in a draft:

- `captain` - Captain making the pick
- `choice` - Player selected
- `pick_number` - Sequential pick number
- `was_tie` - Whether tie-breaking occurred (shuffle only)
- `tie_roll_data` - JSON with tie resolution details

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

### Scheduled Tasks (Celery Beat)

| Task | Schedule | Description |
|------|----------|-------------|
| `sync_league_matches_task` | Every 60s | Fetch new league matches from Steam API |
| `check_scheduled_events` | Every 60s | Check Discord scheduled events |
| `refresh_discord_avatars` | Every 5 min | Batch refresh Discord avatars (50 users) |
| `refresh_all_discord_data` | Daily at 4 AM | Full Discord data refresh for all users |

### Task Functions

**Steam Tasks:**
- **`sync_league_matches_task`**: Fetches recent league matches, processes player stats, updates `LeaguePlayerStats` models
- **`update_all_league_stats_task`**: Recalculates all player statistics and league MMR

**Discord Tasks:**
- **`refresh_discord_avatars`**: Batch checks avatar URLs for validity, updates stale avatars
- **`refresh_single_user_avatar`**: On-demand single user avatar refresh (triggered on login)
- **`refresh_all_discord_data`**: Comprehensive refresh iterating all users with Discord IDs

### League MMR Calculation

League MMR = Base MMR + Performance Adjustment

The performance adjustment ranges from -500 to +500 based on:
- Win rate vs league average (40% weight)
- KDA vs league average (35% weight)
- GPM vs league average (25% weight)

Players must have minimum 5 games to receive a league MMR.

## Redis Distributed Locking

Redis is used for distributed coordination beyond caching, ensuring consistency across multiple Django instances.

### Connection Tracking

WebSocket connection counts are tracked in Redis to enable intelligent resource management:

```python
# Redis key pattern
CONN_COUNT_KEY = "herodraft:connections:{draft_id}"

# Increment on WebSocket connect
count = redis_client.incr(key)
redis_client.expire(key, 300)  # Auto-cleanup after 5 min inactivity

# Decrement on disconnect
count = redis_client.decr(key)
if count <= 0:
    redis_client.delete(key)
```

### Distributed Locks

Prevent duplicate background tasks across multiple server instances:

```python
LOCK_KEY = "herodraft:tick_lock:{draft_id}"
LOCK_TIMEOUT = 10  # seconds

# Acquire lock (atomic, non-blocking)
acquired = redis_client.set(lock_key, "locked", nx=True, ex=LOCK_TIMEOUT)
if not acquired:
    return  # Another instance owns this task

# Renew lock while task runs
redis_client.expire(lock_key, LOCK_TIMEOUT)

# Release lock when done
redis_client.delete(lock_key)
```

This pattern ensures only one tick broadcaster runs per draft, even with multiple Django/Daphne instances.

## Real-Time WebSocket Broadcasting

Django Channels provides WebSocket support for real-time features via Daphne ASGI server.

### URL Routing Convention

**IMPORTANT**: Daphne handles both HTTP and WebSocket on the same URL paths. Do NOT create separate `/ws/` prefixed routes.

| ❌ Wrong | ✅ Correct |
|----------|------------|
| `/ws/herodraft/<id>/` | `/api/herodraft/<id>/` |
| `/ws/draft/<id>/` | `/api/draft/<id>/` |

The `ProtocolTypeRouter` in `backend/asgi.py` automatically routes connections based on protocol:
- HTTP requests → Django URL router (`backend/urls.py`)
- WebSocket connections → Channels URL router (`app/routing.py`)

```python
# backend/app/routing.py
websocket_urlpatterns = [
    path("api/draft/<int:draft_id>/", DraftConsumer.as_asgi()),
    path("api/tournament/<int:tournament_id>/", TournamentConsumer.as_asgi()),
    path("api/herodraft/<int:draft_id>/", HeroDraftConsumer.as_asgi()),
]
```

This works because nginx proxies `/api/` to the backend, and Daphne distinguishes HTTP from WebSocket by the `Upgrade: websocket` header.

### HeroDraft Tick Broadcaster

The hero draft system uses a hybrid approach:

1. **Threading + asyncio** for 1-second tick broadcasts (low latency)
2. **Redis distributed locking** to prevent duplicate broadcasters
3. **Connection tracking** to auto-stop when no clients connected

```
┌─────────────────────┐
│  WebSocket Connect  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Increment Redis     │
│ Connection Count    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Try Acquire Redis   │──── Already held ──► Return (another instance owns it)
│ Distributed Lock    │
└──────────┬──────────┘
           │ Acquired
           ▼
┌─────────────────────┐
│ Start Background    │
│ Thread with Event   │
│ Loop                │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│           Tick Loop (1s interval)       │
│  ┌─────────────────────────────────┐    │
│  │ Check: connections > 0?         │    │
│  │ Check: draft.state == drafting? │    │
│  │ Broadcast tick to channel group │    │
│  │ Check timeout & auto-pick       │    │
│  │ Renew Redis lock                │    │
│  └─────────────────────────────────┘    │
└──────────┬──────────────────────────────┘
           │ Stop conditions met
           ▼
┌─────────────────────┐
│ Release Redis Lock  │
│ Cleanup Thread      │
└─────────────────────┘
```

### Channel Groups

WebSocket consumers join channel groups for targeted broadcasting:

| Group Pattern | Description |
|---------------|-------------|
| `draft_{id}` | Player draft events (snake/shuffle) |
| `tournament_{id}` | Tournament-wide events |
| `herodraft_{id}` | Hero draft tick updates |

### Tick Data Structure

```python
{
    "type": "herodraft.tick",
    "current_round": 1,
    "active_team_id": 42,
    "grace_time_remaining_ms": 15000,
    "team_a_id": 42,
    "team_a_reserve_ms": 120000,
    "team_b_id": 43,
    "team_b_reserve_ms": 120000,
    "draft_state": "drafting"
}
```
