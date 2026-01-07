---
---

# Python Backend Agent

Expert agent for Django/Python backend development in the DTX website project.

## Project Context

**Goal**: Website that helps manage DTX, a Dota2 gaming organization.

**Stack**:
- Django + Django REST Framework
- django-social-auth (Discord OAuth)
- Redis for caching (django-cacheops)
- Poetry for dependency management
- SQLite database

**Location**: `./backend/`

## Environment Setup

```bash
# Activate virtual environment
source .venv/bin/activate

# If Redis is unavailable, disable caching for management commands
DISABLE_CACHE=true python manage.py <command>
```

## Key Directories

- `backend/app/` - Main application (models, views, serializers, permissions)
- `backend/app/migrations/` - Database migrations
- `backend/app/templatetags/` - Custom template tags
- `backend/common/` - Shared utilities (filters, pipeline)
- `backend/tests/` - Test suite including test login endpoints

## Models Overview

Based on migrations, the project has these key models:
- `CustomUser` - Extended user with Discord integration (avatar, discordId, steamId, nickname, discordNickname, guildNickname)
- `Tournament` - Tournament management with type field
- `Team` - Team associations
- `Game` - Game records with dire/radiant teams

## Development Patterns

### API Endpoints
- Use Django REST Framework viewsets and serializers
- Apply proper permissions from `backend/app/permissions.py`
- Follow RESTful conventions

### Testing
- Test endpoints available in `backend/tests/urls.py` for user/staff/admin login
- Tests use real database (no mocking)
- Run with: `python manage.py test`

### Database Operations
```bash
python manage.py makemigrations app
python manage.py migrate app
python manage.py createsuperuser
python manage.py runserver
```

### Adding Dependencies
```bash
poetry add <module_name>
```

## Redis Caching

**IMPORTANT**: All cached data must be properly invalidated when related models change. See the `django-redis-caching` skill for complete patterns.

### Quick Reference

```python
from cacheops import cached_as, invalidate_obj, invalidate_model

# View caching
@cached_as(Model1, Model2, extra=cache_key, timeout=60 * 60)
def get_data():
    return queryset.values()

# After mutations, invalidate related caches
invalidate_obj(instance)       # Specific instance
invalidate_model(RelatedModel) # Entire model
```

### Key Invalidation Rules

- DraftRound changes → invalidate Tournament, Draft, Team
- Team changes → invalidate Tournament (if scoped)
- Game changes → invalidate Tournament, Team

## Steam API Integration

- Python handles all Steam API calls
- Results cached in Django cache for rate limiting
- Frontend only calls Django endpoints (never Steam API directly)

Use cases:
- Search for steamid from username
- Search for games involving DTX Dota guild users
- Live stats of active Dota games

## Coding Standards

- Use type hints where practical
- Follow PEP 8 style guidelines
- Use Django ORM patterns consistently
- Handle errors with try/catch and log with contextual information
- Validate input at API boundaries
