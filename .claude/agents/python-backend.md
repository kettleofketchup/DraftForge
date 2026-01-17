---
skills:
  - inv-runner
  - django-redis-caching
---

# Python Backend Agent

Expert agent for Django/Python backend development in the DTX website project.

## Quick Reference

See [docs/development/backend-quickstart.md](../../../docs/development/backend-quickstart.md) for complete commands.

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

Use the `inv-runner` skill for all invoke commands. Key patterns:

```bash
# Method 1: PATH prefix (recommended for Claude)
PATH=".venv/bin:$PATH" inv <command>

# Method 2: Activate venv
source .venv/bin/activate
inv <command>
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

Test endpoints available in `backend/tests/urls.py` for user/staff/admin login.

**Docker (recommended)** - avoids Redis hanging issues:
```bash
inv test.run --cmd 'python manage.py test app.tests -v 2'
```

**Local** - may hang on cleanup:
```bash
cd backend && DISABLE_CACHE=true python manage.py test app.tests -v 2
```

### Database Operations

Use invoke tasks for database operations (see `inv-runner` skill):

```bash
# Migrations (all environments)
inv db.migrate.all

# Specific environment migrations
inv db.migrate.dev    # Development
inv db.migrate.test   # Test
inv db.migrate.prod   # Production

# Create migrations (requires venv)
cd backend && DISABLE_CACHE=true python manage.py makemigrations app

# Populate test data
inv db.populate.all
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
