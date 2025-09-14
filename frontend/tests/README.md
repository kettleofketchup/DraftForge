# Cypress Testing Suite

This directory contains comprehensive Cypress tests for the frontend application.

## Setup

1. Install Cypress and dependencies:
```bash
npm install
```

2. Install Cypress binary:
```bash
npm run cypress:install
```

## Test Structure

```
tests/cypress/
├── e2e/                     # End-to-end tests
│   ├── 00-hydration-handling.cy.ts # React hydration error handling
│   ├── 01-navigation.cy.ts  # Navigation and basic functionality
│   ├── 01b-structure-accessibility.cy.ts # HTML structure and accessibility
│   ├── 02-tournaments.cy.ts # Tournament features
│   ├── 03-authentication.cy.ts # User auth and profile
│   ├── 04-api-integration.cy.ts # API integration tests
│   └── 05-ui-components.cy.ts # UI components and forms
├── component/               # Component tests (for future use)
├── fixtures/               # Test data
│   ├── auth.json          # Authentication test data
│   └── testData.json      # General test data
└── support/               # Support files
    ├── commands.ts        # Custom Cypress commands
    ├── e2e.ts            # E2E test setup
    ├── component.ts      # Component test setup
    └── utils.ts          # Utility functions for React apps
```

## Running Tests

### Interactive Mode (Recommended for Development)
```bash
# Open Cypress Test Runner for E2E tests
npm run test:e2e:open

# Open Cypress Test Runner for Component tests
npm run test:component:open
```

### Headless Mode (CI/Production)
```bash
# Run all E2E tests headlessly
npm run test:e2e

# Run E2E tests with browser visible
npm run test:e2e:headed

# Run component tests
npm run test:component
```

### Running Specific Tests
```bash
# Run specific test file
npx cypress run --spec "tests/cypress/e2e/01-navigation.cy.ts"

# Run tests matching pattern
npx cypress run --spec "tests/cypress/e2e/*authentication*"
```

## Test Configuration

The tests are configured via `cypress.config.ts` with the following key settings:

- **Base URL**: `http://localhost:3000` (frontend dev server)
- **API URL**: `http://localhost:8000/api` (backend API)
- **Viewport**: 1280x720 (configurable per test)
- **Timeouts**: 10 seconds for commands, 30 seconds for page loads

## Prerequisites

Before running tests, ensure:

1. **Frontend dev server is running**:
```bash
npm run dev
```

2. **Backend API is available** (for API integration tests):
```bash
# In backend directory
python manage.py runserver
```

## Test Features

### Hydration Handling Tests (`00-hydration-handling.cy.ts`)
- ✅ React hydration error suppression
- ✅ Font loading compatibility
- ✅ Theme application verification
- ✅ Client-side navigation after hydration
- ✅ Graceful handling of SSR mismatches

### Navigation Tests (`01-navigation.cy.ts`)
- ✅ Home page loading
- ✅ Navigation link functionality
- ✅ Responsive design testing
- ✅ 404 error handling
- ✅ Asset loading verification
- ✅ Basic accessibility checks
- ✅ Browser back/forward navigation

### Structure & Accessibility Tests (`01b-structure-accessibility.cy.ts`)
- ✅ HTML structure validation
- ✅ Semantic content containers
- ✅ Navigation structure detection
- ✅ Keyboard accessibility testing
- ✅ Visual contrast and visibility
- ✅ Responsive design across viewports

### Tournament Tests (`02-tournaments.cy.ts`)
- ✅ Tournament list display
- ✅ Individual tournament navigation
- ✅ Tournament detail views
- ✅ Tournament creation (if available)
- ✅ Bracket information display
- ✅ Search and filtering

### Authentication Tests (`03-authentication.cy.ts`)
- ✅ Login page functionality
- ✅ Form validation
- ✅ Valid/invalid login handling
- ✅ User profile display
- ✅ Users list navigation
- ✅ Logout functionality
- ✅ Protected route handling

