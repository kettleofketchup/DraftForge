# Backend Architecture

## Technology Stack

- **Framework**: Django 5.x
- **API**: Django REST Framework
- **Authentication**: django-social-auth (Discord OAuth)
- **Caching**: django-cacheops with Redis
- **Database**: SQLite (development), PostgreSQL (production ready)

## Project Structure

```
backend/
├── app/                    # Main application
│   ├── migrations/         # Database migrations
│   ├── templatetags/       # Custom template tags
│   ├── admin.py           # Django admin configuration
│   ├── models.py          # Database models
│   ├── permissions.py     # DRF permissions
│   ├── serializers.py     # DRF serializers
│   └── views.py           # API views
├── backend/               # Django project settings
│   ├── settings.py        # Main settings
│   ├── urls.py            # URL routing
│   └── wsgi.py            # WSGI application
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
