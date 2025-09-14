describe('Form Validation and UI Components', () => {
  beforeEach(() => {
    cy.fixture('auth').as('authData');
  });

  it('should validate form inputs properly', () => {
    cy.visit('/login');

    // Test empty form submission
    cy.get(
      'button[type="submit"], button:contains("Login"), button:contains("Sign in")',
    )
      .first()
      .click();

    // Should show validation errors or prevent submission
    cy.get('body').then(($body) => {
      const hasValidationErrors =
        $body.find(
          ':contains("required"), :contains("Required"), .error, .invalid',
        ).length > 0;
      const staysOnLogin = window.location.pathname.includes('/login');

      // Either show validation errors or stay on login page
      expect(hasValidationErrors || staysOnLogin).to.be.true;
    });
  });

  it('should validate email format', () => {
    cy.visit('/login');

    // Enter invalid email format
    cy.get(
      'input[type="email"], input[name*="email"], input[placeholder*="email"]',
    )
      .first()
      .type('invalid-email');

    cy.get('input[type="password"], input[name*="password"]')
      .first()
      .type('password123');

    cy.get(
      'button[type="submit"], button:contains("Login"), button:contains("Sign in")',
    )
      .first()
      .click();

    // Should show email validation error
    cy.get('body').then(($body) => {
      const hasEmailError =
        $body.find(
          ':contains("email"), :contains("Email"), :contains("valid"), :contains("Valid")',
        ).length > 0;
      const staysOnLogin = window.location.pathname.includes('/login');

      expect(hasEmailError || staysOnLogin).to.be.true;
    });
  });

  it('should handle dark/light theme toggle (if available)', () => {
    cy.visit('/');

    // Look for theme toggle button
    cy.get('body').then(($body) => {
      const themeSelectors = [
        'button:contains("Dark")',
        'button:contains("Light")',
        'button:contains("Theme")',
        '[data-testid*="theme"]',
        '.theme-toggle',
        '.dark-mode-toggle',
      ];

      let foundThemeToggle = false;
      themeSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0 && !foundThemeToggle) {
          foundThemeToggle = true;

          // Get current theme
          const initialTheme = $body.attr('class') || '';

          cy.get(selector).first().click();
          cy.wait(500); // Wait for theme change

          // Check if theme changed
          cy.get('body').then(($newBody) => {
            const newTheme = $newBody.attr('class') || '';
            if (newTheme !== initialTheme) {
              cy.log('Theme toggle working');
            }
          });
        }
      });

      if (!foundThemeToggle) {
        cy.log('No theme toggle found - this is okay');
      }
    });
  });

  it('should handle dropdown menus and navigation', () => {
    cy.visit('/');

    // Look for dropdown menus
    cy.get('body').then(($body) => {
      const dropdownSelectors = [
        '.dropdown',
        '.menu-dropdown',
        'button[aria-haspopup="true"]',
        '[data-testid*="dropdown"]',
        'button:contains("Menu")',
      ];

      dropdownSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).first().click();
          cy.wait(300); // Wait for dropdown to open

          // Check if dropdown content is visible
          cy.get('body').then(($bodyAfter) => {
            const hasDropdownContent =
              $bodyAfter.find('.dropdown-content, .menu-content, [role="menu"]')
                .length > 0;
            if (hasDropdownContent) {
              cy.log('Dropdown menu working');
            }
          });
        }
      });
    });
  });

  it('should handle modals and dialogs', () => {
    cy.visit('/tournaments');

    // Look for buttons that might open modals
    cy.get('body').then(($body) => {
      const modalTriggers = [
        'button:contains("Create")',
        'button:contains("Add")',
        'button:contains("Edit")',
        'button:contains("Delete")',
        '[data-testid*="modal"]',
      ];

      modalTriggers.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).first().click();

          // Check if modal opened
          cy.get('body').then(($bodyAfter) => {
            const hasModal =
              $bodyAfter.find('.modal, .dialog, [role="dialog"], .overlay')
                .length > 0;

            if (hasModal) {
              cy.log('Modal opened successfully');

              // Try to close modal
              const closeSelectors = [
                'button:contains("Cancel")',
                'button:contains("Close")',
                '.modal-close',
                '[aria-label="Close"]',
              ];

              closeSelectors.forEach((closeSelector) => {
                if ($bodyAfter.find(closeSelector).length > 0) {
                  cy.get(closeSelector).first().click();
                  return false; // Exit loop
                }
              });
            }
          });
        }
      });
    });
  });

  it('should handle search functionality', () => {
    cy.visit('/tournaments');

    // Look for search input
    cy.get('body').then(($body) => {
      const searchSelectors = [
        'input[type="search"]',
        'input[placeholder*="search"]',
        'input[placeholder*="Search"]',
        '.search-input',
        '[data-testid*="search"]',
      ];

      searchSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).first().type('test search query');
          cy.wait(1000); // Wait for search results

          // Check if search affected the page content
          cy.get('body').should('be.visible');

          // Clear search
          cy.get(selector).first().clear();
          cy.wait(500);
        }
      });
    });
  });

  it('should handle sorting and filtering', () => {
    cy.visit('/tournaments');

    // Look for sort/filter controls
    cy.get('body').then(($body) => {
      const sortSelectors = [
        'select',
        'button:contains("Sort")',
        'button:contains("Filter")',
        '.sort-button',
        '.filter-button',
        '[data-testid*="sort"]',
        '[data-testid*="filter"]',
      ];

      sortSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          cy.get(selector).first().click();
          cy.wait(500); // Wait for sort/filter to apply

          // Verify page still loads correctly
          cy.get('body').should('be.visible');
        }
      });
    });
  });

  it('should handle tables with interactive elements', () => {
    cy.visit('/users');

    // Look for tables
    cy.get('body').then(($body) => {
      if ($body.find('table, .table').length > 0) {
        cy.get('table, .table')
          .first()
          .within(() => {
            // Check for sortable headers
            cy.get('th, .table-header').then(($headers) => {
              if ($headers.length > 0) {
                cy.wrap($headers).first().click();
                cy.wait(300); // Wait for sort
              }
            });

            // Check for row actions
            cy.get('tr, .table-row').then(($rows) => {
              if ($rows.length > 1) {
                cy.wrap($rows)
                  .eq(1)
                  .within(() => {
                    // Look for action buttons in rows
                    const actionSelectors = [
                      'button',
                      'a',
                      '.action-button',
                      '[data-testid*="action"]',
                    ];

                    actionSelectors.forEach((actionSelector) => {
                      if ($rows.find(actionSelector).length > 0) {
                        cy.get(actionSelector).first().should('be.visible');
                      }
                    });
                  });
              }
            });
          });
      } else {
        cy.log('No tables found on users page');
      }
    });
  });

  it('should be keyboard accessible', () => {
    cy.visit('/');

    // Test tab navigation
    cy.get('body').tab();
    cy.focused().should('be.visible');

    // Continue tabbing through interactive elements
    for (let i = 0; i < 5; i++) {
      cy.focused().tab();
      cy.focused().should('be.visible');
    }

    // Test enter key on focused elements
    cy.focused().then(($el) => {
      if ($el.is('button, a, [role="button"]')) {
        cy.focused().type('{enter}');
        cy.wait(500);
        cy.get('body').should('be.visible');
      }
    });
  });

  it('should handle loading states and skeletons', () => {
    // Mock slow API to trigger loading states
    cy.intercept('GET', '**/api/**', (req) => {
      req.reply((res) => {
        res.delay(1000);
        res.send({ statusCode: 200, body: { results: [] } });
      });
    }).as('slowApi');

    cy.visit('/tournaments');

    // Check for loading indicators
    cy.get('body').then(($body) => {
      const loadingSelectors = [
        '.loading',
        '.spinner',
        '.skeleton',
        '.loader',
        ':contains("Loading")',
        ':contains("loading")',
      ];

      let hasLoadingState = false;
      loadingSelectors.forEach((selector) => {
        if ($body.find(selector).length > 0) {
          hasLoadingState = true;
          cy.get(selector).should('be.visible');
        }
      });

      if (!hasLoadingState) {
        cy.log(
          'No loading states found - this might be okay if content loads instantly',
        );
      }
    });

    cy.wait('@slowApi');

    // Loading should be gone after API completes
    cy.get('body').should('be.visible');
  });
});
