# DTX Website - Claude Code Configuration

Website for managing DTX, a Dota2 gaming organization.

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

**Backend**: Django, Django REST Framework, django-social-auth (Discord OAuth), Redis (cacheops)
**Frontend**: React, TypeScript, Vite, React Router, TailwindCSS, Shadcn UI, Zustand, Zod
**Infrastructure**: Docker, Nginx, GitHub Container Registry

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

### Full Test Setup (with Cypress)
```bash
source .venv/bin/activate
inv test.setup
inv test.open  # or inv test.headless
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

# Database
inv db.migrate         # Run migrations
inv db.populate.all    # Reset and populate test DB

# Docker
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

# Tests
inv test.setup         # Full test setup
inv test.open          # Cypress interactive
inv test.headless      # Cypress headless
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

**Backend**: `python manage.py test`
**Frontend E2E**: Cypress tests in `frontend/tests/cypress/`

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

## Agents Available

- `python-backend` - Django/Python backend expertise
- `typescript-frontend` - React/TypeScript frontend expertise
- `inv-runner` - Python Invoke task runner (consults with docs and docker agents)
- `mkdocs-documentation` - MkDocs Material documentation management
- `docker-ops` - Docker setup, troubleshooting, and verification

## Skills Available

- `visual-debugging` - Chrome MCP browser automation for debugging
