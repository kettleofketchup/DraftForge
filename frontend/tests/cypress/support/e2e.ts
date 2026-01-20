// ***********************************************************
// This example support/e2e.ts is processed and
// loaded automatically before your test files.
//
// This is a great place to put global configuration and
// behavior that modifies Cypress.
//
// You can change the location of this file or turn off
// automatically serving support files with the
// 'supportFile' configuration option.
//
// You can read more here:
// https://on.cypress.io/configuration
// ***********************************************************

// Import commands.js using ES2015 syntax:
import './commands';

// Note: cypress-runner-themes and cypress/react are only needed for component testing
// For E2E testing, we don't need these imports

// Alternatively you can use CommonJS syntax:
// require('./commands')
// Hide fetch/XHR requests from the command log for cleaner output
const app = window.top;
if (!app?.document.head.querySelector('[data-hide-command-log-request]')) {
  const style = app?.document.createElement('style');
  if (style) {
    style.innerHTML =
      '.command-name-request, .command-name-xhr { display: none }';
    style.setAttribute('data-hide-command-log-request', '');
    app?.document.head.appendChild(style);
  }
}

// Set global defaults
Cypress.config('defaultCommandTimeout', 10000);
Cypress.config('requestTimeout', 10000);
Cypress.config('responseTimeout', 10000);

// Handle React hydration issues
beforeEach(() => {
  // Suppress React hydration warnings in tests
  cy.window().then((win) => {
    const originalConsoleError = win.console.error;
    win.console.error = (...args) => {
      const message = args[0]?.toString() || '';

      // Filter out hydration-related warnings/errors
      if (
        message.includes('Hydration failed') ||
        message.includes('hydration failed') ||
        message.includes('Text content does not match') ||
        message.includes('Expected server HTML to contain') ||
        message.includes('Warning: Text content did not match') ||
        message.includes('Minified React error')
      ) {
        // Log for debugging but don't fail the test
        console.log('Suppressed hydration warning:', message);
        return;
      }

      // Call original console.error for other errors
      originalConsoleError.apply(win.console, args);
    };
  });
});

// Add global error handling
Cypress.on('uncaught:exception', (err, runnable) => {
  // Prevent Cypress from failing on uncaught exceptions
  // Return false only for known acceptable errors
  console.log('Uncaught exception:', err.message);

  // Add patterns for errors that should not fail tests
  const ignoredErrors = [
    'ResizeObserver loop limit exceeded',
    'ResizeObserver loop completed with undelivered notifications',
    'Non-Error promise rejection captured',
    'Script error',
    'Hydration failed because the server rendered HTML',
    'hydration failed',
    'Hydration failed',
    'Text content does not match server-rendered HTML',
    'Expected server HTML to contain',
    'Warning: Text content did not match',
    'Warning: Expected server HTML to contain',
    'Minified React error',
    'net::ERR_ABORTED 404',
    'Failed to load resource',
    'FiraCode-VF.woff2',
    'fonts.googleapis.com',
    'font loading',
    "server rendered HTML didn't match the client",
    'This can happen if a SSR-ed Client Component used',
    'Variable input such as',
    "Date formatting in a user's locale",
    'External changing data without sending a snapshot',
    'Invalid HTML tag nesting',
    'browser extension installed which messes with the HTML',
  ];

  return !ignoredErrors.some((ignoredError) =>
    err.message.includes(ignoredError),
  );
});
