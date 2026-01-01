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
cy.loginUser()   // Regular user
cy.loginStaff()  // Staff user
cy.loginAdmin()  # Admin user
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
