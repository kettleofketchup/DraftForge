# Just Command Runner Migration

**Date:** 2026-02-01
**Status:** Design Complete
**Goal:** Migrate from invoke to just as the primary command runner interface

## Problem Statement

1. **Venv activation friction** - Every `inv` command requires `source .venv/bin/activate` first, especially painful in worktrees
2. **Scattered one-offs** - Agents run `npm install`, `npx playwright`, `python manage.py` directly instead of through a unified interface
3. **Discovery** - Hard to remember commands across invoke namespaces
4. **Agent failures** - Claude hooks reminding agents to use invoke causes failures when venv isn't activated

## Solution

Use `just` as the entry point that:
- Handles venv activation internally
- Wraps existing invoke tasks (incremental migration)
- Provides better discoverability via `just --list`
- Works without any setup (standalone binary)

## Directory Structure

```
website/
  dev                      # Bootstrap script (installs just, runs `just dev`)
  justfile                 # Root imports & modules
  just/
    _common.just           # Shared venv/path helpers
    dev.just               # Imported (no namespace) - bootstrap recipes
    docker.just            # docker::*
    demo.just              # demo::*
    docs.just              # docs::*
    update.just            # update::*
    version.just           # version::*
    prod.just              # prod::*
    discord.just           # discord::*
    npm.just               # npm::* (new - wraps npm commands)
    py.just                # py::* (new - wraps python/manage.py)
    test/
      mod.just             # test::*
      pw.just              # test::pw::*
      backend.just         # test::backend::*
      cicd.just            # test::cicd::*
      demo.just            # test::demo::*
    db/
      mod.just             # db::*
      migrate.just         # db::migrate::*
      populate.just        # db::populate::*
```

## Module Mapping

| Invoke Namespace | Just Module | File Path |
|------------------|-------------|-----------|
| `dev.*` | `dev::*` | `just/dev.just` |
| `test.*` | `test::*` | `just/test/mod.just` |
| `test.playwright.*` | `test::pw::*` | `just/test/pw.just` |
| `test.backend.*` | `test::backend::*` | `just/test/backend.just` |
| `test.cicd.*` | `test::cicd::*` | `just/test/cicd.just` |
| `test.demo.*` | `test::demo::*` | `just/test/demo.just` |
| `db.*` | `db::*` | `just/db/mod.just` |
| `db.migrate.*` | `db::migrate::*` | `just/db/migrate.just` |
| `db.populate.*` | `db::populate::*` | `just/db/populate.just` |
| `docker.*` | `docker::*` | `just/docker.just` |
| `demo.*` | `demo::*` | `just/demo.just` |
| `docs.*` | `docs::*` | `just/docs.just` |
| `update.*` | `update::*` | `just/update.just` |
| `version.*` | `version::*` | `just/version.just` |
| `prod.*` | `prod::*` | `just/prod.just` |
| `discord.*` | `discord::*` | `just/discord.just` |
| *(new)* | `npm::*` | `just/npm.just` |
| *(new)* | `py::*` | `just/py.just` |

## Implementation Details

### Root Justfile

```just
# justfile (root)
set quiet
set dotenv-load

# Import dev.just (merged into root namespace for ./dev bootstrap)
import 'just/dev.just'

# Modules (namespaced with ::)
mod docker 'just/docker.just'
mod demo 'just/demo.just'
mod docs 'just/docs.just'
mod update 'just/update.just'
mod version 'just/version.just'
mod prod 'just/prod.just'
mod discord 'just/discord.just'
mod npm 'just/npm.just'
mod py 'just/py.just'
mod test 'just/test/mod.just'
mod db 'just/db/mod.just'

default:
    @just --list
```

### Common Module (`just/_common.just`)

```just
# Auto-detect paths relative to justfile (works in worktrees)
root := justfile_directory()
venv := root / ".venv/bin/activate"
backend := root / "backend"
frontend := root / "frontend"

# Helper to run commands with venv activated
[private]
[no-cd]
venv-run *args:
    @bash -c 'source {{venv}} && {{args}}'

# Helper to run invoke commands (main wrapper pattern)
[private]
[no-cd]
inv *args:
    @bash -c 'source {{venv}} && cd {{root}} && inv {{args}}'
```

