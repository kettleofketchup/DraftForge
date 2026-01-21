/**
 * Hero Draft Full Flow E2E Tests
 *
 * Tests the complete hero draft (Captain's Mode) lifecycle using
 * Real Tournament 38's Winners Final game (vrm.mtl vs ethan0688_).
 *
 * Uses cy.session() for fast captain identity switching.
 */

import {
  suppressHydrationErrors,
  visitAndWaitForHydration,
} from '../../support/utils';
import {
  CAPTAIN_RADIANT,
  CAPTAIN_DIRE,
  switchToCaptainRadiant,
  switchToCaptainDire,
  clearHeroDraftSessions,
} from '../../helpers/herodraft-sessions';
import {
  waitForHeroDraftModal,
  assertWaitingPhase,
  assertRollingPhase,
  assertChoosingPhase,
  assertDraftingPhase,
  assertPausedState,
  clickReadyButton,
  clickFlipCoinButton,
  selectWinnerChoice,
  selectLoserChoice,
  clickHero,
  confirmHeroSelection,
  waitForDraftState,
  getGraceTime,
  assertHeroUnavailable,
} from '../../helpers/herodraft';

describe('Hero Draft Full Flow (e2e)', () => {
  let tournamentPk: number;
  let gamePk: number;
  let heroDraftPk: number;

  before(() => {
    // Get Real Tournament 38 (should be pk 1 after populate reorder)
    cy.getTournamentByKey('real_tournament').then((response) => {
      tournamentPk = response.body.pk;
      // Find Winners Final game (round 2, winners bracket)
      // This is vrm.mtl vs ethan0688_
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/bracket/tournaments/${tournamentPk}/`,
      }).then((bracketResponse) => {
        const games = bracketResponse.body.games || [];
        // Find the pending Winners Final (round 2, winners bracket)
        const winnersFinal = games.find(
          (g: any) =>
            g.round === 2 &&
            g.bracket_type === 'winners' &&
            g.status === 'pending',
        );
        if (winnersFinal) {
          gamePk = winnersFinal.pk;
        } else {
          throw new Error('Winners Final game not found in Real Tournament 38');
        }
      });
    });
  });

  beforeEach(() => {
    suppressHydrationErrors();
  });

  describe('Setup', () => {
    it('should create hero draft for Winners Final game', () => {
      // Login as admin to create draft
      cy.loginAdmin();

      // Create hero draft via API
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/api/herodraft/game/${gamePk}/create/`,
      }).then((response) => {
        expect(response.status).to.be.oneOf([200, 201]);
        heroDraftPk = response.body.pk;
        expect(response.body.state).to.eq('waiting_for_captains');
      });
    });
  });

  describe('Waiting Phase', () => {
    beforeEach(() => {
      // Reset draft to waiting state before each test
      cy.loginAdmin();
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/tests/herodraft/${heroDraftPk}/reset/`,
      });
    });

    it('should show waiting phase when captain visits draft', () => {
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      assertWaitingPhase(cy);
    });

    it('should allow Captain Radiant to ready up (logged to events)', () => {
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);

      clickReadyButton(cy);

      // Verify ready state via API (logged to events)
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
      }).then((response) => {
        const events = response.body;
        const readyEvent = events.find(
          (e: { event_type: string }) => e.event_type === 'captain_ready',
        );
        expect(readyEvent).to.exist;
      });
    });

    it('should allow Captain Dire to ready up (logged to events)', () => {
      // First, radiant readies
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      // Then dire readies
      switchToCaptainDire(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      // Verify both ready events logged
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
      }).then((response) => {
        const events = response.body;
        const readyEvents = events.filter(
          (e: { event_type: string }) => e.event_type === 'captain_ready',
        );
        expect(readyEvents.length).to.eq(2);
      });
    });

    it('should transition to rolling when both captains ready', () => {
      // Radiant readies
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      // Dire readies
      switchToCaptainDire(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      // Should now be in rolling phase
      waitForDraftState(cy, 'rolling');
      assertRollingPhase(cy);
    });
  });
});
