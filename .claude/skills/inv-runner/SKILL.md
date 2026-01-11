---
name: inv-runner
description: Python Invoke task automation for DTX website. Use when running repo commands, backend tests via Docker, updating invoke tasks, Docker operations, or workflow automation. Supports dev/test/prod environments with run, exec, up, down commands.
---

# Invoke Runner Skill

Python Invoke task automation for the DTX website project.

## Prerequisites

**CRITICAL**: Always cd into the project/worktree directory first, then use `poetry run inv`.

```bash
cd /path/to/project  # or worktree path
poetry run inv --list
```

Alternative (activate venv):
```bash
source .venv/bin/activate
inv --list
```

## Quick Reference

| Namespace | Purpose |
|-----------|---------|
| `dev.*` | Development environment |
| `test.*` | Test environment |
| `prod.*` | Production environment |
| `docker.*` | Image build/push/pull |
| `db.*` | Database operations |
| `update.*` | Dependency updates |
| `version.*` | Version management |
| `docs.*` | Documentation |

See [commands.md](references/commands.md) for complete command reference.

## Running Backend Tests (Docker)

**IMPORTANT**: Use Docker to avoid Redis/cacheops hanging issues:

```bash
# Run all tests
inv test.run --cmd 'python manage.py test app.tests -v 2'

# Run specific module
inv test.run --cmd 'python manage.py test app.tests.test_shuffle_draft -v 2'

# Run specific test class
inv test.run --cmd 'python manage.py test app.tests.test_shuffle_draft.GetTeamTotalMmrTest -v 2'
```

Local testing (may hang on cleanup):
```bash
DISABLE_CACHE=true python manage.py test app.tests -v 2
```

## Run vs Exec Commands

**`run`** - One-off command in NEW container (with --rm):
```bash
inv test.run --cmd 'python manage.py shell'
inv dev.run --service frontend --cmd 'npm run build'
```

**`exec`** - Command in RUNNING container:
```bash
inv dev.exec backend 'python manage.py shell'
```

## Common Workflows

### Start Development
```bash
cd /path/to/project
poetry run inv dev.debug
```

### Run Backend Tests
```bash
cd /path/to/project
poetry run inv test.run --cmd 'python manage.py test app.tests -v 2'
```

### E2E Testing (Cypress)
```bash
cd /path/to/project
poetry run inv test.setup
poetry run inv test.open  # or inv test.headless
```

### Release New Version
```bash
cd /path/to/project
poetry run inv version.set 1.2.3
poetry run inv docker.all.build
poetry run inv docker.all.push
poetry run inv version.tag
```

### Database Operations
```bash
poetry run inv db.migrate           # Run migrations (dev, default)
poetry run inv db.migrate.all       # Run migrations for all environments
poetry run inv db.migrate.test      # Run migrations for test
poetry run inv db.populate.all      # Reset and populate test DB
```

## Environment Management

Each environment (dev, test, prod) supports:

```bash
poetry run inv <env>.up      # Start
poetry run inv <env>.down    # Stop and remove
poetry run inv <env>.logs    # Follow logs
poetry run inv <env>.run --cmd '<cmd>'  # Run one-off command
```

## Notes

- Version pulled from `pyproject.toml`
- Images pushed to `ghcr.io/kettleofketchup/dota_tournament/`
- Migrations run with `DISABLE_CACHE=true` to avoid Redis dependency
- Apps with migrations: `steam`, `app`, `bracket`, `discordbot`

## When Modifying Tasks

Update documentation when changing invoke tasks:
- `docs/development/invoke-tasks.md`
- `docs/getting-started/quick-start.md`
- `.claude/CLAUDE.md`
