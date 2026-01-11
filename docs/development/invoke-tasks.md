# Invoke Tasks

This project uses [Python Invoke](https://www.pyinvoke.org/) for task automation.

!!! warning "Always Source Virtual Environment"
    ```bash
    source .venv/bin/activate
    ```

## Task Namespaces

| Namespace | Description |
|-----------|-------------|
| `dev.*` | Development environment |
| `docker.*` | Docker operations |
| `db.*` | Database management |
| `test.*` | Testing commands |
| `update.*` | Dependency updates |
| `version.*` | Version management |
| `prod.*` | Production commands |

## Development Tasks (`inv dev.*`)

```bash
inv dev.debug     # Start with hot reload
inv dev.live      # Start with tmux
inv dev.prod      # Run production images locally
inv dev.release   # Run release images
inv dev.test      # Start test environment
inv dev.mac       # macOS M1 specific
```

## Docker Tasks (`inv docker.*`)

### Build
```bash
inv docker.all.build      # All images
inv docker.backend.build  # Backend only
inv docker.frontend.build # Frontend only
inv docker.nginx.build    # Nginx only
```

### Push
```bash
inv docker.all.push       # All images
inv docker.backend.push   # Backend only
inv docker.frontend.push  # Frontend only
inv docker.nginx.push     # Nginx only
```

### Pull
```bash
inv docker.all.pull       # All images
inv docker.backend.pull   # Backend only
inv docker.frontend.pull  # Frontend only
```

### Run
```bash
inv docker.backend.run    # Run backend container
inv docker.frontend.run   # Run frontend container
inv docker.nginx.run      # Run nginx container
```

## Database Tasks (`inv db.*`)

```bash
# Migrations
inv db.migrate              # Run migrations (dev, default)
inv db.migrate.dev          # Run migrations for dev
inv db.migrate.test         # Run migrations for test
inv db.migrate.prod         # Run migrations for prod
inv db.migrate.all          # Run migrations for all environments
inv db.makemigrations       # Create migrations

# Population
inv db.populate.users       # Populate users
inv db.populate.tournaments # Populate tournaments
inv db.populate.all         # Reset and populate all
```

## Test Tasks (`inv test.*`)

```bash
inv test.setup      # Full setup
inv test.open       # Cypress interactive
inv test.headless   # Cypress headless
```

## Update Tasks (`inv update.*`)

```bash
inv update.all       # Everything
inv update.git       # Git pull
inv update.npm       # npm install
inv update.python    # Poetry install
inv update.all_test  # Test environment
```

## Version Tasks (`inv version.*`)

```bash
inv version.set 1.2.3     # Set version
inv version.from-env      # Sync from .env.release
inv version.from-pyproject # Sync from pyproject.toml
inv version.build         # Build with version
inv version.tag           # Git tag and bump
```

## Production Tasks (`inv prod.*`)

```bash
inv prod.certbot    # SSL certificate renewal
```

## Task Files

- `tasks.py` - Main task definitions
- `scripts/docker.py` - Docker tasks
- `scripts/tests.py` - Test tasks
- `scripts/update.py` - Update tasks
- `scripts/version.py` - Version tasks
- `backend/tasks.py` - Database tasks
