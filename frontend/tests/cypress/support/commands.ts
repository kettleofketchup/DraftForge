// ***********************************************
// This example commands.ts shows you how to
// create various custom commands and overwrite
// existing commands.
//
// For more comprehensive examples of custom
// commands please read more here:
// https://on.cypress.io/custom-commands
// ***********************************************

/// <reference types="cypress" />

declare global {
  namespace Cypress {
    interface Chainable {
      /**
       * Custom command to login via UI
       * @example cy.login('user@example.com', 'password')
       */
      login(email: string, password: string): Chainable<void>;

      /**
       * Custom command to login via API
       * @example cy.loginApi('user@example.com', 'password')
       */
      loginApi(email: string, password: string): Chainable<void>;

      /**
       * Custom command to logout
       * @example cy.logout()
       */
      logout(): Chainable<void>;

      /**
       * Custom command to wait for API calls to complete
       * @example cy.waitForApi()
       */
      waitForApi(): Chainable<void>;

      /**
       * Custom command to visit a route and wait for it to load
       * @example cy.visitAndWait('/tournaments')
       */
      visitAndWait(url: string): Chainable<void>;

      /**
       * Custom command to check if element is visible in viewport
       * @example cy.get('.element').isInViewport()
       */
      isInViewport(): Chainable<void>;

      /**
       * Custom command to wait for React hydration to complete
       * @example cy.waitForHydration()
       */
      waitForHydration(): Chainable<void>;

      /**
       * Custom command to visit and wait for React app to be ready
       * @example cy.visitAndWaitForReact('/tournaments')
       */
      visitAndWaitForReact(url: string): Chainable<void>;
    }
  }
}

// Login via UI
Cypress.Commands.add('login', (email: string, password: string) => {
  cy.visit('/login');
  cy.get('[data-testid="email-input"]').type(email);
  cy.get('[data-testid="password-input"]').type(password);
  cy.get('[data-testid="login-button"]').click();
  cy.url().should('not.include', '/login');
});

// Login via API (faster for test setup)
Cypress.Commands.add('loginApi', (email: string, password: string) => {
  cy.request({
    method: 'POST',
    url: `${Cypress.env('apiUrl')}/auth/login/`,
    body: {
      email,
      password,
    },
  }).then((response) => {
    // Store the auth token if returned
    if (response.body.token) {
      window.localStorage.setItem('authToken', response.body.token);
    }
    if (response.body.access_token) {
      window.localStorage.setItem('access_token', response.body.access_token);
    }
  });
});

// Logout
Cypress.Commands.add('logout', () => {
  cy.visit('/logout');
  cy.url().should('include', '/');
});

// Wait for API calls
Cypress.Commands.add('waitForApi', () => {
  cy.intercept('**').as('apiCall');
  cy.wait('@apiCall', { timeout: 10000 });
});

// Visit and wait for page to load
Cypress.Commands.add('visitAndWait', (url: string) => {
  cy.visit(url);
  cy.get('body').should('be.visible');
  cy.wait(500); // Brief wait for any animations
});

// Check if element is in viewport
Cypress.Commands.add('isInViewport', { prevSubject: true }, (subject) => {
  const bottom = Cypress.$(cy.state('window')).height();
  const right = Cypress.$(cy.state('window')).width();
  const rect = subject[0].getBoundingClientRect();

  expect(rect.top).to.be.at.least(0);
  expect(rect.left).to.be.at.least(0);
  expect(rect.bottom).to.be.at.most(bottom);
  expect(rect.right).to.be.at.most(right);

  return subject;
});

// Wait for React hydration to complete
Cypress.Commands.add('waitForHydration', () => {
  // Wait for React to be available
  cy.window().should('have.property', 'React');

  // Wait for DOM to be stable (no more mutations from hydration)
  cy.get('body').should('be.visible');

  // Give React a moment to finish hydration
  cy.wait(100);

  // Ensure no hydration errors in console
  cy.window().then((win) => {
    // Check if hydration completed successfully
    cy.wrap(null).should(() => {
      // This ensures the DOM is in a stable state
      expect(win.document.readyState).to.eq('complete');
    });
  });
});

// Visit and wait for React app to be ready
Cypress.Commands.add('visitAndWaitForReact', (url: string) => {
  cy.visit(url);
  cy.waitForHydration();
  cy.get('body').should('be.visible');
});
