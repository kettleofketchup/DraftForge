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
    // Clear cookies/session before each test
    cy.clearCookies();
    cy.clearLocalStorage();
  });

  describe('Draft Notifications', () => {
    it('should show floating draft indicator when captain has active turn', () => {
      // Login as captain
      cy.loginAsUser(captainPk).then(() => {
        // Visit any page
        cy.visit('/');
        cy.waitForHydration();

        // Check for floating indicator
        getFloatingDraftIndicator(cy).should('be.visible');
        getFloatingDraftIndicator(cy).should('contain.text', 'Your turn to pick!');
      });
    });

    it('should show notification badge on user avatar when captain has active turn', () => {
      cy.loginAsUser(captainPk).then(() => {
        cy.visit('/');
        cy.waitForHydration();

        // Check for notification badge
        getDraftNotificationBadge(cy).should('be.visible');
      });
    });

    it('should NOT show notifications for non-captain users', () => {
      // Login as regular staff
      cy.loginStaff();
      cy.visit('/');
      cy.waitForHydration();

      // Should not have floating indicator (unless they're also a captain)
      cy.get('[data-testid="floating-draft-indicator"]').should('not.exist');
    });
  });

  describe('Draft Modal Auto-Open', () => {
    it('should auto-open draft modal when visiting tournament with ?draft=open', () => {
      cy.loginAsUser(captainPk).then(() => {
        visitTournamentWithDraftOpen(cy, tournamentPk);

        // Modal should be open
        cy.get('[role="dialog"]').should('be.visible');
        cy.get('[role="dialog"]').should('contain.text', 'Tournament Draft');
      });
    });

    it('should navigate to tournament and open draft when clicking floating indicator', () => {
      cy.loginAsUser(captainPk).then(() => {
        cy.visit('/');
        cy.waitForHydration();

        // Click floating indicator
        getFloatingDraftIndicator(cy).click();

        // Should navigate to tournament with draft open
        cy.url().should('include', `/tournaments/${tournamentPk}`);
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

    it('should allow captain to pick a player', () => {
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

      // Should see waiting message, not pick buttons
      cy.get('[data-testid="available-player"]')
        .first()
        .parent()
        .should('contain.text', 'Waiting for');
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
        // Should be forbidden
        expect(response.status).to.be.oneOf([403, 401]);
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
        .should('be.visible');
    });
  });
});
