# Invoke Commands Reference

Complete reference for all invoke commands in the DTX project.

## Development Commands (`inv dev.*`)

```bash
inv dev.debug    # Start development environment with hot reload
inv dev.live     # Start with tmux (multiple panes)
inv dev.prod     # Run production images locally
inv dev.release  # Run release images
inv dev.mac      # macOS M1 specific
inv dev.test     # Run test environment
```

## Environment Management (`inv <env>.*`)

Available for `dev`, `test`, and `prod` environments:

```bash
inv <env>.up       # Start environment
inv <env>.down     # Stop and remove containers
inv <env>.logs     # Follow container logs
inv <env>.ps       # List containers
inv <env>.restart  # Restart services
inv <env>.stop     # Stop without removing
inv <env>.build    # Build images
inv <env>.pull     # Pull images
inv <env>.top      # Show running processes
inv <env>.exec <svc> <cmd>   # Execute command in running container
inv <env>.run --service <svc> --cmd '<cmd>'  # Run one-off command in new container
```

## Docker Commands (`inv docker.*`)

```bash
# Build
inv docker.all.build      # Build all images
inv docker.backend.build  # Build backend only
inv docker.frontend.build # Build frontend only
inv docker.nginx.build    # Build nginx only

# Push
inv docker.all.push       # Push all images
inv docker.backend.push   # Push backend only

# Pull
inv docker.all.pull       # Pull all images

# Run (without compose)
inv docker.backend.run    # Run backend container
inv docker.frontend.run   # Run frontend container
```

## Database Commands (`inv db.*`)

```bash
# Migrations
inv db.migrate              # Run migrations (dev, default)
inv db.migrate.dev          # Run migrations for dev
inv db.migrate.test         # Run migrations for test
inv db.migrate.prod         # Run migrations for prod
inv db.migrate.all          # Run migrations for all environments
inv db.makemigrations       # Create migrations

# Populate test data
inv db.populate.users       # Populate users from Discord
inv db.populate.tournaments # Populate tournaments with random users
inv db.populate.all         # Reset test DB and populate everything
```

## Test Commands (`inv test.*`)

```bash
inv test.setup      # Full setup: update deps, build images, populate, start
inv test.open       # Open Cypress interactive mode
inv test.headless   # Run Cypress headless
inv test.run --cmd '<cmd>'  # Run command in test container
```

## Update Commands (`inv update.*`)

```bash
inv update.all      # Update everything (git, deps, images)
inv update.git      # Git pull only
inv update.python   # Poetry install only
inv update.npm      # npm install only
```

## Version Commands (`inv version.*`)

```bash
inv version.set <version>     # Set version across all files
inv version.from-env          # Sync from .env.release to pyproject.toml
inv version.from-pyproject    # Sync from pyproject.toml to env files
inv version.build             # Build Docker images with version sync
inv version.tag               # Git tag current version and bump patch
```

## Docs Commands (`inv docs.*`)

```bash
inv docs.serve    # Start MkDocs dev server (port 8000)
inv docs.build    # Build static documentation site
```

## Environment Files

- `docker/.env.dev` - Development settings
- `docker/.env.test` - Testing settings
- `docker/.env.prod` - Production settings
- `docker/.env.release` - Release builds

## Task File Locations

| File | Purpose |
|------|---------|
| `tasks.py` | Main task definitions |
| `scripts/docker.py` | Docker build/push/pull |
| `scripts/tests.py` | Test setup and Cypress |
| `scripts/update.py` | Dependency updates |
| `scripts/version.py` | Version management |
| `backend/tasks.py` | Database migrations |
