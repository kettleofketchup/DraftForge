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
| `discord.*` | Discord integration commands |
| `demo.*` | Demo video recording |
| `docs.*` | Documentation commands |

## Development Tasks (`inv dev.*`)

```bash
inv dev.debug     # Start with hot reload
inv dev.live      # Start with tmux
inv dev.prod      # Run production images locally
inv dev.release   # Run release images
inv dev.test      # Start test environment
inv dev.mac       # macOS M1 specific
inv dev.sync-backend  # Sync backend files to container
inv dev.sync-frontend # Sync frontend files to container
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
inv db.populate.heroes      # Populate hero data
inv db.populate.leagues     # Populate leagues
inv db.populate.all         # Reset and populate all
```

## Test Tasks (`inv test.*`)

### Playwright (Recommended)

```bash
inv test.playwright.install     # Install Playwright browsers
inv test.playwright.headless    # Run all tests headless
inv test.playwright.headed      # Run tests with visible browser
inv test.playwright.ui          # Open Playwright UI mode
inv test.playwright.debug       # Debug mode with inspector
inv test.playwright.report      # View HTML test report
inv test.playwright.spec --spec <pattern>  # Run tests matching grep pattern

# Specific test suites
inv test.playwright.navigation  # Navigation tests
inv test.playwright.tournament  # Tournament tests
inv test.playwright.draft       # Draft tests
inv test.playwright.bracket     # Bracket tests
inv test.playwright.league      # League tests
inv test.playwright.mobile      # Mobile responsive tests
inv test.playwright.herodraft   # HeroDraft tests
```

### Cypress (Legacy)

```bash
inv test.setup      # Full setup
inv test.open       # Cypress interactive
inv test.headless   # Cypress headless
inv test.spec --spec <shortcut>  # Run specific Cypress spec
```

### Backend Tests

```bash
inv test.run --cmd '<command>'  # Run command in test container
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

## Discord Tasks (`inv discord.*`)

```bash
inv discord.sync    # Sync Discord roles and members
```

## Demo Tasks (`inv demo.*`)

Record demo videos of features using Playwright, then convert to GIFs for documentation.

```bash
# Record all demos
inv demo.create

# Record specific demos
inv demo.shuffle        # Shuffle draft demo
inv demo.snake          # Snake draft demo
inv demo.herodraft      # HeroDraft with bracket demo

# Convert videos to GIFs
inv demo.gifs                          # Default settings
inv demo.gifs --duration 10 --fps 15  # Custom duration and framerate

# Record and convert in one step
inv demo.quick

# Clean up demo output
inv demo.clean
```

Output locations:

- Videos: `docs/assets/videos/`
- GIFs: `docs/assets/gifs/`

## Docs Tasks (`inv docs.*`)

```bash
inv docs.serve      # Start MkDocs dev server
inv docs.build      # Build static documentation site
```

## Task Files

- `tasks.py` - Main task definitions
- `scripts/docker.py` - Docker tasks
- `scripts/tests.py` - Test tasks
- `scripts/update.py` - Update tasks
- `scripts/version.py` - Version tasks
- `backend/tasks.py` - Database tasks
