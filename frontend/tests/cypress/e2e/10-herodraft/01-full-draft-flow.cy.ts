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

  describe('Rolling Phase', () => {
    beforeEach(() => {
      // Setup: get both captains ready
      cy.loginAdmin();
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/tests/herodraft/${heroDraftPk}/reset/`,
      });

      // Both captains ready up
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      switchToCaptainDire(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);
      waitForDraftState(cy, 'rolling');
    });

    it('should show coin flip UI in rolling phase', () => {
      assertRollingPhase(cy);
      cy.get('[data-testid="herodraft-flip-coin-button"]').should('be.visible');
    });

    it('should allow captain to trigger coin flip (logged to events)', () => {
      clickFlipCoinButton(cy);

      // Wait for roll result
      cy.wait(1000); // Allow animation

      // Verify roll events logged
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
      }).then((response) => {
        const events = response.body;
        const rollEvent = events.find(
          (e: { event_type: string }) =>
            e.event_type === 'roll_triggered' || e.event_type === 'roll_result',
        );
        expect(rollEvent).to.exist;
      });

      // Should transition to choosing phase
      waitForDraftState(cy, 'choosing');
    });
  });

  describe('Choosing Phase', () => {
    beforeEach(() => {
      // Setup: get to choosing phase
      cy.loginAdmin();
      cy.request({
        method: 'POST',
        url: `${Cypress.env('apiUrl')}/tests/herodraft/${heroDraftPk}/reset/`,
      });

      // Both ready
      switchToCaptainRadiant(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);

      switchToCaptainDire(cy);
      visitAndWaitForHydration(
        `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
      );
      waitForHeroDraftModal(cy);
      clickReadyButton(cy);
      waitForDraftState(cy, 'rolling');

      // Trigger roll
      clickFlipCoinButton(cy);
      waitForDraftState(cy, 'choosing');
    });

    it('should show choosing phase UI', () => {
      assertChoosingPhase(cy);
    });

    it('should allow roll winner to choose first pick (logged to events)', () => {
      // Get current draft to find roll winner
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
      }).then((response) => {
        const draft = response.body;
        const rollWinnerDiscordId =
          draft.roll_winner?.tournament_team?.captain?.discordId;

        // Switch to roll winner
        if (rollWinnerDiscordId === CAPTAIN_RADIANT.discordId) {
          switchToCaptainRadiant(cy);
        } else {
          switchToCaptainDire(cy);
        }

        visitAndWaitForHydration(
          `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
        );
        waitForHeroDraftModal(cy);

        // Winner chooses first pick
        selectWinnerChoice(cy, 'first_pick');

        // Verify choice logged
        cy.request({
          method: 'GET',
          url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/events/`,
        }).then((eventsResponse) => {
          const events = eventsResponse.body;
          const choiceEvent = events.find(
            (e: { event_type: string }) => e.event_type === 'choice_made',
          );
          expect(choiceEvent).to.exist;
        });
      });
    });

    it('should transition to drafting after both choices made', () => {
      // Get roll winner
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/api/herodraft/${heroDraftPk}/`,
      }).then((response) => {
        const draft = response.body;
        const rollWinnerDiscordId =
          draft.roll_winner?.tournament_team?.captain?.discordId;
        const isRadiantWinner =
          rollWinnerDiscordId === CAPTAIN_RADIANT.discordId;

        // Winner chooses
        if (isRadiantWinner) {
          switchToCaptainRadiant(cy);
        } else {
          switchToCaptainDire(cy);
        }
        visitAndWaitForHydration(
          `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
        );
        waitForHeroDraftModal(cy);
        selectWinnerChoice(cy, 'first_pick');

        // Loser chooses remaining
        if (isRadiantWinner) {
          switchToCaptainDire(cy);
        } else {
          switchToCaptainRadiant(cy);
        }
        visitAndWaitForHydration(
          `/tournament/${tournamentPk}/bracket/draft/${heroDraftPk}`,
        );
        waitForHeroDraftModal(cy);
        selectLoserChoice(cy, 'radiant');

        // Should now be in drafting phase
        waitForDraftState(cy, 'drafting');
        assertDraftingPhase(cy);
      });
    });
  });
});