### API Integration Tests (`04-api-integration.cy.ts`)
- ✅ Tournament API calls
- ✅ Error handling
- ✅ Authentication API
- ✅ User profile API
- ✅ Tournament creation API
- ✅ Pagination handling
- ✅ Loading states
- ✅ Concurrent requests

### UI Component Tests (`05-ui-components.cy.ts`)
- ✅ Form validation
- ✅ Theme toggling
- ✅ Dropdown menus
- ✅ Modal dialogs
- ✅ Search functionality
- ✅ Sorting and filtering
- ✅ Table interactions
- ✅ Keyboard accessibility
- ✅ Loading states and skeletons

## Custom Commands

The test suite includes custom Cypress commands defined in `support/commands.ts`:

```typescript
// Login via UI
cy.login('user@example.com', 'password')

// Login via API (faster for test setup)
cy.loginApi('user@example.com', 'password')

// Logout
cy.logout()

// Visit page and wait for loading
cy.visitAndWait('/tournaments')

// Check if element is in viewport
cy.get('.element').isInViewport()

// Wait for API calls
cy.waitForApi()
```

## Test Data

Test fixtures are located in `fixtures/`:

- `auth.json`: User credentials for authentication tests
- `testData.json`: Sample tournaments, users, and brackets

## Environment Variables

Set these in `cypress.config.ts` or via environment:

- `CYPRESS_baseUrl`: Frontend URL (default: http://localhost:3000)
- `CYPRESS_apiUrl`: Backend API URL (default: http://localhost:8000/api)

## CI/CD Integration

For continuous integration, use:

```yaml
# Example GitHub Actions
- name: Run Cypress Tests
  run: |
    npm install
    npm run cypress:install
    npm run test:e2e
```

## Debugging Tests

1. **Use Cypress Test Runner** for visual debugging:
```bash
npm run test:e2e:open
```

2. **Add debug commands** in tests:
```typescript
cy.debug()          // Pause execution
cy.pause()          // Pause with resume option
cy.screenshot()     // Take screenshot
cy.log('Debug message')  // Add log message
```

3. **View network requests** in Cypress Test Runner's Network tab

4. **Check browser console** for JavaScript errors

## Best Practices

1. **Use data-testid attributes** in components for reliable element selection
2. **Mock API responses** for consistent test results
3. **Use utility functions** for React apps - use `visitAndWaitForHydration()` instead of `cy.visit()`
4. **Handle hydration errors** - suppress SSR/client mismatches that don't affect functionality
5. **Keep tests independent** - each test should be able to run in isolation
6. **Use proper wait strategies** - avoid cy.wait() with fixed times

## React Hydration Issues

This test suite includes special handling for React hydration errors. See [HYDRATION.md](./HYDRATION.md) for detailed information.

**Quick fix for hydration errors:**
```typescript
import { visitAndWaitForHydration, suppressHydrationErrors } from '../support/utils';

describe('My Tests', () => {
  beforeEach(() => {
    suppressHydrationErrors();
    visitAndWaitForHydration('/my-page');
  });
});
```

## Contributing

When adding new tests:

1. Follow the existing naming convention (`XX-feature.cy.ts`)
2. Add test data to appropriate fixtures
3. Use `visitAndWaitForHydration()` for React apps
4. Include both positive and negative test cases
5. Update this README with new test descriptions

## Troubleshooting

### Common Issues

1. **Tests fail on first run**: Run `npm run cypress:install`
2. **API errors**: Ensure backend is running on correct port
3. **Element not found**: Check if app uses data-testid attributes
4. **Timeout errors**: Increase timeout in cypress.config.ts
5. **TypeScript errors**: Install `@types/cypress` if needed
6. **Hydration errors**: Use `visitAndWaitForHydration()` and `suppressHydrationErrors()` - see [HYDRATION.md](./HYDRATION.md)
7. **Font loading issues**: Wait for external resources or suppress related errors

### Getting Help

- Check [Cypress Documentation](https://docs.cypress.io/)
- Review test logs in Cypress Test Runner
- Check browser console for JavaScript errors
- For hydration issues, see [HYDRATION.md](./HYDRATION.md)
- Verify network requests in DevTools
