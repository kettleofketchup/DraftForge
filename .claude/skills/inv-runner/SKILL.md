---
name: inv-runner
description: Python Invoke task automation for DTX website. Use when running repo commands, backend tests via Docker, updating invoke tasks, Docker operations, or workflow automation. Supports dev/test/prod environments with run, exec, up, down commands.
---

# Invoke Runner Skill

Python Invoke task automation for the DTX website project.

## Prerequisites

**CRITICAL**: Always source virtual environment before invoke commands.

```bash
# Main repo
source .venv/bin/activate

# Git worktrees - use main repo venv
source /home/kettle/git_repos/website/.venv/bin/activate
```

Run `inv --list` to see all available tasks.

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
source .venv/bin/activate
inv dev.debug
```

### Run Backend Tests
```bash
source .venv/bin/activate
inv test.run --cmd 'python manage.py test app.tests -v 2'
```

### E2E Testing (Cypress)
```bash
source .venv/bin/activate
inv test.setup
inv test.open  # or inv test.headless
```

### Release New Version
```bash
source .venv/bin/activate
inv version.set 1.2.3
inv docker.all.build
inv docker.all.push
inv version.tag
```

### Database Operations
```bash
inv db.migrate           # Run migrations
inv db.populate.all      # Reset and populate test DB
```

## Environment Management

Each environment (dev, test, prod) supports:

```bash
inv <env>.up      # Start
inv <env>.down    # Stop and remove
inv <env>.logs    # Follow logs
inv <env>.run --cmd '<cmd>'  # Run one-off command
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
