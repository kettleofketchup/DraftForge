/**
 * Undo Pick Tests
 *
 * Tests the staff ability to undo draft picks.
 * The undo button should only be visible to staff members
 * and should revert the last pick made in the draft.
 *
 * Uses 'completed_bracket' tournament from test config
 */

describe('Undo Pick', () => {
  let tournamentPk: number;

  before(() => {
    // Get tournament PK dynamically instead of hardcoding
    cy.getTournamentByKey('completed_bracket').then((response) => {
      expect(response.status).to.eq(200);
      tournamentPk = response.body.pk;
    });
  });

  beforeEach(() => {
    // Clear all storage to prevent stale user data from previous tests
    // The Zustand user store persists to sessionStorage
    cy.clearCookies();
    cy.clearLocalStorage();
    cy.window().then((win) => {
      win.sessionStorage.clear();
    });
  });

  describe('Undo Button Visibility', () => {
    it('should show undo button for staff when picks have been made', () => {
      // Login as admin/staff
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/tests/login-admin/`,
      });

      cy.visit(`/tournament/${tournamentPk}`);
      cy.get('body').should('be.visible');

      // Wait for page to load
      cy.contains('h1', 'Completed Bracket Test', { timeout: 10000 }).should(
        'be.visible',
      );

      // Click on Teams tab
      cy.contains('Teams (4)').click({ force: true });
      cy.wait(1000);

      // Open draft modal
      cy.contains('button', /Live Draft|Start Draft/i).click({ force: true });
      cy.wait(1000);

      cy.get('[role="dialog"]').should('be.visible');

      // Initialize draft if needed
      cy.get('body').then(($body) => {
        if ($body.find('button:contains("Restart Draft")').length > 0) {
          cy.contains('button', 'Restart Draft').click({ force: true });
          cy.wait(500);

          // Confirm if dialog appears
          cy.get('body').then(($body2) => {
            if ($body2.find('[role="alertdialog"]').length > 0) {
              cy.get('[role="alertdialog"]')
                .contains('button', /Confirm|Yes|Continue|Restart/i)
                .click({ force: true });
            }
          });

          cy.wait(2000);
        }
      });

      // Make a pick first
      cy.get('[role="dialog"]').then(($dialog) => {
        const pickButtons = $dialog.find('button:contains("Pick")');
        if (pickButtons.length > 0) {
          cy.wrap(pickButtons.first()).click({ force: true });
          cy.wait(500);

          // Confirm pick
          cy.get('body').then(($body) => {
            if ($body.find('[role="alertdialog"]').length > 0) {
              cy.get('[role="alertdialog"]')
                .contains('button', /Confirm|Yes|Pick/i)
                .click({ force: true });
            }
          });

          cy.wait(2000);
        }
      });

      // Now check for undo button
      cy.get('[role="dialog"]').should('be.visible');
      cy.get('[role="dialog"]')
        .contains('button', 'Undo')
        .should('be.visible');
    });

    it('should NOT show undo button for non-staff users', () => {
      // Login as regular user
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/tests/login-user/`,
      });

      cy.visit(`/tournament/${tournamentPk}`);
      cy.get('body').should('be.visible');

      // Wait for page to load
      cy.contains('h1', 'Completed Bracket Test', { timeout: 10000 }).should(
        'be.visible',
      );

      // Click on Teams tab
      cy.contains('Teams (4)').click({ force: true });
      cy.wait(1000);

      // Open draft modal
      cy.contains('button', /Live Draft|Start Draft/i).click({ force: true });
      cy.wait(1000);

      cy.get('[role="dialog"]').should('be.visible');

      // Undo button should not be visible for non-staff
      cy.get('[role="dialog"]')
        .contains('button', 'Undo')
        .should('not.exist');
    });

    it('should NOT show undo button when no picks have been made', () => {
      // Login as admin/staff
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/tests/login-admin/`,
      });

      cy.visit(`/tournament/${tournamentPk}`);
      cy.get('body').should('be.visible');

      // Wait for page to load
      cy.contains('h1', 'Completed Bracket Test', { timeout: 10000 }).should(
        'be.visible',
      );

      // Click on Teams tab
      cy.contains('Teams (4)').click({ force: true });
      cy.wait(1000);

      // Open draft modal
      cy.contains('button', /Live Draft|Start Draft/i).click({ force: true });
      cy.wait(1000);

      cy.get('[role="dialog"]').should('be.visible');

      // Restart draft to reset all picks
      cy.get('body').then(($body) => {
        if ($body.find('button:contains("Restart Draft")').length > 0) {
          cy.contains('button', 'Restart Draft').click({ force: true });
          cy.wait(500);

          // Confirm if dialog appears
          cy.get('body').then(($body2) => {
            if ($body2.find('[role="alertdialog"]').length > 0) {
              cy.get('[role="alertdialog"]')
                .contains('button', /Confirm|Yes|Continue|Restart/i)
                .click({ force: true });
            }
          });

          cy.wait(2000);
        }
      });

      // After restart, no picks should exist, so undo should not be visible
      cy.get('[role="dialog"]')
        .contains('button', 'Undo')
        .should('not.exist');
    });
  });

  describe('Undo Functionality', () => {
    it('should undo the last pick when confirmed', () => {
      // Login as admin/staff
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/tests/login-admin/`,
      });

      cy.visit(`/tournament/${tournamentPk}`);
      cy.get('body').should('be.visible');

      // Wait for page to load
      cy.contains('h1', 'Completed Bracket Test', { timeout: 10000 }).should(
        'be.visible',
      );

      // Click on Teams tab
      cy.contains('Teams (4)').click({ force: true });
      cy.wait(1000);

      // Open draft modal
      cy.contains('button', /Live Draft|Start Draft/i).click({ force: true });
      cy.wait(1000);

      cy.get('[role="dialog"]').should('be.visible');

      // Restart draft to start fresh
      cy.get('body').then(($body) => {
        if ($body.find('button:contains("Restart Draft")').length > 0) {
          cy.contains('button', 'Restart Draft').click({ force: true });
          cy.wait(500);

          cy.get('body').then(($body2) => {
            if ($body2.find('[role="alertdialog"]').length > 0) {
              cy.get('[role="alertdialog"]')
                .contains('button', /Confirm|Yes|Continue|Restart/i)
                .click({ force: true });
            }
          });

          cy.wait(2000);
        }
      });

      // Get the username of a player before picking
      let pickedPlayerName: string;

      cy.get('[role="dialog"]')
        .find('[data-testid="available-player"]')
        .first()
        .then(($player) => {
          // Get player name from the row
          pickedPlayerName = $player.text().split('\n')[0].trim();
          cy.log(`Will pick player: ${pickedPlayerName}`);

          // Make a pick
          cy.get('[role="dialog"]')
            .find('button:contains("Pick")')
            .first()
            .click({ force: true });
          cy.wait(500);

          // Confirm pick
          cy.get('body').then(($body) => {
            if ($body.find('[role="alertdialog"]').length > 0) {
              cy.get('[role="alertdialog"]')
                .contains('button', /Confirm|Yes|Pick/i)
                .click({ force: true });
            }
          });

          cy.wait(2000);

          // Now undo the pick - wait for button to appear first (confirms pick was recorded)
          cy.get('[role="dialog"]')
            .contains('button', 'Undo', { timeout: 10000 })
            .should('be.visible')
            .click({ force: true });

          // Confirm undo in the alert dialog
          cy.get('[role="alertdialog"]', { timeout: 10000 }).should('be.visible');
          cy.get('[role="alertdialog"]')
            .contains('button', 'Undo Pick')
            .click({ force: true });

          cy.wait(2000);

          // Verify success toast
          cy.contains(/Pick undone|successfully/i, { timeout: 5000 }).should(
            'be.visible',
          );

          // The player should be back in the available pool
          // Check that we can still make picks (draft round was reset)
          cy.get('[role="dialog"]')
            .find('button:contains("Pick")')
            .should('exist');
        });
    });

    it('should cancel undo when cancel is clicked', () => {
      // Login as admin/staff
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/tests/login-admin/`,
      });

      cy.visit(`/tournament/${tournamentPk}`);
      cy.get('body').should('be.visible');

      // Wait for page to load
      cy.contains('h1', 'Completed Bracket Test', { timeout: 10000 }).should(
        'be.visible',
      );

      // Click on Teams tab
      cy.contains('Teams (4)').click({ force: true });
      cy.wait(1000);

      // Open draft modal
      cy.contains('button', /Live Draft|Start Draft/i).click({ force: true });
      cy.wait(1000);

      cy.get('[role="dialog"]').should('be.visible');

      // Make a pick first
      cy.get('[role="dialog"]').then(($dialog) => {
        const pickButtons = $dialog.find('button:contains("Pick")');
        if (pickButtons.length > 0) {
          cy.wrap(pickButtons.first()).click({ force: true });
          cy.wait(500);

          // Confirm pick
          cy.get('body').then(($body) => {
            if ($body.find('[role="alertdialog"]').length > 0) {
              cy.get('[role="alertdialog"]')
                .contains('button', /Confirm|Yes|Pick/i)
                .click({ force: true });
            }
          });

          cy.wait(2000);
        }
      });

      // Click undo button
      cy.get('[role="dialog"]')
        .contains('button', 'Undo')
        .click({ force: true });
      cy.wait(500);

      // Click cancel in the alert dialog
      cy.get('[role="alertdialog"]').should('be.visible');
      cy.get('[role="alertdialog"]')
        .contains('button', 'Cancel')
        .click({ force: true });

      cy.wait(500);

      // Alert dialog should be closed
      cy.get('[role="alertdialog"]').should('not.exist');

      // Pick should NOT be undone - undo button should still be visible
      cy.get('[role="dialog"]')
        .contains('button', 'Undo')
        .should('be.visible');
    });
  });
});
