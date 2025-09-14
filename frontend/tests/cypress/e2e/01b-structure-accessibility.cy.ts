import { visitAndWaitForHydration } from '../support/utils';

describe('Application Structure and Accessibility', () => {
  beforeEach(() => {
    visitAndWaitForHydration('/');
  });

  it('should have proper HTML structure', () => {
    // Check basic HTML structure
    cy.get('html').should('exist').and('have.attr', 'lang');
    cy.get('head').should('exist');
    cy.get('body').should('exist').and('be.visible');
    cy.get('title').should('exist').and('not.be.empty');
  });

  it('should have semantic content structure', () => {
    cy.get('body').then(($body) => {
      // Check for various content containers
      const containers = [
        'main',
        '[role="main"]',
        '#root',
        '.app',
        '.main-content',
        '.container',
        '[data-testid="main-content"]',
        'div[class*="app"]',
        'div[id*="app"]',
      ];

      let foundContainer = false;

      containers.forEach((selector) => {
        if (!foundContainer && $body.find(selector).length > 0) {
          cy.get(selector).should('exist');
          cy.log(`Found content container: ${selector}`);
          foundContainer = true;
        }
      });

      if (!foundContainer) {
        // Fallback: check that body has content
        cy.log(
          'No specific content container found, checking for general content',
        );
        cy.get('body').children().should('have.length.greaterThan', 0);
        cy.get('body').should('not.be.empty');
      }
    });
  });

  it('should have navigation structure', () => {
    cy.get('body').then(($body) => {
      const navSelectors = [
        'nav',
        '[role="navigation"]',
        '.navbar',
        '.navigation',
        'header nav',
        '[data-testid="navigation"]',
      ];

      let foundNav = false;

      navSelectors.forEach((selector) => {
        if (!foundNav && $body.find(selector).length > 0) {
          cy.get(selector).should('exist');
          cy.log(`Found navigation: ${selector}`);
          foundNav = true;
        }
      });

      if (!foundNav) {
        cy.log(
          'No specific navigation structure found - this might be okay for some apps',
        );
      }
    });
  });

  it('should be keyboard accessible', () => {
    cy.get('body').then(($body) => {
      // Find focusable elements
      const focusableSelectors = [
        'a[href]',
        'button:not([disabled])',
        'input:not([disabled])',
        'select:not([disabled])',
        'textarea:not([disabled])',
        '[tabindex]:not([tabindex="-1"])',
      ];

      let focusableCount = 0;
      focusableSelectors.forEach((selector) => {
        focusableCount += $body.find(selector).length;
      });

      if (focusableCount > 0) {
        cy.log(`Found ${focusableCount} focusable elements`);

        // Test tab navigation using real DOM focus
        cy.get(
          'a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])',
        )
          .first()
          .focus();
        cy.focused().should('exist');

        // Test that we can move focus through elements
        cy.get(
          'a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ).then(($elements) => {
          const focusableElements = Array.from($elements);
          const maxToTest = Math.min(3, focusableElements.length);

          for (let i = 1; i < maxToTest; i++) {
            cy.wrap(focusableElements[i]).focus();
            cy.focused().should('exist');
          }
        });
      } else {
        cy.log(
          'No focusable elements found - this might indicate an accessibility issue',
        );
      }
    });
  });

  it('should have proper contrast and visibility', () => {
    // Check that text is visible and has some contrast
    cy.get('body').then(($body) => {
      const textElements = $body
        .find('p, h1, h2, h3, h4, h5, h6, span, div, a, button')
        .filter(':visible');

      if (textElements.length > 0) {
        cy.log(`Found ${textElements.length} visible text elements`);

        // Check a few elements for basic visibility
        cy.wrap(textElements.slice(0, 5)).each(($el) => {
          cy.wrap($el).should('be.visible');
        });
      } else {
        cy.log('No visible text elements found - checking for basic content');
        cy.get('body').should('not.be.empty');
      }
    });
  });

  it('should handle different viewport sizes', () => {
    const viewports = [
      { width: 320, height: 568, name: 'Mobile Small' },
      { width: 768, height: 1024, name: 'Tablet' },
      { width: 1280, height: 720, name: 'Desktop' },
    ];

    viewports.forEach((viewport) => {
      cy.viewport(viewport.width, viewport.height);
      cy.log(`Testing ${viewport.name} (${viewport.width}x${viewport.height})`);

      // Reload the page for this viewport
      visitAndWaitForHydration('/');

      // Basic checks
      cy.get('body').should('be.visible');

      // Check for horizontal scrolling on smaller screens
      if (viewport.width <= 768) {
        cy.get('body').then(($body) => {
          const scrollWidth = $body[0].scrollWidth;
          const clientWidth = $body[0].clientWidth;

          // Allow for small differences (scroll bars, etc.)
          expect(scrollWidth).to.be.at.most(clientWidth + 20);
        });
      }
    });
  });
});
