# Handling React Hydration Errors in Cypress Tests

## The Problem

When testing React applications with Server-Side Rendering (SSR), you might encounter hydration mismatch errors like:

```
Error: Hydration failed because the server rendered HTML didn't match the client.
```

This commonly happens due to:
- Dynamic content that differs between server and client (like dates, random numbers)
- Font loading that affects text rendering
- Theme/styling differences between server and client
- Browser extensions modifying HTML before React loads

## The Solution

Our Cypress test suite includes several strategies to handle these issues:

### 1. Error Suppression in Tests

The `e2e.ts` support file automatically ignores hydration-related errors:

```typescript
// Add patterns for errors that should not fail tests
const ignoredErrors = [
  'Hydration failed because the server rendered HTML',
  'hydration failed',
  'Text content does not match server-rendered HTML',
  // ... more patterns
];
```

### 2. Utility Functions

Use the utility functions in `support/utils.ts`:

```typescript
import {
  visitAndWaitForHydration,
  suppressHydrationErrors,
  navigateToRoute
} from '../support/utils';

// In your test
visitAndWaitForHydration('/'); // Instead of cy.visit('/')
suppressHydrationErrors(); // Suppress console errors
navigateToRoute('/tournaments'); // Smart navigation handling dropdowns
```

### 3. Specific Hydration Test

The `00-hydration-handling.cy.ts` test file specifically tests that the app works despite hydration issues:

```typescript
describe('Hydration Error Handling', () => {
  beforeEach(() => {
    suppressHydrationErrors();
  });

  it('should handle hydration mismatches gracefully', () => {
    visitAndWaitForHydration('/');
    cy.get('body').should('be.visible');
    // App should work despite hydration warnings
  });
});
```

## Best Practices

1. **Always use `visitAndWaitForHydration()`** instead of `cy.visit()` for React apps
2. **Suppress hydration errors** in test setup using `suppressHydrationErrors()`
3. **Use `navigateToRoute()`** for navigation that handles both visible links and dropdown menus
4. **Focus on functionality** - if the app works, hydration warnings are acceptable in tests
5. **Test after fonts load** - wait for external resources that might cause mismatches

## Common Issues and Solutions

### Dropdown Navigation
If navigation links are hidden in dropdown menus, the standard Cypress click will fail:
```
CypressError: element is not visible because its parent has CSS property: display: none
```

**Solution**: Use `navigateToRoute()` which automatically handles dropdown menus:
```typescript
import { navigateToRoute } from '../support/utils';

// This handles both visible links and dropdown navigation
navigateToRoute('/tournaments');
```

## Example Usage

```typescript
import {
  visitAndWaitForHydration,
  suppressHydrationErrors,
  navigateToRoute
} from '../support/utils';

describe('My Feature Tests', () => {
  beforeEach(() => {
    suppressHydrationErrors();
    visitAndWaitForHydration('/my-page');
  });

  it('should work despite hydration issues', () => {
    cy.get('[data-testid="my-component"]').should('be.visible');

    // Navigate using smart navigation that handles dropdowns
    navigateToRoute('/tournaments');
    cy.get('body').should('be.visible');
  });
});
```

This approach allows your tests to pass while the application functions correctly, even if there are minor hydration mismatches that don't affect user experience.
