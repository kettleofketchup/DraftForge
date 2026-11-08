---
name: inv-runner
description: Python Invoke task automation for DTX website. This skill should be used when running repo commands, backend tests via Docker, database migrations, updating invoke tasks, Docker operations, or workflow automation. Supports dev/test/prod environments with run, exec, up, down commands, and per-worktree test stack slots. References docs/development/invoke-tasks.md for complete command reference.
---

# Invoke Runner Skill

Python Invoke task automation for the DTX website project.

## Documentation References (Single Source of Truth)

For complete command reference, consult these mkdocs files:

| Document | Content |
|----------|---------|
| `docs/development/invoke-tasks.md` | Complete invoke command reference |
| `docs/development/backend-quickstart.md` | Backend development quickstart |
| `docs/development/testing.md` | Testing procedures including worktree verification |

## Running Invoke Commands

### Method 1: PATH Prefix (Recommended for Claude)

When bash hooks block `source` commands, prepend the venv bin to PATH:

```bash
PATH=".venv/bin:$PATH" inv <command>
```

For worktrees, use the full path:

```bash
PATH="/path/to/worktree/.venv/bin:$PATH" /path/to/worktree/.venv/bin/inv <command>
```

### Method 2: Poetry Run

```bash
poetry run inv <command>
```

### Method 3: Activate venv

```bash
source .venv/bin/activate
inv <command>
```

## Why PATH Matters

Invoke tasks call `python manage.py` or other Python commands. Without venv bin in PATH:
```
/bin/bash: line 1: python: command not found
```

PATH prefix ensures subprocess calls find the correct Python interpreter.

## Key Patterns

### Run vs Exec

**`run`** - One-off command in NEW container (with --rm):
```bash
inv test.run --cmd 'python manage.py test app.tests -v 2'
```

**`exec`** - Command in RUNNING container:
```bash
inv dev.exec backend 'python manage.py shell'
```

### Environment-Specific Commands

All environments (dev, test, prod) support:
```bash
inv <env>.up       # Start
inv <env>.down     # Stop and remove
inv <env>.logs     # Follow logs
inv <env>.run --cmd '<cmd>'  # One-off command
```

### Database Operations

```bash
inv db.migrate.all       # Migrations for all environments
inv db.migrate.test      # Test environment only
inv db.populate.all      # Reset and populate test DB
```

**Adding a new Django app:** `inv db.migrate.*` runs
`python manage.py makemigrations <apps>` with an explicit app list
defined at `backend/tasks.py::apps` (it does NOT auto-discover from
`INSTALLED_APPS`). When you scaffold a new app, append it there too —
otherwise `makemigrations` silently skips it. Reference impl:
the `user` app entry in
`backend/tasks.py:27`. Registering in `settings.INSTALLED_APPS`
covers `migrate` but not `makemigrations` in this project.

### Testing (Docker - Recommended)

Avoid Redis hanging issues by running tests in Docker:
```bash
inv test.run --cmd 'python manage.py test app.tests -v 2'
```

### Cypress E2E

```bash
inv test.setup           # Full setup
inv test.spec --spec navigation  # Specific spec
inv test.headless        # All tests headless
```

## Worktree Workflow

Each worktree has its own test stack slot (project `df` for slot 0, `df-sN`
otherwise). Prefer the just recipes, which target the worktree they live in:
```bash
just -f /path/to/worktree/justfile -d /path/to/worktree test::slot    # slot, project, URL
just -f /path/to/worktree/justfile -d /path/to/worktree test::down    # this slot only
just -f /path/to/worktree/justfile -d /path/to/worktree test::setup
just -f /path/to/worktree/justfile -d /path/to/worktree db::migrate::test
just -f /path/to/worktree/justfile -d /path/to/worktree db::populate::all
just -f /path/to/worktree/justfile -d /path/to/worktree test::upd
```

## Compose Helper

All compose calls go through `scripts/slots.py` (`compose_cmd(stack, ...)`, with
`stack` one of `test`, `dev`, `dev-m1`, `prod`, `release`). It always passes `-p` and
absolute `-f` paths; `docker_stop_all` (which stopped every container on the host)
was removed. For ad-hoc compose commands use `just test::compose <args>`
(`--stack dev` for `df-dev`), never raw `docker compose`. `just test::slot-reap`,
`test::slot-claim` and `test::slot-release --slot N` need no approval, but check first
that no other agent is using that slot (see the doc's pre-checks); if in doubt, don't.
See `docs/development/test-stack-slots.md`.

## Common Issues

| Issue | Solution |
|-------|----------|
| `python: command not found` | Use PATH prefix method |
| Redis connection errors | Use Docker: `inv test.run --cmd '...'` |
| Tests hang on cleanup | Use Docker: `inv test.run --cmd '...'` |
| Module not found | Ensure correct venv is activated |
| `No test-stack slot for this worktree` | Run `just test::slot` |
| `slot N now belongs to <path>` | Slot was taken by another worktree; `just test::slot` re-allocates |

## When Modifying Tasks

Update these files when changing invoke tasks:
- `docs/development/invoke-tasks.md` (primary reference)
- `docs/development/backend-quickstart.md` (if backend-related)
