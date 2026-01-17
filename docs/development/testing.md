# Testing

## Test Environment Setup

```bash
source .venv/bin/activate
inv test.setup
```

This command:

1. Updates npm and Python dependencies
2. Builds Docker images
3. Populates test database
4. Starts test containers

## Cypress E2E Tests

### Interactive Mode

```bash
inv test.open
```

Opens Cypress Test Runner for interactive debugging.

### Headless Mode

```bash
inv test.headless
```

Runs all tests in headless mode (CI/CD).

### Run Specific Test Specs

```bash
inv test.spec --spec drafts      # Run draft tests only
inv test.spec --spec tournament  # Run tournament tests
inv test.spec --spec navigation  # Run navigation tests
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
source .venv/bin/activate
cd backend
python manage.py test
```

## Worktree Testing Verification

When working in a git worktree (e.g., `.worktrees/feature-name`), you **must** verify the full stack works before completing the branch (merge, PR, or discard).

### Why Worktrees Need Special Attention

- Worktrees have isolated environments with separate databases
- Unit tests alone don't catch integration issues (database, Docker, nginx routing)
- The test environment verifies frontend-backend integration works

### Required Verification Steps

From the worktree root directory:

```bash
cd /home/kettle/git_repos/website/.worktrees/feature-name

# 1. Source the worktree's virtual environment
source .venv/bin/activate

# 2. Stop any existing test environment
inv test.down

# 3. Run full test setup (builds images, installs deps)
inv test.setup

# 4. Run database migrations for test environment
inv db.migrate.test

# 5. Populate test data
inv db.populate.all

# 6. Run backend tests in Docker
inv test.run --cmd 'python manage.py test app.tests -v 2'

# 7. Start test environment
inv test.up

# 8. Run Cypress smoke tests
inv test.headless
```

### Quick Verification (Minimum)

If full Cypress tests aren't required, at minimum:

1. Run `inv test.up` and verify containers start without errors
2. Navigate to `https://localhost` in browser
3. Verify login works and pages load without database errors
4. Check browser console for JavaScript errors

### Common Issues

| Issue | Solution |
|-------|----------|
| Database errors on page load | Run `inv db.migrate.test` and `inv db.populate.all` |
| Container won't start | Run `inv test.down` then `inv test.setup` |
| WebSocket connection failed | Check nginx config routes `/ws/` correctly |
| Missing dependencies | Run `inv test.setup` to rebuild images |
