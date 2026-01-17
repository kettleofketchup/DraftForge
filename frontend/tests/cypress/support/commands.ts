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

// Extend Cypress namespace for custom commands
declare namespace Cypress {
  interface Chainable {
    /**
     * Custom command to login via UI
     * @example cy.login('user@example.com', 'password')
     */
    login(email: string, password: string): void;

    /**
     * Custom command to login via API
     * @example cy.loginAdmin()
     */
    loginAdmin(): void;
    loginStaff(): void;
    loginUser(): void;

    /**
     * Custom command to login as a specific user by primary key (TEST ONLY)
     * @example cy.loginAsUser(123)
     */
    loginAsUser(userPk: number): Chainable<Cypress.Response<{ user_id: number; username: string }>>;

    /**
     * Custom command to get tournament details by test config key (TEST ONLY)
     * @example cy.getTournamentByKey('captain_draft_test')
     */
    getTournamentByKey(key: string): Chainable<Cypress.Response<{ pk: number; name: string }>>;

    /**
     * Custom command to logout
     * @example cy.logout()
     */
    logout(): void;

    /**
     * Custom command to wait for API calls to complete
     * @example cy.waitForApi()
     */
    waitForApi(): void;

    /**
     * Custom command to visit a route and wait for it to load
     * @example cy.visitAndWait('/tournaments')
     */
    visitAndWait(url: string): void;

    /**
     * Custom command to check if element is visible in viewport
     * @example cy.get('.element').isInViewport()
     */
    isInViewport(): Chainable<JQuery<HTMLElement>>;

    /**
     * Custom command to wait for React hydration to complete
     * @example cy.waitForHydration()
     */
    waitForHydration(): void;

    /**
     * Custom command to visit and wait for React app to be ready
     * @example cy.visitAndWaitForReact('/tournaments')
     */
    visitAndWaitForReact(url: string): void;
  }
}

// Login via API (faster for test setup)
Cypress.Commands.add('loginAdmin', () => {
  cy.request({
    method: 'POST',
    url: `${Cypress.env('apiUrl')}/tests/login-admin/`,
  }).then((response) => {
    // Store the auth token if returned

    if (response.headers.cookiescsrftoken) {
      window.cookieStore.set(
        'csrftoken',
        response.headers.cookiescsrftoken as string,
      );
    }
    if (response.headers.cookiesessionid) {
      window.cookieStore.set(
        'sessionid',
        response.headers.cookiesessionid as string,
      );
    }
  });
});

Cypress.Commands.add('loginStaff', () => {
  cy.request({
    method: 'POST',
    url: `${Cypress.env('apiUrl')}/tests/login-staff/`,
  }).then((response) => {
    // Store the auth token if returned

    if (response.headers.cookiescsrftoken) {
      window.cookieStore.set(
        'csrftoken',
        response.headers.cookiescsrftoken as string,
      );
    }
    if (response.headers.cookiesessionid) {
      window.cookieStore.set(
        'sessionid',
        response.headers.cookiesessionid as string,
      );
    }
  });
});

Cypress.Commands.add('loginUser', () => {
  cy.request({
    method: 'POST',
    url: `${Cypress.env('apiUrl')}/tests/login-user/`,
  }).then((response) => {
    // Store the auth token if returned

    if (response.headers.cookiescsrftoken) {
      window.cookieStore.set(
        'csrftoken',
        response.headers.cookiescsrftoken as string,
      );
    }
    if (response.headers.cookiesessionid) {
      window.cookieStore.set(
        'sessionid',
        response.headers.cookiesessionid as string,
      );
    }
  });
});

// Login as specific user by primary key (TEST ONLY)
Cypress.Commands.add('loginAsUser', (userPk: number) => {
  return cy.request({
    method: 'POST',
    url: `${Cypress.env('apiUrl')}/tests/login-as/`,
    body: { user_pk: userPk },
    headers: {
      'Content-Type': 'application/json',
    },
  }).then((response) => {
    if (response.headers.cookiescsrftoken) {
      window.cookieStore.set(
        'csrftoken',
        response.headers.cookiescsrftoken as string,
      );
    }
    if (response.headers.cookiesessionid) {
      window.cookieStore.set(
        'sessionid',
        response.headers.cookiesessionid as string,
      );
    }
    return response;
  });
});

// Get tournament by test config key (TEST ONLY)
Cypress.Commands.add('getTournamentByKey', (key: string) => {
  return cy.request({
    method: 'GET',
    url: `${Cypress.env('apiUrl')}/tests/tournament-by-key/${key}/`,
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
  cy.window().then((win) => {
    const bottom = win.innerHeight;
    const right = win.innerWidth;
    const element = subject[0] as HTMLElement;
    const rect = element.getBoundingClientRect();

    expect(rect.top).to.be.at.least(0);
    expect(rect.left).to.be.at.least(0);
    expect(rect.bottom).to.be.at.most(bottom);
    expect(rect.right).to.be.at.most(right);
  });

  return subject;
});

// Wait for React hydration to complete
Cypress.Commands.add('waitForHydration', () => {
  // Wait for DOM to be stable (body should be visible)
  cy.get('body').should('be.visible');

  // Wait for document ready state to be complete
  cy.window().then((win) => {
    cy.wrap(null).should(() => {
      expect(win.document.readyState).to.eq('complete');
    });
  });

  // Wait for app root to be hydrated (React Router app structure)
  // Look for common React app indicators like navigation or main content
  cy.get('[data-slot], nav, main, #root', { timeout: 10000 }).should('exist');

  // Give React a moment to finish hydration
  cy.wait(200);
});

// Visit and wait for React app to be ready
Cypress.Commands.add('visitAndWaitForReact', (url: string) => {
  cy.visit(url);
  cy.waitForHydration();
  cy.get('body').should('be.visible');
});
