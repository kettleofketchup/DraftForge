# Quick Start

!!! warning "Always Source the Virtual Environment"
    Before running any Python or Invoke commands:
    ```bash
    source .venv/bin/activate
    ```

## Development Mode

Start the full development stack with hot reloading:

```bash
source .venv/bin/activate
inv dev.debug
```

This starts:

- Frontend dev server with hot reload
- Backend Django server
- Redis cache
- Nginx reverse proxy

Access the application at **https://localhost**

## Common Commands

### Start Development

```bash
inv dev.debug      # Standard development
inv dev.live       # Development with tmux
```

### Database Operations

```bash
inv db.migrate           # Run migrations (dev, default)
inv db.migrate.all       # Run migrations for all environments
inv db.migrate.test      # Run migrations for test environment
inv db.populate.all      # Populate test data
inv db.populate.users    # Populate users only
```

### Docker Operations

```bash
inv docker.all.build     # Build all images
inv docker.all.push      # Push to registry
inv docker.all.pull      # Pull latest images
```

### Testing

```bash
inv test.setup      # Full test environment setup
inv test.open       # Cypress interactive mode
inv test.headless   # Cypress headless mode
```

### Updates

```bash
inv update.all      # Update everything
inv update.git      # Git pull only
inv update.npm      # npm install only
inv update.python   # Poetry install only
```

## Available Invoke Tasks

Run `inv --list` to see all available tasks organized by namespace:

- `dev.*` - Development commands
- `docker.*` - Docker operations
- `db.*` - Database operations
- `test.*` - Testing commands
- `update.*` - Dependency updates
- `version.*` - Version management
- `prod.*` - Production commands
