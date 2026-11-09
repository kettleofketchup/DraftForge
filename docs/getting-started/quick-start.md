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

Access the application at **https://localhost**. The dev stack runs as compose
project `df-dev`, one per machine.

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
just test::slot            # This worktree's test slot and URL
just test::pw::ui          # Playwright interactive UI mode
just test::pw::headless    # Playwright headless mode
```

Each git worktree runs its own test stack in a slot: `https://localhost` on slot 0,
`https://localhost:1N443` on slot N. The dev stack and test slot 0 both use ports
80/443, so stop one before starting the other. See
[Test Stack Slots](../development/test-stack-slots.md).

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
