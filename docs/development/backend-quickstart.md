# Backend Quickstart

Quick reference for Django backend development in the DraftForge project.

## Prerequisites

Always activate the virtual environment or use invoke commands:

```bash
source .venv/bin/activate

# Or use invoke directly with PATH
PATH=".venv/bin:$PATH" inv <command>
```

## Database Operations

### Migrations

Run migrations using invoke (recommended):

```bash
# All environments
inv db.migrate.all

# Specific environments
inv db.migrate.dev     # Development (default)
inv db.migrate.test    # Test environment
inv db.migrate.prod    # Production
```

To create new migrations:

```bash
cd backend
DISABLE_CACHE=true python manage.py makemigrations app
```

### Test Data Population

```bash
# Full test database reset and population
inv db.populate.all

# Individual population commands
inv db.populate.users          # Discord users
inv db.populate.tournaments    # Random tournaments
inv db.populate.steam-mock     # Mock Steam matches
inv db.populate.test-tournaments  # Cypress test scenarios
```

## Running the Server

### Development (Docker)

```bash
inv dev.debug   # Interactive mode with logs
inv dev.up      # Detached mode with sync
```

### Direct (Local)

```bash
cd backend
DISABLE_CACHE=true python manage.py runserver
```

Note: Use `DISABLE_CACHE=true` when Redis is unavailable.

## Running Tests

### Backend Tests (Docker - Recommended)

```bash
# All tests
inv test.run --cmd 'python manage.py test app.tests -v 2'

# Specific module
inv test.run --cmd 'python manage.py test app.tests.test_shuffle_draft -v 2'

# Specific test class
inv test.run --cmd 'python manage.py test app.tests.test_shuffle_draft.GetTeamTotalMmrTest -v 2'
```

### Backend Tests (Local)

May hang on cleanup due to Redis/cacheops:

```bash
cd backend
DISABLE_CACHE=true python manage.py test app.tests -v 2
```

## Creating New Endpoints

1. **Add serializer** in `backend/app/serializers.py`
2. **Add viewset** in `backend/app/views.py`
3. **Add permissions** from `backend/app/permissions.py`
4. **Register route** in `backend/app/urls.py`

## Common Commands

```bash
# Django shell
inv dev.exec backend 'python manage.py shell'

# Create superuser
inv dev.exec backend 'python manage.py createsuperuser'

# Check for issues
cd backend
DISABLE_CACHE=true python manage.py check
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Redis connection errors | Use `DISABLE_CACHE=true` prefix |
| Migrations out of sync | Run `inv db.migrate.all` |
| Module not found | Activate venv: `source .venv/bin/activate` |
| Tests hang on cleanup | Use Docker: `inv test.run --cmd '...'` |
