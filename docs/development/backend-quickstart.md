# Backend Quickstart

Quick reference for Django backend development in the DraftForge project.

## Prerequisites

Just commands automatically activate the virtual environment. No manual activation needed.

## Database Operations

### Migrations

Run migrations using just (recommended):

```bash
# All environments
just db::migrate::all

# Specific environments
just db::migrate::dev     # Development (default)
just db::migrate::test    # Test environment
just db::migrate::prod    # Production
```

To create new migrations:

```bash
just db::makemigrations app
```

### Test Data Population

```bash
# Full test database reset and population
just db::populate::all
```

## Running the Server

### Development (Docker)

```bash
just dev::debug   # Interactive mode with logs
just dev::up      # Detached mode
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
just test::run 'python manage.py test app.tests -v 2'

# Specific module
just test::run 'python manage.py test app.tests.test_shuffle_draft -v 2'

# Specific test class
just test::run 'python manage.py test app.tests.test_shuffle_draft.GetTeamTotalMmrTest -v 2'
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
just py::shell

# Create superuser
just dev::exec backend 'python manage.py createsuperuser'

# Check for issues
just dev::exec backend 'python manage.py check'
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Redis connection errors | Use `DISABLE_CACHE=true` prefix |
| Migrations out of sync | Run `just db::migrate::all` |
| Module not found | Run `./dev` to bootstrap the environment |
| Tests hang on cleanup | Use Docker: `just test::run '...'` |