### Bootstrap Script (`dev`)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Bootstrap script: installs just if needed, then runs `just dev`

install_just() {
    echo "Installing just..."

    if command -v cargo &> /dev/null; then
        cargo install just
    elif command -v brew &> /dev/null; then
        brew install just
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin
        export PATH="$HOME/.local/bin:$PATH"
    else
        echo "Error: Could not install just. Please install manually: https://github.com/casey/just#installation"
        exit 1
    fi
}

if ! command -v just &> /dev/null; then
    install_just
fi

just dev "$@"
```

### Dev Module (`just/dev.just`)

Imported (no namespace) for bootstrap recipes:

```just
# Development bootstrap recipes (imported, no namespace)
import '_common.just'

# Bootstrap: install deps, run migrations, start dev environment
dev *args:
    #!/usr/bin/env bash
    set -euo pipefail

    # Install Python deps if needed
    if [[ ! -d "{{root}}/.venv" ]]; then
        python -m venv {{root}}/.venv
        source {{venv}}
        pip install poetry
        poetry install
    else
        source {{venv}}
    fi

    # Install frontend deps if needed
    if [[ ! -d "{{frontend}}/node_modules" ]]; then
        cd {{frontend}} && npm install
    fi

    # Run migrations and start
    inv dev.debug {{args}}

# Start dev environment with hot reload
[group('dev')]
debug:
    {{inv}} dev.debug

# Start dev in detached mode
[group('dev')]
upd:
    {{inv}} dev.upd

# Stop dev environment
[group('dev')]
down:
    {{inv}} dev.down

# View dev logs
[group('dev')]
logs:
    {{inv}} dev.logs

# Full sync from production
[group('dev')]
up *args:
    {{inv}} dev.up {{args}}
```

### Test Module (`just/test/mod.just`)

```just
mod test

import '../_common.just'
import 'pw.just'
import 'backend.just'
import 'cicd.just'
import 'demo.just'

# Start test environment
[group('test')]
up:
    {{inv}} test.up

# Start test detached
[group('test')]
upd:
    {{inv}} test.upd

# Stop test environment
[group('test')]
down:
    {{inv}} test.down

# View test logs
[group('test')]
logs:
    {{inv}} test.logs

# Setup test environment (build, populate, start)
[group('test')]
setup:
    {{inv}} test.setup
```

### Playwright Module (`just/test/pw.just`)

```just
mod pw

# Run all tests headless
[group('test::pw')]
headless *args:
    {{inv}} test.playwright.headless {{ if args != "" { "--args='" + args + "'" } else { "" } }}

# Run tests headed (visible browser)
[group('test::pw')]
headed *args:
    {{inv}} test.playwright.headed {{ if args != "" { "--args='" + args + "'" } else { "" } }}

# Open Playwright UI
[group('test::pw')]
ui:
    {{inv}} test.playwright.ui

# Run specific pattern
[group('test::pw')]
spec pattern:
    {{inv}} test.playwright.spec --spec "{{pattern}}"

# Install browsers
[group('test::pw')]
install:
    {{inv}} test.playwright.install

# Show HTML report
[group('test::pw')]
report:
    {{inv}} test.playwright.report
```

### NPM Module (`just/npm.just`)

New module for frontend npm commands:

```just
mod npm

import '_common.just'

# Install dependencies
[group('npm')]
[no-cd]
install:
    cd {{frontend}} && npm install

# Run dev server
[group('npm')]
[no-cd]
dev:
    cd {{frontend}} && npm run dev

# Run build
[group('npm')]
[no-cd]
build:
    cd {{frontend}} && npm run build

# Run any npm command
[group('npm')]
[no-cd]
run *args:
    cd {{frontend}} && npm {{args}}
```

### Python Module (`just/py.just`)

New module for Django/Python commands:

```just
mod py

import '_common.just'

