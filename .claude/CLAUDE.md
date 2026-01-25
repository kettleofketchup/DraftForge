# DraftForge - Claude Code Configuration

DraftForge is a platform for managing Dota 2 tournaments, teams, and competitive gaming.

## First Things First

**IMPORTANT**: Always source the virtual environment before running Python or Invoke commands:

```bash
source .venv/bin/activate
```

This project uses Python Invoke for task automation. All repo operations should use `inv` commands.

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

### Development (Docker)
```bash
source .venv/bin/activate
inv dev.debug
```

### Production
```bash
source .venv/bin/activate
inv dev.prod
```

### Testing
```bash
source .venv/bin/activate
inv dev.test
```

### Full Test Setup (with Playwright)
```bash
source .venv/bin/activate
inv test.setup
inv test.playwright.headless  # or inv test.playwright.headed
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
source .venv/bin/activate

# Build all
inv docker.all.build

# Push all
inv docker.all.push

# Individual services
inv docker.backend.build
inv docker.frontend.build
inv docker.nginx.build
```

Version is pulled from `pyproject.toml`.

## Common Invoke Commands

```bash
source .venv/bin/activate

# Development
inv dev.debug          # Start dev environment
inv dev.live           # Start with tmux

# Environment Management (dev, test, prod)
inv dev.up             # Start dev environment
inv dev.down           # Stop dev environment
inv dev.logs           # Follow dev logs
inv dev.ps             # List dev containers
inv dev.restart        # Restart dev services
inv dev.stop           # Stop without removing
inv dev.build          # Build dev images
inv dev.pull           # Pull dev images
inv dev.top            # Show running processes
inv dev.exec <svc> <cmd>  # Execute command in running container
inv dev.run --service backend --cmd '<cmd>'  # Run one-off command in new container

inv test.up            # Start test environment
inv test.down          # Stop test environment
# ... (same commands as dev)

inv prod.up            # Start prod environment
inv prod.down          # Stop prod environment
# ... (same commands as dev)

# Database Migrations
inv db.migrate         # Run migrations for dev (default)
inv db.migrate.dev     # Run migrations for dev environment
inv db.migrate.test    # Run migrations for test environment
inv db.migrate.prod    # Run migrations for prod environment
inv db.migrate.all     # Run migrations for all environments

# Database Population
inv db.populate.all    # Reset and populate test DB

# Docker Images
inv docker.all.build   # Build all images
inv docker.all.push    # Push all images
inv docker.all.pull    # Pull all images

# Docs
inv docs.serve         # Start MkDocs dev server
inv docs.build         # Build static docs site

# Updates
inv update.all         # Update everything (git, deps, images)

# Version
inv version.set 1.2.3  # Set version
inv version.tag        # Tag and bump version

# Tests (Playwright)
inv test.playwright.install    # Install Playwright browsers
inv test.playwright.headless   # Run all tests headless
inv test.playwright.headed     # Run all tests headed
inv test.playwright.ui         # Open Playwright UI mode
inv test.playwright.debug      # Debug mode with inspector
inv test.playwright.spec --spec <pattern>  # Run tests matching pattern
```

Run `inv --list` for all available tasks.

## Backend Development

```bash
source .venv/bin/activate
cd backend

# Database migrations
python manage.py makemigrations app
python manage.py migrate

# Without Redis (for management commands)
DISABLE_CACHE=true python manage.py <command>

# Run server
python manage.py runserver
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
source .venv/bin/activate

# Run all tests (avoids Redis hanging issues)
inv test.run --cmd 'python manage.py test app.tests -v 2'

# Run specific test module
inv test.run --cmd 'python manage.py test app.tests.test_shuffle_draft -v 2'
```

**Backend (Local - May hang on cleanup due to Redis/cacheops)**:
```bash
DISABLE_CACHE=true python manage.py test app.tests -v 2
```

**Frontend E2E (Playwright - Recommended)**:
```bash
source .venv/bin/activate

# Run all Playwright tests headless
inv test.playwright.headless

# Run tests in headed mode (visible browser)
inv test.playwright.headed

# Open Playwright UI for interactive debugging
inv test.playwright.ui

# Run specific test file
inv test.playwright.spec --file tests/playwright/e2e/01-navigation.spec.ts
```

### Playwright Performance

**Local parallel execution:**
```bash
# Run with default workers (50% of CPUs)
inv test.playwright.headless

# Run with specific worker count
inv test.playwright.headless --args="--workers=4"

# Run specific shard locally (for debugging CI issues)
inv test.playwright.headless --args="--shard=1/4"
```

**CI sharding:**
Tests are automatically sharded across 4 parallel runners in CI for ~4x speedup.
Each shard runs approximately 1/4 of the test suite.

**Running specific test suites:**
```bash
inv test.playwright.navigation    # Navigation tests only
inv test.playwright.tournament    # Tournament tests only
inv test.playwright.league        # League tests only
inv test.playwright.herodraft     # HeroDraft tests only
```

## Documentation

Project documentation uses MkDocs Material:

```bash
source .venv/bin/activate

# Serve docs locally
mkdocs serve

# Build static site
mkdocs build
```

Docs available at http://127.0.0.1:8000

## Git Worktree Setup

**Note**: `.claude/` directory is shared between main repo and worktrees (same git repo). Changes sync automatically.

### Initial Worktree Setup

```bash
# 1. Create worktree
cd /home/kettle/git_repos/website
git worktree add .worktrees/feature-name -b feature/feature-name

# 2. Setup worktree Python environment
cd /home/kettle/git_repos/website/.worktrees/feature-name
python -m venv .venv
source .venv/bin/activate
poetry install

# 3. Copy backend secrets from main repo
cp /home/kettle/git_repos/website/backend/.env ./backend/.env

# 4. Install frontend dependencies (IMPORTANT: must be in worktree!)
cd /home/kettle/git_repos/website/.worktrees/feature-name/frontend
npm install

# 5. Run migrations for all environments (from worktree root)
cd /home/kettle/git_repos/website/.worktrees/feature-name
source .venv/bin/activate
inv db.migrate.all

# 6. Start Docker environment
inv dev.test  # Detached mode for testing, or inv dev.debug for dev

# 7. Populate test data (optional)
inv db.populate.all
```

### Using Invoke in Worktrees

Always cd into the worktree first:
```bash
cd /home/kettle/git_repos/website/.worktrees/feature-name
poetry run inv dev.debug
poetry run inv test.run --cmd 'python manage.py test app.tests -v 2'
```

## Agents Available

- `python-backend` - Django/Python backend expertise
- `typescript-frontend` - React/TypeScript frontend expertise
- `mkdocs-documentation` - MkDocs Material documentation management
- `docker-ops` - Docker setup, troubleshooting, and verification

## Skills Available

- `inv-runner` - Python Invoke task automation (backend tests via Docker, environment management)
- `visual-debugging` - Chrome MCP browser automation for debugging
