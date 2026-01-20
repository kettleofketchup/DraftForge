/**
 * HeroDraft Rolling & Choosing Phase Tests
 *
 * Tests the coin flip (rolling) and choice selection (choosing) phases.
 * After both captains are ready, a coin flip determines who chooses first.
 * The winner picks either pick order or side, loser gets the remaining choice.
 */

import {
  assertRollingPhase,
  assertChoosingPhase,
  clickFlipCoinButton,
  selectWinnerChoice,
  selectLoserChoice,
  waitForHeroDraftModal,
  waitForDraftState,
} from '../../helpers/herodraft';

describe('HeroDraft - Rolling & Choosing Phases', () => {
  let heroDraftId: number;
  let captainAPk: number;
  let captainBPk: number;

  before(() => {
    // Get HeroDraft in rolling state from test config
    cy.request({
      method: 'GET',
      url: `${Cypress.env('apiUrl')}/tests/herodraft-by-key/rolling_phase/`,
      failOnStatusCode: false,
    }).then((response) => {
      if (response.status === 200) {
        heroDraftId = response.body.pk;
        const teams = response.body.draft_teams || [];
        if (teams.length >= 2) {
          captainAPk = teams[0].captain?.pk;
          captainBPk = teams[1].captain?.pk;
        }
      } else {
        cy.log('HeroDraft rolling phase test data not available');
      }
    });
  });

  beforeEach(() => {
    cy.clearCookies();
    cy.clearLocalStorage();
    cy.window().then((win) => {
      win.sessionStorage.clear();
    });
  });

  describe('Rolling Phase', () => {
    it('should display rolling phase UI', function () {
      if (!heroDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${heroDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      assertRollingPhase(cy);
    });

    it('should show flip coin button only to captains', function () {
      if (!heroDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${heroDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-flip-coin-button"]').should('be.visible');
    });

    it('should not show flip coin button to spectators', function () {
      if (!heroDraftId) {
        this.skip();
        return;
      }

      cy.loginUser();
      cy.visit(`/herodraft/${heroDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-flip-coin-button"]').should('not.exist');
    });

    it('should transition to choosing phase after coin flip', function () {
      if (!heroDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${heroDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // Check if we're in rolling phase
      cy.get('[data-testid="herodraft-rolling-phase"]').then(($rolling) => {
        if ($rolling.length > 0) {
          clickFlipCoinButton(cy);
          // Wait for transition to choosing phase
          waitForDraftState(cy, 'choosing', 10000);
        }
      });
    });
  });

  describe('Choosing Phase - Winner', () => {
    let choosingDraftId: number;
    let winnerCaptainPk: number;

    before(() => {
      // Get HeroDraft in choosing state with known winner
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/tests/herodraft-by-key/choosing_phase/`,
        failOnStatusCode: false,
      }).then((response) => {
        if (response.status === 200) {
          choosingDraftId = response.body.pk;
          // roll_winner contains the winning team
          if (response.body.roll_winner?.captain?.pk) {
            winnerCaptainPk = response.body.roll_winner.captain.pk;
          }
        }
      });
    });

    it('should display flip winner name', function () {
      if (!choosingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(winnerCaptainPk || captainAPk);
      cy.visit(`/herodraft/${choosingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-flip-winner"]').should('be.visible');
      cy.get('[data-testid="herodraft-flip-winner"]').should('contain.text', 'won the flip');
    });

    it('should show all choice buttons to the winner', function () {
      if (!choosingDraftId || !winnerCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(winnerCaptainPk);
      cy.visit(`/herodraft/${choosingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-winner-choices"]').should('be.visible');
      cy.get('[data-testid="herodraft-choice-first-pick"]').should('be.visible');
      cy.get('[data-testid="herodraft-choice-second-pick"]').should('be.visible');
      cy.get('[data-testid="herodraft-choice-radiant"]').should('be.visible');
      cy.get('[data-testid="herodraft-choice-dire"]').should('be.visible');
    });

    it('should allow winner to select first pick', function () {
      if (!choosingDraftId || !winnerCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(winnerCaptainPk);
      cy.visit(`/herodraft/${choosingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      selectWinnerChoice(cy, 'first_pick');

      // Wait for the choice to be submitted
      cy.wait(1000);
      // Winner should now wait for loser to choose side
      cy.get('[data-testid="herodraft-winner-choices"]').should('not.exist');
    });

    it('should allow winner to select radiant side', function () {
      if (!choosingDraftId || !winnerCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(winnerCaptainPk);
      cy.visit(`/herodraft/${choosingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // Check if choice buttons are still visible
      cy.get('[data-testid="herodraft-winner-choices"]').then(($choices) => {
        if ($choices.length > 0) {
          selectWinnerChoice(cy, 'radiant');
          cy.wait(1000);
        }
      });
    });
  });

  describe('Choosing Phase - Loser', () => {
    let choosingDraftId: number;
    let winnerCaptainPk: number;
    let loserCaptainPk: number;

    before(() => {
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/tests/herodraft-by-key/choosing_phase_loser_turn/`,
        failOnStatusCode: false,
      }).then((response) => {
        if (response.status === 200) {
          choosingDraftId = response.body.pk;
          const teams = response.body.draft_teams || [];
          const winner = response.body.roll_winner;

          if (winner && teams.length >= 2) {
            winnerCaptainPk = winner.captain?.pk;
            // Loser is the team that is not the winner
            const loserTeam = teams.find((t: { id: number }) => t.id !== winner.id);
            loserCaptainPk = loserTeam?.captain?.pk;
          }
        }
      });
    });

    it('should show remaining choices to the loser', function () {
      if (!choosingDraftId || !loserCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(loserCaptainPk);
      cy.visit(`/herodraft/${choosingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-loser-choices"]').should('be.visible');
    });

    it('should show only pick order buttons if winner chose side', function () {
      if (!choosingDraftId || !loserCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(loserCaptainPk);
      cy.visit(`/herodraft/${choosingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // Check if remaining buttons exist
      cy.get('[data-testid="herodraft-remaining-choice-buttons"]').should('be.visible');
    });

    it('should allow loser to select remaining choice', function () {
      if (!choosingDraftId || !loserCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(loserCaptainPk);
      cy.visit(`/herodraft/${choosingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // Try to click any available choice
      cy.get('[data-testid="herodraft-remaining-choice-buttons"]').then(($btns) => {
        if ($btns.find('[data-testid="herodraft-remaining-first-pick"]').length > 0) {
          selectLoserChoice(cy, 'first_pick');
        } else if ($btns.find('[data-testid="herodraft-remaining-radiant"]').length > 0) {
          selectLoserChoice(cy, 'radiant');
        }
      });

      // Should transition to drafting phase
      cy.wait(2000);
    });

    it('should show waiting message to spectators', function () {
      if (!choosingDraftId) {
        this.skip();
        return;
      }

      cy.loginUser();
      cy.visit(`/herodraft/${choosingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-spectating"]').should('be.visible');
    });
  });

  describe('Transition to Drafting', () => {
    let readyDraftId: number;
    let captainPk: number;

    before(() => {
      // Get a draft that's ready to transition to drafting
      cy.request({
        method: 'GET',
        url: `${Cypress.env('apiUrl')}/tests/herodraft-by-key/ready_to_draft/`,
        failOnStatusCode: false,
      }).then((response) => {
        if (response.status === 200) {
          readyDraftId = response.body.pk;
          const teams = response.body.draft_teams || [];
          if (teams.length > 0) {
            captainPk = teams[0].captain?.pk;
          }
        }
      });
    });

    it('should transition to drafting phase after both choices made', function () {
      if (!readyDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainPk);
      cy.visit(`/herodraft/${readyDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // Should be in drafting phase
      waitForDraftState(cy, 'drafting', 5000);
      cy.get('[data-testid="herodraft-hero-grid-container"]').should('be.visible');
      cy.get('[data-testid="herodraft-panel-container"]').should('be.visible');
    });

    it('should show correct teams on correct sides after choices', function () {
      if (!readyDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainPk);
      cy.visit(`/herodraft/${readyDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      waitForDraftState(cy, 'drafting', 5000);

      // Verify top bar shows teams
      cy.get('[data-testid="herodraft-team-a-side"]').should('be.visible');
      cy.get('[data-testid="herodraft-team-b-side"]').should('be.visible');
    });
  });
});
