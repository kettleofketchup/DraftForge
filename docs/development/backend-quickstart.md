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

### Migration conflicts (`max_migration.txt`)

Every app with migrations has `migrations/max_migration.txt` holding the name of its
latest migration ([django-linear-migrations](https://github.com/adamchainz/django-linear-migrations)).
`makemigrations` updates it for you; commit it with the migration. When your branch and
`main` both add a migration to the same app, git conflicts on that file instead of Django
raising "Conflicting migrations" after the merge:

```text
CONFLICT (content): Merge conflict in backend/events/migrations/max_migration.txt

<<<<<<< HEAD
0036_add_signup_note
=======
0036_event_capacity
>>>>>>> origin/main
```

To fix it (example app `events`, last common migration `0035`):

```bash
# 1. Before merging, unapply your branch's migration from each local DB that has it
just db::manage dev migrate events 0035
just db::manage test migrate events 0035

# 2. Merge (or rebase onto) main; git stops on max_migration.txt
git merge origin/main

# 3. Renumber your migration after main's: renames it to 0037_..., points its
#    dependency at main's 0036 and rewrites max_migration.txt
just db::rebase-migration events

# 4. Stage the rename and the resolved file, finish the merge
git add backend/events/migrations
git merge --continue          # or: git rebase --continue

# 5. Verify, then migrate
just db::manage dev makemigrations --check --dry-run
just db::migrate::dev
```

`rebase_migration` refuses to run while your migration is still applied (step 1), and it
only moves one migration: if your branch adds several to the same app, squash them first or
renumber by hand. The system check (`dlm.E00x`) fails `makemigrations --check`,
`manage.py check` and `manage.py test` when a `max_migration.txt` is stale; after editing
migrations by hand, `just db::manage dev create_max_migration_files --recreate` rewrites them.

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
just test::run 'python manage.py test draft.tests.test_team_shuffle -v 2'

# Specific test class
just test::run 'python manage.py test draft.tests.test_team_shuffle.GetTeamTotalMmrTest -v 2'
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
