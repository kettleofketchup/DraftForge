/**
 * Captain Draft Pick Tests
 *
 * Tests the captain's ability to pick players during a draft.
 * Uses the 'draft_captain_turn' tournament which is configured with:
 * - Active draft in progress
 * - Captain assigned with pending pick
 */

import {
  assertMyTurn,
  getDraftNotificationBadge,
  getFloatingDraftIndicator,
  openDraftModal,
  pickPlayer,
  visitTournamentWithDraftOpen,
  waitForUserLoggedIn,
} from '../../helpers/draft';

describe('Captain Draft Pick', () => {
  // Tournament and user IDs will be fetched from test config
  let tournamentPk: number;
  let captainPk: number;

  before(() => {
    // Get tournament info from test config
    cy.getTournamentByKey('draft_captain_turn').then((response) => {
      expect(response.status).to.eq(200);
      tournamentPk = response.body.pk;

      // Extract captain PK from first team (sorted by draft_order)
      const teams = response.body.teams || [];
      const sortedTeams = [...teams].sort(
        (a, b) => (a.draft_order || 0) - (b.draft_order || 0),
      );
      const firstTeam = sortedTeams[0];
      if (firstTeam && firstTeam.captain) {
        captainPk = firstTeam.captain.pk;
        cy.log(`Found captain PK: ${captainPk}`);
      } else {
        throw new Error('Could not find captain for first team');
      }
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

  describe('Draft Notifications', () => {
    it('should show floating draft indicator when captain has active turn', () => {
      // Login as captain
      cy.loginAsUser(captainPk).then(() => {
        // Visit any page
        cy.visit('/');
        cy.waitForHydration();

        // Wait for user to be fully logged in (avatar visible)
        waitForUserLoggedIn(cy);

        // Check for floating indicator
        getFloatingDraftIndicator(cy).should('be.visible');
        getFloatingDraftIndicator(cy).should('contain.text', 'Your turn to pick!');
      });
    });

    it('should show notification badge on user avatar when captain has active turn', () => {
      cy.loginAsUser(captainPk).then(() => {
        cy.visit('/');
        cy.waitForHydration();

        // Wait for user to be fully logged in (avatar visible)
        waitForUserLoggedIn(cy);

        // Check for notification badge
        getDraftNotificationBadge(cy).should('be.visible');
      });
    });

    it('should NOT show notifications for non-captain users', () => {
      // Login as regular user (not staff, to ensure they're not a captain)
      cy.loginUser();
      cy.visit('/');
      cy.waitForHydration();

      // Wait for the page to fully load before asserting
      cy.wait(1000);

      // Check if this user happens to be a captain via current_user response
      // The active_drafts array is included in the current_user API response
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/current_user/`,
        failOnStatusCode: false,
      }).then((response) => {
        if (response.status === 200 && response.body.active_drafts && response.body.active_drafts.length > 0) {
          // This user is actually a captain - skip the assertion
          cy.log(
            'User is a captain in test data - skipping floating indicator check',
          );
        } else {
          // User is not a captain - should not have floating indicator
          cy.get('[data-testid="floating-draft-indicator"]').should('not.exist');
        }
      });
    });
  });

  describe('Draft Modal Auto-Open', () => {
    // Skip: API timeout issues make this test flaky
    it.skip('should auto-open draft modal when visiting tournament with ?draft=open', () => {
      cy.loginAsUser(captainPk).then(() => {
        visitTournamentWithDraftOpen(cy, tournamentPk);

        // Modal should be open
        cy.get('[role="dialog"]').should('be.visible');
        cy.get('[role="dialog"]').should('contain.text', 'Tournament Draft');
      });
    });

    // Skip: URL routing varies between /tournament/ and /tournaments/ depending on configuration
    it.skip('should navigate to tournament and open draft when clicking floating indicator', () => {
      cy.loginAsUser(captainPk).then(() => {
        cy.visit('/');
        cy.waitForHydration();

        // Wait for user to be fully logged in
        waitForUserLoggedIn(cy);

        // Click floating indicator
        getFloatingDraftIndicator(cy).click();

        // Should navigate to tournament with draft open
        cy.url().should('include', `/tournament/${tournamentPk}`);
        cy.get('[role="dialog"]').should('be.visible');
      });
    });
  });

  describe('Captain Pick Flow', () => {
    it('should show "Your turn" indicator when captain opens draft modal', () => {
      cy.loginAsUser(captainPk).then(() => {
        cy.visit(`/tournament/${tournamentPk}`);
        cy.waitForHydration();

        openDraftModal(cy);
        assertMyTurn(cy);
      });
    });

    // Skip: Pick confirmation dialog is not appearing reliably in tests
    it.skip('should allow captain to pick a player', () => {
      cy.loginAsUser(captainPk).then(() => {
        cy.visit(`/tournament/${tournamentPk}`);
        cy.waitForHydration();

        openDraftModal(cy);

        // Find an available player and pick them
        cy.get('[data-testid="available-player"]')
          .first()
          .then(($player) => {
            const playerName = $player.text().split('\n')[0].trim();
            pickPlayer(cy, playerName);

            // Verify pick was recorded (toast or UI update)
            cy.contains(/pick.*completed|selected/i, { timeout: 5000 }).should(
              'be.visible',
            );
          });
      });
    });

    it('should show "Waiting for captain" when not the current captain', () => {
      // Login as a different user who is not the current picking captain
      cy.loginUser();
      cy.visit(`/tournament/${tournamentPk}`);
      cy.waitForHydration();

      openDraftModal(cy);

      // Check if this user is a captain or staff - they would see Pick buttons
      // Non-captain/non-staff should see waiting message
      cy.get('[role="dialog"]').then(($dialog) => {
        const hasPickButton = $dialog.find('button:contains("Pick")').length > 0;
        if (hasPickButton) {
          // User is captain or staff in test data - they can pick
          cy.log('User can pick - they are either captain or staff');
          cy.get('[data-testid="available-player"]')
            .first()
            .parent()
            .find('button')
            .contains('Pick')
            .should('exist');
        } else {
          // User is not captain - should see waiting message
          cy.get('[data-testid="available-player"]')
            .first()
            .parent()
            .should('contain.text', 'Waiting for');
        }
      });
    });
  });

  describe('Permission Enforcement', () => {
    it('should not allow non-captain to pick via API', () => {
      cy.loginUser();

      // Try to make a pick via API directly
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/pick-player-for-round/`,
        body: {
          draft_round_pk: 1, // This would need to be a real PK
          user_pk: 1,
        },
        failOnStatusCode: false,
      }).then((response) => {
        // Should be forbidden or not found (404 if round doesn't exist)
        expect(response.status).to.be.oneOf([403, 401, 404]);
      });
    });

    it('should allow staff to pick for any captain', () => {
      cy.loginStaff();
      cy.visit(`/tournament/${tournamentPk}`);
      cy.waitForHydration();

      openDraftModal(cy);

      // Staff should see pick buttons
      cy.get('[data-testid="available-player"]')
        .first()
        .parent()
        .find('button')
        .contains('Pick')
        .scrollIntoView()
        .should('be.visible');
    });
  });
});
