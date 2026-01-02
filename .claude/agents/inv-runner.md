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

**IMPORTANT**: Use `poetry run inv` to run invoke commands (no need to source venv):

```bash
poetry run inv <command>
```

## Available Task Namespaces

Run `poetry run inv --list` to see all available tasks. The project uses these namespaces:

| Namespace | Description |
|-----------|-------------|
| `dev.*` | Development environment commands |
| `docker.*` | Docker image build/push/pull |
| `db.*` | Database migrations and population |
| `test.*` | Testing commands |
| `update.*` | Dependency and repo updates |
| `version.*` | Version management |
| `prod.*` | Production commands |
| `docs.*` | Documentation build commands |

## Development Commands (`poetry run inv dev.*`)

```bash
# Start development environment with hot reload
poetry run inv dev.debug

# Start with tmux (multiple panes)
poetry run inv dev.live

# Run production images locally
poetry run inv dev.prod

# Run release images
poetry run inv dev.release

# macOS M1 specific
poetry run inv dev.mac

# Run test environment
poetry run inv dev.test
```

## Docker Commands (`poetry run inv docker.*`)

### Build Images
```bash
poetry run inv docker.all.build      # Build all images
poetry run inv docker.backend.build  # Build backend only
poetry run inv docker.frontend.build # Build frontend only
poetry run inv docker.nginx.build    # Build nginx only
```

### Push Images
```bash
poetry run inv docker.all.push       # Push all images
poetry run inv docker.backend.push   # Push backend only
poetry run inv docker.frontend.push  # Push frontend only
poetry run inv docker.nginx.push     # Push nginx only
```

### Pull Images
```bash
poetry run inv docker.all.pull       # Pull all images
poetry run inv docker.backend.pull   # Pull backend
poetry run inv docker.frontend.pull  # Pull frontend
```

### Run Images
```bash
poetry run inv docker.backend.run    # Run backend container
poetry run inv docker.frontend.run   # Run frontend container
poetry run inv docker.nginx.run      # Run nginx container
```

## Database Commands (`poetry run inv db.*`)

```bash
poetry run inv db.migrate              # Run migrations (default: debug env)
poetry run inv db.makemigrations       # Create migrations

# Populate test data
poetry run inv db.populate.users       # Populate users from Discord
poetry run inv db.populate.tournaments # Populate tournaments with random users
poetry run inv db.populate.all         # Reset test DB and populate everything
```

## Test Commands (`poetry run inv test.*`)

```bash
poetry run inv test.setup      # Full setup: update deps, build images, populate, start
poetry run inv test.open       # Open Cypress interactive mode (runs setup first)
poetry run inv test.headless   # Run Cypress headless (runs setup first)
```

## Update Commands (`poetry run inv update.*`)

```bash
poetry run inv update.all      # Pull git, migrate, npm install, poetry install, pull images
poetry run inv update.git      # Git pull only
poetry run inv update.python   # Poetry install only
poetry run inv update.npm      # npm install only
poetry run inv update.all_test # Update for test environment
```

## Version Commands (`poetry run inv version.*`)

```bash
poetry run inv version.set <version>     # Set version across all files
poetry run inv version.from-env          # Sync version from .env.release to pyproject.toml
poetry run inv version.from-pyproject    # Sync version from pyproject.toml to env files
poetry run inv version.build             # Build Docker images with version sync
poetry run inv version.tag               # Git tag current version and bump patch
```

## Production Commands (`poetry run inv prod.*`)

```bash
poetry run inv prod.certbot    # Run certbot for SSL certificate renewal
```

## Docs Commands (`poetry run inv docs.*`)

```bash
poetry run inv docs.serve    # Start MkDocs dev server with hot reload (port 8000)
poetry run inv docs.build    # Build static documentation site to site/
```

## Common Workflows

### Start Development
```bash
poetry run inv dev.debug
```

### Prepare for Testing
```bash
poetry run inv test.setup
poetry run inv test.open  # or poetry run inv test.headless
```

### Release New Version
```bash
poetry run inv version.set 1.2.3
poetry run inv docker.all.build
poetry run inv docker.all.push
poetry run inv version.tag
```

### Update Everything
```bash
poetry run inv update.all
```

### Reset Test Database
```bash
poetry run inv db.populate.all
```

## Environment Files

Tasks use different environment files based on context:
- `docker/.env.dev` - Development
- `docker/.env.test` - Testing
- `docker/.env.prod` - Production
- `docker/.env.release` - Release builds

## Notes

- Version is pulled from `pyproject.toml`
- Docker images are pushed to GitHub Container Registry (`ghcr.io/kettleofketchup/dota_tournament/`)
- Database migrations run with `DISABLE_CACHE=true` to avoid Redis dependency
- Apps with migrations: `steam`, `app`, `bracket`, `discordbot`
