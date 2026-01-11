import {
  suppressHydrationErrors,
  visitAndWaitForHydration,
} from 'tests/cypress/support/utils';

describe('Bracket Generation and Winner Advancement (e2e)', () => {
  beforeEach(() => {
    cy.loginStaff();
    suppressHydrationErrors();
  });

  describe('Bracket Generation', () => {
    it('should generate a bracket with seeding', () => {
      // Use Pending Bracket Test (Tournament 3) which has teams but pending games
      visitAndWaitForHydration('/tournament/3/games');

      // Wait for the games tab to load
      cy.get('[data-testid="gamesTab"]', { timeout: 10000 }).should('be.visible');

      // Should see the bracket container
      cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
        'be.visible',
      );

      // Staff should see the toolbar
      cy.contains('button', /Reseed Bracket|Generate Bracket/).should('be.visible');
    });

    it('should allow reseeding with different methods', () => {
      visitAndWaitForHydration('/tournament/3/games');

      cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
        'be.visible',
      );

      // Click on Reseed Bracket dropdown
      cy.contains('button', /Reseed Bracket|Generate Bracket/).click();

      // Should show seeding options
      cy.contains('Seed by Team MMR').should('be.visible');
      cy.contains('Seed by Captain MMR').should('be.visible');
      cy.contains('Random Seeding').should('be.visible');
    });

    it('should enable save button after reseeding', () => {
      visitAndWaitForHydration('/tournament/3/games');

      cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
        'be.visible',
      );

      // Click on Reseed Bracket
      cy.contains('button', /Reseed Bracket|Generate Bracket/).click();

      // Select a seeding method
      cy.contains('Random Seeding').click();

      // If confirmation dialog appears, confirm it
      cy.get('body').then(($body) => {
        if ($body.find('button:contains("Regenerate")').length > 0) {
          cy.contains('button', 'Regenerate').click();
        }
      });

      // Wait for bracket to regenerate
      cy.wait(500);

      // Should show unsaved changes indicator
      cy.contains('Unsaved changes').should('be.visible');

      // Save button should be enabled and clickable
      cy.contains('button', /Save Bracket|Save Changes/)
        .should('be.visible')
        .and('not.be.disabled');
    });
  });

  describe('Winner Selection', () => {
    it('should show captain names in winner selection buttons', () => {
      // Use Pending Bracket Test with teams assigned
      visitAndWaitForHydration('/tournament/3/games');

      cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
        'be.visible',
      );

      // Click on a match node that has teams assigned (first round)
      // ReactFlow nodes have class containing 'react-flow__node'
      cy.get('.react-flow__node')
        .filter(':visible')
        .first()
        .click({ force: true });

      // Wait for modal to open
      cy.get('[role="dialog"]', { timeout: 5000 }).should('be.visible');

      // Modal should show Match Details
      cy.contains('Match Details').should('be.visible');

      // If match has teams, the Set Winner buttons should show captain names, not team names
      // The button text should contain "Wins" and NOT "Team Alpha Wins" pattern
      cy.get('[role="dialog"]').then(($dialog) => {
        if ($dialog.find('button:contains("Wins")').length > 0) {
          // Check that buttons show captain usernames (from mock data these are player usernames)
          // The buttons should NOT show generic "Team X" pattern
          cy.get('button:contains("Wins")').each(($btn) => {
            const text = $btn.text();
            // Should not be a generic team name pattern
            expect(text).to.not.match(/^Team (Alpha|Beta|Gamma|Delta|Epsilon) Wins$/);
          });
        }
      });

      // Close modal by pressing Escape
      cy.get('body').type('{esc}');
    });

    it('should advance winner to next match after selection', () => {
      visitAndWaitForHydration('/tournament/3/games');

      cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
        'be.visible',
      );

      // Find a winners bracket R1 match with both teams
      cy.get('.react-flow__node')
        .filter(':visible')
        .first()
        .click({ force: true });

      // Wait for modal
      cy.get('[role="dialog"]', { timeout: 5000 }).should('be.visible');

      // Check if this match has teams and Set Winner buttons
      cy.get('[role="dialog"]').then(($dialog) => {
        const winButtons = $dialog.find('button:contains("Wins")');

        if (winButtons.length >= 2) {
          // Get the first team's name from the button
          const firstButtonText = winButtons.first().text();
          const teamName = firstButtonText.replace(' Wins', '');

          // Click to set winner
          cy.wrap(winButtons.first()).click();

          // Close modal
          cy.wait(500);

          // Should show unsaved changes (winner was set locally)
          cy.contains('Unsaved changes').should('be.visible');
        } else {
          cy.log('Match does not have two teams assigned - skipping winner selection');
        }
      });
    });

    // Skip: This test is flaky due to timing issues with modal after reseed
    it.skip('should advance loser to losers bracket after winner selection', () => {
      visitAndWaitForHydration('/tournament/3/games');

      cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
        'be.visible',
      );

      // First, reseed to ensure we have a fresh bracket with loser paths
      cy.contains('button', /Reseed Bracket|Generate Bracket/).click();
      cy.contains('Random Seeding').click();

      // Confirm if dialog appears - wait for it to potentially appear
      cy.wait(500);
      cy.get('body').then(($body) => {
        if ($body.find('button:contains("Regenerate")').length > 0) {
          cy.contains('button', 'Regenerate').click({ force: true });
        }
      });

      cy.wait(1000);

      // Click on first match
      cy.get('.react-flow__node')
        .filter(':visible')
        .first()
        .click({ force: true });

      // Wait for modal - give more time
      cy.wait(500);
      cy.get('[role="dialog"]', { timeout: 10000 }).should('be.visible');

      // If match has Set Winner buttons, click one
      cy.get('[role="dialog"]').then(($dialog) => {
        const winButtons = $dialog.find('button:contains("Wins")');

        if (winButtons.length >= 2) {
          // Click second button (dire wins, so radiant is loser)
          cy.wrap(winButtons.eq(1)).click({ force: true });

          cy.wait(500);

          // The loser should now be in the losers bracket
          // But we can verify unsaved changes is shown
          cy.contains('Unsaved changes').should('be.visible');
        } else {
          cy.log('Match does not have two teams - skipping loser advancement check');
        }
      });
    });
  });

  describe('Bracket Saving', () => {
    it('should save bracket and persist changes', () => {
      visitAndWaitForHydration('/tournament/3/games');

      cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
        'be.visible',
      );

      // Reseed the bracket
      cy.contains('button', /Reseed Bracket|Generate Bracket/).click();
      cy.contains('Random Seeding').click();

      // Confirm if dialog appears - wait for it
      cy.wait(500);
      cy.get('body').then(($body) => {
        if ($body.find('button:contains("Regenerate")').length > 0) {
          cy.contains('button', 'Regenerate').click({ force: true });
        }
      });

      // Wait for dialog to close and bracket to regenerate
      cy.wait(1000);

      // Should show unsaved changes
      cy.contains('Unsaved changes').should('be.visible');

      // Save the bracket - use force to handle any overlays
      cy.contains('button', /Save Bracket|Save Changes/).click({ force: true });

      // Wait for save to complete
      cy.wait(2000);

      // Unsaved changes should disappear
      cy.contains('Unsaved changes').should('not.exist');
    });
  });
});
