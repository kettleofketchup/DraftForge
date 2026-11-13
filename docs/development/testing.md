# Testing

## Test Environment Setup

```bash
just test::setup
```

This command:

1. Updates npm and Python dependencies
2. Builds Docker images
3. Populates test database
4. Starts test containers

## Playwright E2E Tests (Recommended)

Playwright is the recommended E2E testing framework with parallel execution and better performance.

### Quick Start

```bash
# Install browsers (first time only)
just test::pw::install

# Run all tests headless
just test::pw::headless

# Open interactive UI mode
just test::pw::ui
```

### Run Specific Test Suites

```bash
just test::pw::spec navigation    # Navigation tests
just test::pw::spec tournament    # Tournament tests
just test::pw::spec draft         # Draft tests
just test::pw::spec bracket       # Bracket tests
just test::pw::spec league        # League tests
just test::pw::spec herodraft     # HeroDraft tests
just test::pw::spec mobile        # Mobile responsive tests
just test::pw::dota-lobby         # dota_lobby integration (needs `just test::dota-lobby up`)
```

### Performance Options

```bash
# Run with specific worker count
just test::pw::headless --workers=4

# Run specific shard (for debugging CI)
just test::pw::headless --shard=1/4
```

### Debugging

```bash
# Debug mode with inspector
just test::pw::debug

# View HTML report
just test::pw::report
```

See [Playwright Testing Guide](../testing/playwright.md) for comprehensive documentation.

## Cypress E2E Tests (Legacy)

### Interactive Mode

```bash
just test::pw::ui
```

Opens Playwright UI for interactive debugging.

### Headless Mode

```bash
just test::pw::headless
```

Runs all tests in headless mode (CI/CD).

### Run Specific Test Specs

```bash
just test::pw::spec draft        # Run draft tests only
just test::pw::spec tournament   # Run tournament tests
just test::pw::spec navigation   # Run navigation tests
```

Available spec shortcuts:

| Shortcut | Pattern |
|----------|---------|
| `drafts` | `tests/cypress/e2e/07-draft/**/*.cy.ts` |
| `tournament` | `tests/cypress/e2e/04-tournament/**/*.cy.ts` |
| `tournaments` | `tests/cypress/e2e/03-tournaments/**/*.cy.ts` |
| `navigation` | `tests/cypress/e2e/01-*.cy.ts` |
| `mobile` | `tests/cypress/e2e/06-mobile/**/*.cy.ts` |

## Test Location

### Playwright (Recommended)

```
frontend/tests/playwright/
├── e2e/           # Test specs organized by feature
├── fixtures/      # Test fixtures and auth helpers
├── helpers/       # Page objects and utilities
└── global-setup.ts # Pre-test data caching
```

### Cypress (Legacy)

```
frontend/tests/cypress/
├── e2e/           # Test specs
├── fixtures/      # Test data
└── support/       # Custom commands
```

## Authentication Helpers

Custom Cypress commands for authentication:

```typescript
cy.loginUser()           // Regular user
cy.loginStaff()          // Staff user
cy.loginAdmin()          // Admin user
cy.loginAsUser(userPk)   // Login as specific user by PK
```

### Login As User

For testing captain-specific flows, use `loginAsUser` to login as any user:

```typescript
// Login as captain to test draft picks
cy.loginAsUser(captainPk).then(() => {
  cy.visit(`/tournament/${tournamentPk}?draft=open`)
  // Draft modal auto-opens, captain can pick
})
```

### Get Tournament by Key

For tests that need specific tournament configurations:

```typescript
cy.getTournamentByKey('captain_draft_test').then((response) => {
  const tournamentPk = response.body.pk
  cy.visit(`/tournament/${tournamentPk}`)
})
```

## API Testing Pattern

```typescript
import { apiBasePath } from '~/components/api/axios'

cy.loginAdmin().then(() => {
  cy.request('POST', `${apiBasePath}/items/`, { name: 'Test' })
  cy.visit('/')
  cy.contains('Test').should('exist')
})
```