# Run manage.py command
[group('py')]
[no-cd]
manage *args:
    bash -c 'source {{venv}} && cd {{backend}} && python manage.py {{args}}'

# Run migrations
[group('py')]
[no-cd]
migrate:
    bash -c 'source {{venv}} && cd {{backend}} && DISABLE_CACHE=true python manage.py migrate'

# Make migrations
[group('py')]
[no-cd]
makemigrations *args:
    bash -c 'source {{venv}} && cd {{backend}} && python manage.py makemigrations {{args}}'

# Django shell
[group('py')]
[no-cd]
shell:
    bash -c 'source {{venv}} && cd {{backend}} && DISABLE_CACHE=true python manage.py shell'

# Run any python command in backend
[group('py')]
[no-cd]
run *args:
    bash -c 'source {{venv}} && cd {{backend}} && python {{args}}'
```

### DB Module (`just/db/mod.just`)

```just
mod db

import '../_common.just'
import 'migrate.just'
import 'populate.just'

# Run dev migrations (default)
[group('db')]
migrate:
    {{inv}} db.migrate

# Make migrations
[group('db')]
makemigrations *args:
    {{inv}} db.makemigrations {{args}}
```

### DB Populate Module (`just/db/populate.just`)

```just
mod populate

# Populate all test data
[group('db::populate')]
all:
    {{inv}} db.populate.all

# Populate users
[group('db::populate')]
users:
    {{inv}} db.populate.users

# Populate tournaments
[group('db::populate')]
tournaments:
    {{inv}} db.populate.tournaments

# Populate organizations
[group('db::populate')]
organizations:
    {{inv}} db.populate.organizations
```

## Claude Hooks Configuration

### Hook Script (`.claude/hooks/prompt-submit.sh`)

```bash
#!/usr/bin/env bash
# Remind Claude agents to use just commands

cat << 'EOF'
<system-reminder>
IMPORTANT: This project uses `just` as the command runner.

DO NOT run these directly:
- `inv ...` or `invoke ...` (requires venv activation)
- `npm ...` in frontend/
- `python manage.py ...` in backend/
- `npx playwright ...`

INSTEAD use just recipes:
- `just dev::debug` - start dev environment
- `just test::up` - start test environment
- `just test::pw::headless` - run playwright tests
- `just test::pw::ui` - playwright UI mode
- `just npm::install` - install frontend deps
- `just py::manage <cmd>` - run manage.py commands
- `just db::migrate` - run migrations
- `just db::populate::all` - populate test data

Run `just --list --list-submodules` to see all available commands.
</system-reminder>
EOF
```

### Settings (`.claude/settings.json`)

```json
{
  "hooks": {
    "prompt-submit": [
      {
        "command": ".claude/hooks/prompt-submit.sh"
      }
    ]
  }
}
```

## Usage Examples

```bash
# Bootstrap (installs just if needed, sets up environment)
./dev

# Development
just dev::debug          # Start dev environment
just dev::up             # Start with production sync
just dev::down           # Stop dev environment

# Testing
just test::up            # Start test environment
just test::pw::headless  # Run all Playwright tests
just test::pw::ui        # Open Playwright UI
just test::pw::spec herodraft  # Run specific tests

# Database
just db::migrate         # Run migrations
just db::populate::all   # Populate test data

# Frontend (new)
just npm::install        # Install frontend deps
just npm::run build      # Run npm build

# Backend (new)
just py::manage shell    # Django shell
just py::migrate         # Run migrations with cache disabled

# Discovery
just --list              # Show all commands
just --list --list-submodules  # Show nested modules
```

## Implementation Plan

1. Create worktree for implementation
2. Copy bootstrap script from just skill assets
3. Create `just/` directory structure
4. Implement `_common.just` with venv helpers
5. Implement `dev.just` (imported for bootstrap)
6. Implement remaining modules wrapping invoke
7. Add new `npm.just` and `py.just` convenience modules
8. Configure Claude hooks
9. Update CLAUDE.md with new commands
10. Test in worktree environment
