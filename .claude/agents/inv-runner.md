# Invoke Runner Agent

Expert agent for running Python Invoke tasks in the DTX website project.

## When to Use This Agent

Use this agent when:

- **Running repo commands** - Any invoke task execution
- **Updating invoke tasks** - Modifying `tasks.py` or `scripts/*.py`
- **Adding new tasks** - Creating new automation commands
- **Docker command updates** - Changes to docker-related invoke tasks
- **Workflow automation** - Creating or modifying development workflows

## Agent Collaboration

!!! important "Keep Documentation in Sync"
    When modifying invoke tasks, **always consult the `mkdocs-documentation` agent** to update:

    - `docs/development/invoke-tasks.md` - Task reference
    - `docs/getting-started/quick-start.md` - Common commands
    - `CLAUDE.md` - Quick reference section

!!! important "Docker Changes"
    When modifying docker-related tasks, **consult the `docker-ops` agent** to ensure:

    - Docker Compose files are updated if needed
    - Environment files are consistent
    - Image tags and versions are correct

## Task File Locations

| File | Purpose |
|------|---------|
| `tasks.py` | Main task definitions, dev commands |
| `scripts/docker.py` | Docker build/push/pull tasks |
| `scripts/tests.py` | Test setup and Cypress tasks |
| `scripts/update.py` | Dependency update tasks |
| `scripts/version.py` | Version management tasks |
| `backend/tasks.py` | Database migration tasks |

## Prerequisites

**IMPORTANT**: Always source the virtual environment before running invoke commands:

```bash
source .venv/bin/activate
```

## Available Task Namespaces

Run `inv --list` to see all available tasks. The project uses these namespaces:

| Namespace | Description |
|-----------|-------------|
| `dev.*` | Development environment commands |
| `docker.*` | Docker image build/push/pull |
| `db.*` | Database migrations and population |
| `test.*` | Testing commands |
| `update.*` | Dependency and repo updates |
| `version.*` | Version management |
| `prod.*` | Production commands |

## Development Commands (`inv dev.*`)

```bash
# Start development environment with hot reload
inv dev.debug

# Start with tmux (multiple panes)
inv dev.live

# Run production images locally
inv dev.prod

# Run release images
inv dev.release

# macOS M1 specific
inv dev.mac

# Run test environment
inv dev.test
```

## Docker Commands (`inv docker.*`)

### Build Images
```bash
inv docker.all.build      # Build all images
inv docker.backend.build  # Build backend only
inv docker.frontend.build # Build frontend only
inv docker.nginx.build    # Build nginx only
```

### Push Images
```bash
inv docker.all.push       # Push all images
inv docker.backend.push   # Push backend only
inv docker.frontend.push  # Push frontend only
inv docker.nginx.push     # Push nginx only
```

### Pull Images
```bash
inv docker.all.pull       # Pull all images
inv docker.backend.pull   # Pull backend
inv docker.frontend.pull  # Pull frontend
```

### Run Images
```bash
inv docker.backend.run    # Run backend container
inv docker.frontend.run   # Run frontend container
inv docker.nginx.run      # Run nginx container
```

## Database Commands (`inv db.*`)

```bash
inv db.migrate              # Run migrations (default: debug env)
inv db.makemigrations       # Create migrations

# Populate test data
inv db.populate.users       # Populate users from Discord
inv db.populate.tournaments # Populate tournaments with random users
inv db.populate.all         # Reset test DB and populate everything
```

## Test Commands (`inv test.*`)

```bash
inv test.setup      # Full setup: update deps, build images, populate, start
inv test.open       # Open Cypress interactive mode (runs setup first)
inv test.headless   # Run Cypress headless (runs setup first)
```

## Update Commands (`inv update.*`)

```bash
inv update.all      # Pull git, migrate, npm install, poetry install, pull images
inv update.git      # Git pull only
inv update.python   # Poetry install only
inv update.npm      # npm install only
inv update.all_test # Update for test environment
```

## Version Commands (`inv version.*`)

```bash
inv version.set <version>     # Set version across all files
inv version.from-env          # Sync version from .env.release to pyproject.toml
inv version.from-pyproject    # Sync version from pyproject.toml to env files
inv version.build             # Build Docker images with version sync
inv version.tag               # Git tag current version and bump patch
```

## Production Commands (`inv prod.*`)

```bash
inv prod.certbot    # Run certbot for SSL certificate renewal
```

## Common Workflows

### Start Development
```bash
source .venv/bin/activate
inv dev.debug
```

### Prepare for Testing
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

### Update Everything
```bash
source .venv/bin/activate
inv update.all
```

### Reset Test Database
```bash
source .venv/bin/activate
inv db.populate.all
```

## Environment Files

Tasks use different environment files based on context:
- `docker/.env.dev` - Development
- `docker/.env.test` - Testing
- `docker/.env.prod` - Production
- `docker/.env.release` - Release builds

## Notes

- Version is pulled from `pyproject.toml`
- Docker images are pushed to GitHub Container Registry (`ghcr.io/kettleofketchup/dtx_website/`)
- Database migrations run with `DISABLE_CACHE=true` to avoid Redis dependency
- Apps with migrations: `steam`, `app`, `bracket`, `discordbot`
