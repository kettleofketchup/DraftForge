# DraftForge - Claude Code Configuration

DraftForge is a platform for managing Dota 2 tournaments, teams, and competitive gaming.

## First Things First

This project uses **just** as the task runner, which automatically handles venv activation.

```bash
# First-time setup (installs just, creates venv, installs deps)
./dev

# All commands use just with :: namespace syntax
just dev::debug        # Start dev environment
just test::pw::ui      # Open Playwright UI
just db::migrate::all  # Run all migrations
```

**No manual venv activation needed** - just commands auto-activate the correct venv (works in worktrees too).

Run `just --list --list-submodules` to see all available commands.

## Project Structure

```
website/
  backend/          # Django REST API
  frontend/         # React + TypeScript + Vite
  docker/           # Docker Compose configurations
  nginx/            # Nginx reverse proxy config
  scripts/          # Utility scripts
```

## Tech Stack

**Backend**: Django, Django REST Framework, Django Channels (Daphne), django-social-auth (Discord OAuth), Redis (cacheops)
**Frontend**: React, TypeScript, Vite, React Router, TailwindCSS, Shadcn UI, Zustand, Zod
**Infrastructure**: Docker, Nginx, GitHub Container Registry

## WebSocket Architecture

**IMPORTANT**: This project uses Daphne (Django Channels) which handles both HTTP and WebSocket connections on the same URL paths.

- **DO NOT** create separate `/ws/` URL paths for WebSocket endpoints
- WebSocket routes should use the same `/api/` prefix as HTTP endpoints
- Daphne's `ProtocolTypeRouter` automatically routes based on connection protocol
- Example: `/api/herodraft/<id>/` handles both HTTP GET requests AND WebSocket connections

WebSocket routing is defined in `backend/app/routing.py`:
```python
websocket_urlpatterns = [
    path("api/draft/<int:draft_id>/", DraftConsumer.as_asgi()),
    path("api/tournament/<int:tournament_id>/", TournamentConsumer.as_asgi()),
    path("api/herodraft/<int:draft_id>/", HeroDraftConsumer.as_asgi()),
]
```

Frontend connects via:
```typescript
const wsUrl = `${protocol}//${host}/api/herodraft/${draftId}/`;
const ws = new WebSocket(wsUrl);
```

## Quick Start

### First-Time Setup
```bash
./dev  # Installs just, creates venv, installs deps, starts dev environment
```

### Development (Docker)
```bash
just dev::debug
```

### Production
```bash
just dev::local-prod
```

### Testing
```bash
just test::up
```

### Full Test Setup (with Playwright)
```bash
just test::setup
just test::pw::headless  # or just test::pw::headed
```

## Docker Compose Architecture

### Services

| Service | Description | Port |
|---------|-------------|------|
| `frontend` | React dev server | 3000 (internal) |
| `backend` | Django API | 8000 (internal) |
| `nginx` | Reverse proxy | 80, 443 |
| `redis` | Cache layer | 6379 (internal) |

### Environment Files
- `docker/.env.dev` - Development settings
- `docker/.env.test` - Test settings
- `docker/.env.prod` - Production settings
- `docker/.env.release` - Release settings

### Compose Configurations

**docker-compose.debug.yaml** (Development)
- Mounts local source code for hot reloading
- Frontend at `./frontend/`
- Backend at `./backend/`
- Uses dev Docker images

**docker-compose.test.yaml** (Testing)
- Same as debug but uses test environment
- Creates isolated `test-network`
- Frontend runs with `npx react-router dev`

**docker-compose.prod.yaml** (Production)
- Uses built production images
- No source mounting
- SQLite database persisted at `./backend/db.sqlite3`

**docker-compose.release.yaml**
- For release builds

### Nginx Configuration
- Routes `/api/` to backend
- Routes all other requests to frontend
- SSL certificates at `nginx/data/ssl/`
- Certbot integration for Let's Encrypt

## Building & Pushing Images

```bash
# Build all
just docker::all-build

# Push all
just docker::all-push

# Individual services
just docker::backend::build
just docker::frontend::build
just docker::nginx::build
```

Version is pulled from `pyproject.toml`.

## Common Just Commands

```bash
# Development
just dev::debug          # Start dev environment
just dev::live           # Start with tmux

# Environment Management (dev, test, prod)
just dev::up             # Start dev environment
just dev::down           # Stop dev environment
just dev::logs           # Follow dev logs
just dev::ps             # List dev containers
just dev::restart        # Restart dev services
just dev::stop           # Stop without removing
just dev::build          # Build dev images
just dev::pull           # Pull dev images
just dev::top            # Show running processes
just dev::exec <svc> <cmd>    # Execute command in running container
just dev::run '<cmd>'         # Run one-off command in backend container

just test::up            # Start test environment
just test::down          # Stop test environment
# ... (same commands as dev::)

just prod::up            # Start prod environment
just prod::down          # Stop prod environment
# ... (same commands as dev::)

# Database Migrations
just db::run-migrate           # Run migrations for dev (default)
just db::migrate::dev          # Run migrations for dev environment
just db::migrate::test         # Run migrations for test environment
just db::migrate::prod         # Run migrations for prod environment
just db::migrate::all          # Run migrations for all environments

# Database Population
just db::populate::all         # Reset and populate test DB