## Best Practices

!!! tip "Real Backend Testing"
    This project tests against the real backend. Don't stub API calls with `cy.intercept()` for E2E tests.

- Use `cy.request()` for setup/teardown
- Import `apiBasePath` from axios config
- Use stable selectors (`data-testid`, `id`)
- Keep tests isolated and independent

## Backend Tests

```bash
just test::run 'python manage.py test -v 2'                   # whole suite, same as CI
just test::run 'python manage.py test app.tests -v 2'         # one package
just test::run 'python manage.py test app.tests.test_bracket -v 2'  # one module
```

The `Backend tests` job in `.github/workflows/playwright.yml` runs
`python manage.py test` with no labels. `BackendDiscoverRunner` (`backend/backend/test_runner.py`)
anchors discovery at `backend/`, so every `test*.py` module in a package
(a directory with `__init__.py`) under `backend/` runs, including the top-level
`backend/tests/` package. New test modules are picked up without editing the workflow.

`just py::test` runs the same modules with pytest on the host (`backend/pytest.ini`,
`backend/conftest.py`): same temp-file test DB and `DOTA_LOBBY_*` defaults as
`BackendDiscoverRunner`, with `docker/.env.test` loaded. Like the container it needs
Redis, on `localhost:6379`. `just test::run 'python -m pytest'` runs it in the container.

Write backend tests as Django/unittest `TestCase` or `SimpleTestCase` classes.
The Django runner doesn't collect bare pytest `def test_*` functions, so CI
would never run them.

## Worktree Testing Verification

When working in a git worktree (e.g., `.worktrees/feature-name`), you **must** verify the full stack works before completing the branch (merge, PR, or discard).

### Why Worktrees Need Special Attention

- Worktrees have isolated environments with separate databases
- Each worktree runs its **own** test stack in a slot, so several worktrees can test at once (see [Test Stack Slots](test-stack-slots.md))
- Unit tests alone don't catch integration issues (database, Docker, nginx routing)
- The test environment verifies frontend-backend integration works

!!! warning "Merge main first"
    Worktrees on branches without test stack slots still run the old
    `test::down` (stops every container on the host) and `test::upd` (takes
    over project `df`). Merge main into a worktree before using its test stack.

### Required Verification Steps

From the worktree root directory:

```bash
cd /home/kettle/git_repos/draftforge/.worktrees/feature-name

# 1. See which slot and URL this worktree uses (allocates one if needed)
just test::slot

# 2. Stop this worktree's test stack, if it runs (scoped to its slot)
just test::down

# 3. Run full test setup (builds images, installs deps)
just test::setup

# 4. Run database migrations for test environment
just db::migrate::test

# 5. Populate test data
just db::populate::all

# 6. Run backend tests in Docker
just test::run 'python manage.py test app.tests -v 2'

# 7. Start test environment
just test::upd

# 8. Run Playwright smoke tests (recommended)
just test::pw::headless
```

Playwright reads the base URL from `docker/.env.slot`; never hardcode
`https://localhost`.

### Quick Verification (Minimum)

If full Playwright tests aren't required, at minimum:

1. Run `just test::upd` and verify containers start without errors
2. Open the URL `just test::slot` prints (`https://localhost` on slot 0, `https://localhost:1N443` on slot N), in a separate browser profile per slot
3. Verify login works and pages load without database errors
4. Check browser console for JavaScript errors

### Common Issues

| Issue | Solution |
|-------|----------|
| Database errors on page load | Run `just db::migrate::test` and `just db::populate::all` |
| Container won't start | Run `just test::down` then `just test::setup` |
| WebSocket connection failed | Check nginx config routes `/api/` correctly (WebSockets use /api/ paths) |
| Missing dependencies | Run `just test::setup` to rebuild images |
| `No test-stack slot for this worktree` | Run `just test::slot` (Playwright never allocates a slot itself) |
| `slot N now belongs to <path>` | Another worktree took this slot; run `just test::slot` to get a new one |
| Which stack is on which port? | `just test::slots` |
