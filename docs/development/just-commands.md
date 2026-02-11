# Just Commands

This project uses [just](https://github.com/casey/just) as the task runner. Just automatically handles virtual environment activation -- no manual `source .venv/bin/activate` needed.

!!! info "Listing All Commands"
    ```bash
    just --list --list-submodules
    ```

## Command Namespaces

| Namespace | Description |
|-----------|-------------|
| `dev::*` | Development environment |
| `docker::*` | Docker operations |
| `db::*` | Database management |
| `test::*` | Testing commands |
| `update::*` | Dependency updates |
| `version::*` | Version management |
| `prod::*` | Production commands |
| `demo::*` | Demo video recording |
| `docs::*` | Documentation commands |
| `py::*` | Python/Django commands |

## Development Commands (`just dev::*`)

```bash
just dev::debug     # Start with hot reload
just dev::live      # Start with tmux
just dev::local-prod # Run production images locally
just dev::up        # Start dev environment (detached)
just dev::down      # Stop dev environment
just dev::logs      # Follow dev logs
just dev::ps        # List dev containers
just dev::restart   # Restart dev services
just dev::stop      # Stop without removing
just dev::build     # Build dev images
just dev::pull      # Pull dev images
just dev::exec <svc> <cmd>  # Execute command in running container
just dev::run '<cmd>'       # Run one-off command in backend container
```

## Docker Commands (`just docker::*`)

### Build
```bash
just docker::all-build        # All images
just docker::backend::build   # Backend only
just docker::frontend::build  # Frontend only
just docker::nginx::build     # Nginx only
just docker::release::build   # Prod-only images (no -dev)
```

### Push
```bash
just docker::all-push         # All images
just docker::backend::push    # Backend only
just docker::frontend::push   # Frontend only
just docker::nginx::push      # Nginx only
just docker::release::push    # Build and push prod-only images
```

### Pull
```bash
just docker::all-pull         # All images
just docker::release::pull    # Prod-only images (no -dev)
```

### Test Database
```bash
just docker::db::hash         # Output content hash for test-db sources
just docker::db::build        # Build test-db image (skips if hash unchanged)
just docker::db::pull         # Pull from GHCR (tries hash first, then latest)
just docker::db::push         # Push to GHCR (both hash and latest tags)
```

## Database Commands (`just db::*`)

```bash
# Migrations
just db::run-migrate          # Run migrations (dev, default)
just db::migrate::dev         # Run migrations for dev
just db::migrate::test        # Run migrations for test
just db::migrate::prod        # Run migrations for prod
just db::migrate::all         # Run migrations for all environments
just db::makemigrations app   # Create migrations

# Population
just db::populate::all        # Reset and populate all
just db::populate::fresh      # Bypass cache, run fresh populate
just db::reset-test           # Extract cached DB to backend/test.db.sqlite3
```

## Test Commands (`just test::*`)

### Playwright (Recommended)

```bash
just test::pw::install        # Install Playwright browsers
just test::pw::headless       # Run all tests headless
just test::pw::headed         # Run tests with visible browser
just test::pw::ui             # Open Playwright UI mode
just test::pw::debug          # Debug mode with inspector
just test::pw::report         # View HTML test report
just test::pw::spec <pattern> # Run tests matching grep pattern

# Specific test suites
just test::pw::spec navigation  # Navigation tests
just test::pw::spec tournament  # Tournament tests
just test::pw::spec draft       # Draft tests
just test::pw::spec bracket     # Bracket tests
just test::pw::spec league      # League tests
just test::pw::spec mobile      # Mobile responsive tests
just test::pw::spec herodraft   # HeroDraft tests
```

### Environment Management

```bash
just test::setup              # Full test environment setup
just test::up                 # Start test environment
just test::down               # Stop test environment
just test::logs               # Follow test logs
just test::ps                 # List test containers
just test::restart            # Restart test services
```

### Backend Tests

```bash
just test::run '<command>'    # Run command in test container
```

## Update Commands (`just update::*`)

```bash
just update::all       # Everything (git, deps, images)
```

## Version Commands (`just version::*`)

```bash
just version::set 1.2.3     # Set version
just version::tag            # Git tag and bump
```

## Production Commands (`just prod::*`)

```bash
just prod::certbot    # SSL certificate renewal
just prod::up         # Start production environment
just prod::down       # Stop production environment
```

## Python/Django Commands (`just py::*`)

```bash
just py::manage <command>    # Django management commands
just py::shell               # Django shell (with cache disabled)
just py::runserver           # Run server directly
just py::test                # Run pytest locally
just py::migrate             # Run migrations
```

## Demo Tasks

Record demo videos of features using Playwright, then convert to GIFs for documentation.

```bash
# Record all demos
just demo::all

# Record specific demos
just demo::shuffle        # Shuffle draft demo
just demo::snake          # Snake draft demo
just demo::herodraft      # HeroDraft with bracket demo
just demo::snapshots      # Site screenshots

# Convert videos to GIFs
just demo::gifs

# Trim initial white screen from videos
just demo::trim

# Record and convert in one step
just demo::quick
```

Output locations:

- Videos: `docs/assets/videos/`
- GIFs: `docs/assets/gifs/`

## Docs Commands (`just docs::*`)

```bash
just docs::serve      # Start MkDocs dev server
just docs::build      # Build static documentation site
```

## Justfile Location

The main `justfile` is at the project root. It imports module justfiles for each namespace.
