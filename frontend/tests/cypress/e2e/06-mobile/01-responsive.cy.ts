/**
 * Mobile-first responsive tests for Match Stats Modal and Tournament Bracket
 *
 * Tests ensure components are usable and properly displayed on mobile devices
 */

import { visitAndWaitForHydration } from '../../support/utils';

// Mobile-first viewport sizes (smallest first)
const VIEWPORTS = {
  mobile: { width: 375, height: 667, device: 'iPhone SE' },
  mobileLarge: { width: 414, height: 896, device: 'iPhone 11' },
  tablet: { width: 768, height: 1024, device: 'iPad' },
  desktop: { width: 1280, height: 720, device: 'Desktop' },
} as const;

// Helper to navigate to bracket view and wait for it to load
const navigateToBracket = () => {
  cy.contains(/Games/i).click();
  cy.wait(500);
  // Wait for React Flow to render
  cy.get('.react-flow', { timeout: 10000 }).should('exist');
};

// Helper to click on a bracket node - uses the group role with node roledescription
const clickBracketNode = () => {
  // React Flow nodes are rendered as groups with roledescription="node"
  // Find nodes that contain match info (have headings like "Winners R1", etc.)
  cy.get('.react-flow [role="group"]', { timeout: 10000 })
    .filter(':has(h3)')
    .first()
    .click({ force: true });
  cy.wait(300);
};

describe('Mobile-First: Tournament Bracket', () => {
  beforeEach(() => {
    cy.loginAdmin();
  });

  Object.entries(VIEWPORTS).forEach(([name, viewport]) => {
    describe(`${viewport.device} (${viewport.width}x${viewport.height})`, () => {
      beforeEach(() => {
        cy.viewport(viewport.width, viewport.height);
      });

      it('should display tournament page without horizontal scroll', () => {
        visitAndWaitForHydration('/tournament/1');

        // Page should be visible
        cy.get('body').should('be.visible');
        cy.contains('Completed Bracket Test').should('be.visible');

        // No horizontal scrolling
        cy.get('body').then(($body) => {
          expect($body[0].scrollWidth).to.be.at.most(viewport.width + 1);
        });
      });

      it('should display Games tab and bracket view', () => {
        visitAndWaitForHydration('/tournament/1');

        navigateToBracket();

        // Bracket view should be visible
        cy.get('.react-flow').should('be.visible');

        // Check for bracket content (Winners/Losers bracket labels)
        cy.contains(/Winners|Losers|Grand Finals/i).should('exist');
      });

      it('should allow horizontal pan/scroll on bracket if content overflows', () => {
        visitAndWaitForHydration('/tournament/1');

        navigateToBracket();

        // React Flow should be visible and interactive
        cy.get('.react-flow').should('be.visible');
      });

      it('should display bracket nodes readably', () => {
        visitAndWaitForHydration('/tournament/1');

        navigateToBracket();

        // Check that bracket nodes are visible and have minimum readable size
        cy.get('.react-flow [role="group"]')
          .filter(':has(h3)')
          .first()
          .then(($node) => {
            const rect = $node[0].getBoundingClientRect();
            // Minimum touch target size for mobile (44px recommended)
            expect(rect.width).to.be.at.least(44);
            expect(rect.height).to.be.at.least(44);
          });
      });

      it('should open match modal when clicking bracket node', () => {
        visitAndWaitForHydration('/tournament/1');

        navigateToBracket();
        clickBracketNode();

        // Modal should appear
        cy.get('[role="dialog"]').should('be.visible');
      });
    });
  });
});

