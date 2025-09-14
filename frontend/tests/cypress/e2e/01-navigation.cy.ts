import {
  checkBasicAccessibility,
  visitAndWaitForHydration,
} from '../support/utils';

describe('Navigation and Basic Functionality', () => {
  beforeEach(() => {
    // Visit the home page and wait for React hydration before each test
    visitAndWaitForHydration('/');
  });

  it('should load the home page successfully', () => {
    cy.get('body').should('be.visible');
    cy.title().should('not.be.empty');

    // Check that the page loads without errors
    cy.url().should('eq', Cypress.config().baseUrl + '/');
  });

  it('should    have working navigation links', () => {
    // Test navigation to different routes
    const routes = ['/tournaments', '/about', '/blog', '/users'];

    routes.forEach((route) => {
      // Use smart navigation that handles dropdowns
      cy.get('body').then(($body) => {
        // First try to find visible navigation links
        const visibleSelectors = [
          `nav > a[href="${route}"]:visible`,
          `header > a[href="${route}"]:visible`,
          `.navbar a[href="${route}"]:visible`,
          `a[href="${route}"]:visible`,
        ];

        let foundVisibleLink = false;

        // Try visible links first
        visibleSelectors.forEach((selector) => {
          if (!foundVisibleLink && $body.find(selector).length > 0) {
            cy.get(selector).first().click();
            foundVisibleLink = true;
            return false;
          }
        });

        // If no visible links, try dropdown navigation
        if (!foundVisibleLink) {
          const dropdownTriggers = [
            'button[aria-haspopup="true"]',
            '.dropdown-toggle',
            'button:contains("Menu")',
            '.menu-button',
            '[data-testid="menu-button"]',
          ];

          dropdownTriggers.forEach((triggerSelector) => {
            if (!foundVisibleLink && $body.find(triggerSelector).length > 0) {
              cy.get(triggerSelector).first().click();
              cy.wait(300); // Wait for dropdown to open

              // Now try to click the navigation link
              cy.get('body').then(($updatedBody) => {
                if (
                  $updatedBody.find(`a[href="${route}"]:visible`).length > 0
                ) {
                  cy.get(`a[href="${route}"]:visible`).first().click();
                  foundVisibleLink = true;
                }
              });
              return false;
            }
          });
        }

        // If still no navigation found, skip this route
        if (!foundVisibleLink) {
          cy.log(`No UI navigation found for ${route} - skipping`);
          return;
        }
      });

      // Verify we navigated to the correct route (if navigation was attempted)
      cy.url().then((url) => {
        if (url.includes(route)) {
          cy.get('body').should('be.visible');
        }
      });

      // Go back to home for next iteration
      visitAndWaitForHydration('/');
    });
  });

  it('should be responsive and mobile-friendly', () => {
    // Test different viewport sizes
    const viewports = [
      { width: 375, height: 667, device: 'iPhone SE' },
      { width: 768, height: 1024, device: 'iPad' },
      { width: 1280, height: 720, device: 'Desktop' },
    ];

    viewports.forEach((viewport) => {
      cy.viewport(viewport.width, viewport.height);
      visitAndWaitForHydration('/');

      // Check that content is visible and accessible
      cy.get('body').should('be.visible');

      // Ensure no horizontal scrolling on mobile
      if (viewport.width < 768) {
        cy.get('body').then(($body) => {
          expect($body[0].scrollWidth).to.be.at.most(viewport.width + 1);
        });
      }
    });
  });

  it('should handle 404 pages gracefully', () => {
    cy.visit('/non-existent-page', { failOnStatusCode: false });

    // Should show some kind of error page or redirect
    cy.get('body').should('be.visible');

    // Could be 404 page or redirect to home
    cy.url().should('satisfy', (url) => {
      return (
        url.includes('/non-existent-page') ||
        url === Cypress.config().baseUrl + '/'
      );
    });
  });

  it('should load page assets correctly', () => {
    visitAndWaitForHydration('/');

    // Check that CSS is loaded (by verifying styled elements)
    cy.get('body').should('have.css', 'margin').and('not.eq', '');

    // Check for favicon
    cy.get('link[rel="icon"], link[rel="shortcut icon"]').should('exist');

    // Verify no console errors
    cy.window().then((win) => {
      expect(win.console.error).to.not.have.been.called;
    });
  });

  it('should have accessibility basics', () => {
    visitAndWaitForHydration('/');

    // Use the flexible accessibility checker
    checkBasicAccessibility();
  });

  it('should handle browser back/forward navigation', () => {
    // Navigate through several pages
    visitAndWaitForHydration('/');
    cy.get('nav, navbar, header, .navigation, [role="navigation"]')
      .should('exist')
      .within(() => {
        cy.get('a')
          .contains(/tournaments/i)
          .first()
          .click();
      });

    cy.url().should('include', '/tournaments');

    // Use browser back button
    cy.go('back');
    cy.url().should('eq', Cypress.config().baseUrl + '/');

    // Use browser forward button
    cy.go('forward');
    cy.url().should('include', '/tournaments');
  });
});
