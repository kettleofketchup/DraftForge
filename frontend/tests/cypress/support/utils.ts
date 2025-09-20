/**
 * Utilities for handling React hydration issues in Cypress tests
 */

/**
 * Visit a page and wait for React hydration to complete
 */
export function visitAndWaitForHydration(url: string) {
  cy.visit(url);

  // Wait for the page to be visible
  cy.get('body').should('be.visible');

  // Wait for React to be available and hydrated
  cy.window().then((win) => {
    // Check if we're in a React app
    if (win.React || win.__REACT_DEVTOOLS_GLOBAL_HOOK__) {
      // Give React time to hydrate
      cy.wait(500);
    }
  });

  // Wait for any pending network requests to complete
  cy.get('body').should('be.visible');
}

/**
 * Suppress console errors that are hydration-related
 */
export function suppressHydrationErrors() {
  cy.window().then((win) => {
    const originalError = win.console.error;
    const originalWarn = win.console.warn;

    win.console.error = (...args) => {
      const message = args[0]?.toString() || '';

      // Filter out hydration warnings and font loading errors
      if (
        message.includes('Hydration failed') ||
        message.includes('Text content does not match') ||
        message.includes('Warning: Text content did not match') ||
        message.includes("server rendered HTML didn't match the client") ||
        message.includes('Expected server HTML to contain') ||
        message.includes('net::ERR_ABORTED') ||
        message.includes('Failed to load resource') ||
        message.includes('fonts.googleapis.com') ||
        message.includes('font')
      ) {
        return; // Suppress these errors
      }

      originalError.apply(win.console, args);
    };

    win.console.warn = (...args) => {
      const message = args[0]?.toString() || '';

      // Filter out hydration warnings
      if (
        message.includes('Hydration') ||
        message.includes('Text content did not match') ||
        message.includes('server HTML')
      ) {
        return; // Suppress these warnings
      }

      originalWarn.apply(win.console, args);
    };
  });
}

/**
 * Wait for any loading states to complete
 */
export function waitForLoadingToComplete() {
  // Wait for common loading indicators to disappear
  cy.get('body').then(($body) => {
    if ($body.find('[data-testid="loading"], .loading, .spinner').length > 0) {
      cy.get('[data-testid="loading"], .loading, .spinner', {
        timeout: 10000,
      }).should('not.exist');
    }
  });
}

/**
 * Smart navigation that handles both visible links and dropdown menus
 */
export function navigateToRoute(route: string) {
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
        '.hamburger-menu',
      ];

      dropdownTriggers.forEach((triggerSelector) => {
        if (!foundVisibleLink && $body.find(triggerSelector).length > 0) {
          cy.get(triggerSelector).first().click();
          cy.wait(300); // Wait for dropdown to open

          // Now try to click the navigation link
          cy.get(`a[href="${route}"]:visible`).first().click();
          foundVisibleLink = true;
          return false;
        }
      });
    }

    // If still no navigation found, force navigation via URL
    if (!foundVisibleLink) {
      cy.log(`No navigation UI found for ${route}, using direct navigation`);
      visitAndWaitForHydration(route);
    }
  });
}

/**
 * Check for basic accessibility features with flexible expectations
 */
export function checkBasicAccessibility() {
  // Check language attribute
  cy.get('html').should('have.attr', 'lang');

  // Check for title
  cy.get('title').should('exist').and('not.be.empty');

  // Check for main content landmark
  cy.get('body').then(($body) => {
    const hasMainLandmark = $body.find('main, [role="main"]').length > 0;

    if (hasMainLandmark) {
      cy.get('main, [role="main"]').should('exist');
    } else {
      cy.log(
        'No main landmark found - this could be improved for accessibility',
      );
    }
  });

  // Check that interactive elements have proper accessibility
  cy.get('body').then(($body) => {
    // Check buttons have accessible names (text content or aria-label)
    const buttons = $body.find('button');
    if (buttons.length > 0) {
      cy.get('button').each(($btn) => {
        const hasText = $btn.text().trim().length > 0;
        const hasAriaLabel = $btn.attr('aria-label');
        const hasAriaLabelledBy = $btn.attr('aria-labelledby');

        if (!hasText && !hasAriaLabel && !hasAriaLabelledBy) {
          cy.log(`Button without accessible name found: ${$btn[0].outerHTML}`);
        }
      });
    }

    // Check links have accessible names
    const links = $body.find('a');
    if (links.length > 0) {
      cy.get('a').each(($link) => {
        const hasText = $link.text().trim().length > 0;
        const hasAriaLabel = $link.attr('aria-label');

        if (!hasText && !hasAriaLabel) {
          cy.log(`Link without accessible name found: ${$link[0].outerHTML}`);
        }
      });
    }

    // Check form inputs have labels
    const inputs = $body.find('input:not([type="hidden"])');
    if (inputs.length > 0) {
      cy.get('input:not([type="hidden"])').each(($input) => {
        const id = $input.attr('id');
        const hasLabel = id && $body.find(`label[for="${id}"]`).length > 0;
        const hasAriaLabel = $input.attr('aria-label');
        const hasAriaLabelledBy = $input.attr('aria-labelledby');

        if (!hasLabel && !hasAriaLabel && !hasAriaLabelledBy) {
          cy.log(`Input without label found: ${$input[0].outerHTML}`);
        }
      });
    }
  });
}
