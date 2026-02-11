# Quick Start

!!! info "No Manual Venv Activation Needed"
    Just commands automatically activate the correct virtual environment.

## Development Mode

Start the full development stack with hot reloading:

```bash
just dev::debug
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
just dev::debug      # Standard development
just dev::live       # Development with tmux
```

### Database Operations

```bash
just db::run-migrate       # Run migrations (dev, default)
just db::migrate::all      # Run migrations for all environments
just db::migrate::test     # Run migrations for test environment
just db::populate::all     # Populate test data
```

### Docker Operations

```bash
just docker::all-build     # Build all images
just docker::all-push      # Push to registry
just docker::all-pull      # Pull latest images
```

### Testing

```bash
just test::setup           # Full test environment setup
just test::pw::ui          # Playwright interactive UI mode
just test::pw::headless    # Playwright headless mode
```

### Updates

```bash
just update::all      # Update everything
```

## Available Just Commands

Run `just --list --list-submodules` to see all available commands organized by namespace:

- `dev::*` - Development commands
- `docker::*` - Docker operations
- `db::*` - Database operations
- `test::*` - Testing commands
- `update::*` - Dependency updates
- `version::*` - Version management
- `prod::*` - Production commands