# Docker Images
just docker::all-build         # Build all images
just docker::all-push          # Push all images
just docker::all-pull          # Pull all images
just docker::backend::build    # Build backend image
just docker::frontend::build   # Build frontend image
just docker::nginx::build      # Build nginx image

# Test Database
just docker::db::hash          # Output content hash for test-db sources
just docker::db::build         # Build test-db image (skips if hash unchanged)
just docker::db::pull          # Pull from GHCR (tries hash first, then latest)
just docker::db::push          # Push to GHCR (both hash and latest tags)
just db::reset-test            # Extract cached DB to backend/test.db.sqlite3
just db::populate::fresh       # Bypass cache, run fresh populate

# Docs
just docs::serve         # Start MkDocs dev server
just docs::build         # Build static docs site

# Updates
just update::all         # Update everything (git, deps, images)

# Version
just version::set 1.2.3  # Set version
just version::tag        # Tag and bump version

# Tests (Playwright)
just test::pw::install   # Install Playwright browsers
just test::pw::headless  # Run all tests headless
just test::pw::headed    # Run all tests headed
just test::pw::ui        # Open Playwright UI mode
just test::pw::debug     # Debug mode with inspector
just test::pw::spec <pattern>  # Run tests matching pattern
```

Run `just --list --list-submodules` for all available commands.

## Backend Development

```bash
# Database migrations
just db::makemigrations app
just py::migrate

# Django management commands
just py::manage <command>

# Django shell (with cache disabled)
just py::shell

# Run server directly
just py::runserver
```

## Frontend Development

```bash
cd frontend
npm install
npm run dev
```

## Testing

**Backend (via Docker - Recommended)**:
```bash
# Run all tests (avoids Redis hanging issues)
just test::run 'python manage.py test app.tests -v 2'

# Run specific test module
just test::run 'python manage.py test app.tests.test_shuffle_draft -v 2'
```

**Backend (Local - via pytest)**:
```bash
just py::test
```

**Frontend E2E (Playwright - Recommended)**:
```bash
# Run all Playwright tests headless
just test::pw::headless

# Run tests in headed mode (visible browser)
just test::pw::headed

# Open Playwright UI for interactive debugging
just test::pw::ui

# Run specific test file
just test::pw::spec 01-navigation
```

### Playwright Performance

**Local parallel execution:**
```bash
# Run with default workers (50% of CPUs)
just test::pw::headless

# Run with specific worker count
just test::pw::headless --workers=4

# Run specific shard locally (for debugging CI issues)
just test::pw::headless --shard=1/4
```

**CI sharding:**
Tests are automatically sharded across 4 parallel runners in CI for ~4x speedup.
Each shard runs approximately 1/4 of the test suite.

**Running specific test suites:**
```bash
just test::pw::spec navigation    # Navigation tests only
just test::pw::spec tournament    # Tournament tests only
just test::pw::spec league        # League tests only
just test::pw::spec herodraft     # HeroDraft tests only
```

## Documentation

Project documentation uses MkDocs Material:

```bash
# Serve docs locally
just docs::serve

# Build static site
just docs::build
```

Docs available at http://127.0.0.1:8000

## Git Worktree Setup

**Note**: `.claude/` directory is shared between main repo and worktrees (same git repo). Changes sync automatically.

### Initial Worktree Setup

```bash
# 1. Create worktree
cd /home/kettle/git_repos/website
git worktree add .worktrees/feature-name -b feature/feature-name

# 2. Bootstrap the worktree (creates venv, installs deps)
cd /home/kettle/git_repos/website/.worktrees/feature-name
./dev

# 3. Copy backend secrets from main repo
cp /home/kettle/git_repos/website/backend/.env ./backend/.env

# 4. Run migrations for all environments
just db::migrate::all

# 5. Populate test data (optional)
just db::populate::all
```

### Using Just in Worktrees

Just auto-detects the venv from the repo root, so commands work seamlessly:
```bash
cd /home/kettle/git_repos/website/.worktrees/feature-name
just dev::debug
just test::run 'python manage.py test app.tests -v 2'
```

## Agents Available

- `python-backend` - Django/Python backend expertise
- `typescript-frontend` - React/TypeScript frontend expertise
- `mkdocs-documentation` - MkDocs Material documentation management
- `docker-ops` - Docker setup, troubleshooting, and verification

## Skills Available

- `just` - Just command runner (auto-activates venv, works in worktrees)
- `visual-debugging` - Chrome MCP browser automation for debugging

## Demo Video Recording

**IMPORTANT**: Always use `just demo::*` commands to record demo videos (or `just test::demo::*` when in test environment).

After editing UI components in `frontend/app/components/herodraft/`, `draft/`, or `bracket/`, run the appropriate demo recording command:

```bash
# Record all demos
just demo::all

# Individual demos
just demo::snake         # Snake draft demo
just demo::shuffle       # Shuffle draft demo
just demo::herodraft     # HeroDraft with bracket demo
just demo::snapshots     # Site screenshots

# Post-processing
just demo::trim          # Trim initial white screen
just demo::gifs          # Convert videos to GIFs

# Quick workflow (record + GIFs)
just demo::quick
```

See [docs/ai/demo/](docs/ai/demo/index.md) for full guidelines.