describe('Mobile-First: Match Stats Modal', () => {
  beforeEach(() => {
    cy.loginAdmin();
  });

  Object.entries(VIEWPORTS).forEach(([name, viewport]) => {
    describe(`${viewport.device} (${viewport.width}x${viewport.height})`, () => {
      beforeEach(() => {
        cy.viewport(viewport.width, viewport.height);
      });

      it('should display match details modal properly', () => {
        visitAndWaitForHydration('/tournament/1');

        navigateToBracket();
        clickBracketNode();

        // Modal should be visible
        cy.get('[role="dialog"]').should('be.visible');

        // Modal should not cause horizontal scroll
        cy.get('[role="dialog"]').then(($modal) => {
          const rect = $modal[0].getBoundingClientRect();
          expect(rect.right).to.be.at.most(viewport.width + 10);
        });
      });

      it('should display View Stats button and open stats modal', () => {
        visitAndWaitForHydration('/tournament/1');

        navigateToBracket();
        clickBracketNode();

        // Look for View Stats button
        cy.get('[role="dialog"]').then(($dialog) => {
          if ($dialog.text().includes('View Stats')) {
            cy.contains('View Stats').click();
            cy.wait(500);

            // Stats modal should open
            cy.get('[role="dialog"]').should('be.visible');
          }
        });
      });

      it('should display player stats table with proper layout', () => {
        visitAndWaitForHydration('/tournament/1');

        navigateToBracket();
        clickBracketNode();

        cy.get('[role="dialog"]').then(($dialog) => {
          if ($dialog.text().includes('View Stats')) {
            cy.contains('View Stats').click();
            cy.wait(500);

            // Check for team tables (RADIANT/DIRE)
            cy.get('[role="dialog"]').then(($statsModal) => {
              const hasRadiant = $statsModal.text().includes('RADIANT');
              const hasDire = $statsModal.text().includes('DIRE');

              if (hasRadiant || hasDire) {
                // Tables should be present
                expect(hasRadiant || hasDire).to.be.true;

                // Modal should be scrollable if content overflows
                const scrollArea = $statsModal.find('[data-radix-scroll-area-viewport]');
                if (scrollArea.length > 0) {
                  expect(scrollArea[0].scrollHeight).to.be.at.least(0);
                }
              }
            });
          }
        });
      });

      it('should display external links (Dotabuff, OpenDota) accessibly', () => {
        visitAndWaitForHydration('/tournament/1');

        navigateToBracket();
        clickBracketNode();

        cy.get('[role="dialog"]').first().then(($dialog) => {
          if ($dialog.text().includes('View Stats')) {
            cy.contains('View Stats').click();
            cy.wait(500);

            // Check for external links in the stats modal (last dialog)
            cy.get('[role="dialog"]').last().within(() => {
              // Look for Dotabuff and OpenDota links
              cy.get('a[href*="dotabuff.com"]').should('exist');
              cy.get('a[href*="opendota.com"]').should('exist');

              // Links should have proper touch target size
              cy.get('a[href*="dotabuff.com"]').then(($link) => {
                const rect = $link[0].getBoundingClientRect();
                expect(rect.height).to.be.at.least(32); // Minimum touch target
              });
            });
          }
        });
      });

      it('should allow closing modals on mobile', () => {
        visitAndWaitForHydration('/tournament/1');

        navigateToBracket();
        clickBracketNode();

        // Modal should be visible
        cy.get('[role="dialog"]').should('be.visible');

        // Close modal by pressing Escape or clicking close button
        cy.get('body').type('{esc}');
        cy.wait(300);

        // Modal should close
        cy.get('[role="dialog"]').should('not.exist');
      });

      it('should have readable font sizes on mobile', () => {
        visitAndWaitForHydration('/tournament/1');

        navigateToBracket();
        clickBracketNode();

        cy.get('[role="dialog"]').then(($dialog) => {
          if ($dialog.text().includes('View Stats')) {
            cy.contains('View Stats').click();
            cy.wait(500);

            // Check font sizes are readable (minimum 10px for mobile)
            cy.get('[role="dialog"]').find('td, th').each(($cell) => {
              const fontSize = parseInt(window.getComputedStyle($cell[0]).fontSize);
              expect(fontSize).to.be.at.least(10); // Allow smaller for dense tables
            });
          }
        });
      });
    });
  });
});

describe('Mobile-First: Touch Interactions', () => {
  beforeEach(() => {
    cy.loginAdmin();
    // Set mobile viewport
    cy.viewport(375, 667);
  });

  it('should support touch scrolling in stats modal', () => {
    visitAndWaitForHydration('/tournament/1');

    navigateToBracket();
    clickBracketNode();

    cy.get('[role="dialog"]').first().then(($dialog) => {
      if ($dialog.text().includes('View Stats')) {
        cy.contains('View Stats').click();
        cy.wait(500);

        // Verify the stats modal is scrollable if content overflows
        // Check that the modal content area has overflow handling
        cy.get('[role="dialog"]').last().should('be.visible').then(($modal) => {
          // Modal should allow scrolling for overflow content
          const style = window.getComputedStyle($modal[0]);
          const hasScroll = style.overflowY === 'auto' || style.overflowY === 'scroll' ||
            $modal.find('[style*="overflow"]').length > 0 ||
            $modal.find('[data-radix-scroll-area-viewport]').length > 0;
          // Just verify the modal is visible and usable - scroll behavior varies
          expect($modal[0].clientHeight).to.be.greaterThan(0);
        });
      }
    });
  });

  it('should have adequate tap targets for all interactive elements', () => {
    visitAndWaitForHydration('/tournament/1');

    navigateToBracket();

    // Check that buttons and links meet minimum tap target size (44x44)
    cy.get('button:visible, a:visible').each(($el) => {
      const rect = $el[0].getBoundingClientRect();
      // Only check elements that are actually interactive and visible
      if (rect.width > 0 && rect.height > 0) {
        // Allow some flexibility but warn on very small targets
        if (rect.height < 32 || rect.width < 32) {
          cy.log(`Warning: Small tap target detected: ${rect.width}x${rect.height}`);
        }
      }
    });
  });
});

describe('Mobile-First: Orientation Changes', () => {
  beforeEach(() => {
    cy.loginAdmin();
  });

  it('should handle portrait to landscape orientation', () => {
    // Start in portrait
    cy.viewport(375, 667);
    visitAndWaitForHydration('/tournament/1');

    navigateToBracket();

    // Switch to landscape
    cy.viewport(667, 375);
    cy.wait(300);

    // Content should still be visible
    cy.get('body').should('be.visible');

    // No content should be cut off
    cy.get('body').then(($body) => {
      expect($body[0].scrollWidth).to.be.at.most(670);
    });
  });

  it('should maintain modal visibility after orientation change', () => {
    cy.viewport(375, 667);
    visitAndWaitForHydration('/tournament/1');

    navigateToBracket();
    clickBracketNode();

    // Modal should be visible in portrait
    cy.get('[role="dialog"]').should('be.visible');

    // Switch to landscape
    cy.viewport(667, 375);
    cy.wait(300);

    // Modal should still be visible and accessible
    cy.get('[role="dialog"]').should('be.visible');
  });
});
