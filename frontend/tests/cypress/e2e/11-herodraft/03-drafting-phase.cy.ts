/**
 * HeroDraft Main Drafting Phase Tests
 *
 * Tests the main drafting phase where captains ban and pick heroes.
 * Covers hero grid interaction, confirm dialogs, and draft panel updates.
 */

import {
  assertDraftingPhase,
  assertTeamAPicking,
  assertTeamBPicking,
  assertHeroAvailable,
  assertHeroUnavailable,
  assertHeroSelected,
  assertRoundActive,
  assertRoundCompleted,
  assertRoundHeroId,
  assertConfirmDialogAction,
  clickHero,
  searchHero,
  clearHeroSearch,
  selectHeroByName,
  confirmHeroSelection,
  cancelHeroSelection,
  getConfirmDialog,
  getGraceTime,
  getCurrentAction,
  getHeroGrid,
  getDraftPanel,
  waitForHeroDraftModal,
  waitForDraftUpdate,
} from '../../helpers/herodraft';

describe('HeroDraft - Main Drafting Phase', () => {
  let draftingDraftId: number;
  let captainAPk: number;
  let captainBPk: number;
  let firstPickCaptainPk: number;

  before(() => {
    // Get HeroDraft in drafting state
    cy.request({
      method: 'GET',
      url: `${Cypress.env('apiUrl')}/tests/herodraft-by-key/drafting_phase/`,
      failOnStatusCode: false,
    }).then((response) => {
      if (response.status === 200) {
        draftingDraftId = response.body.pk;
        const teams = response.body.draft_teams || [];
        if (teams.length >= 2) {
          captainAPk = teams[0].captain?.pk;
          captainBPk = teams[1].captain?.pk;
          // Determine who picks first
          const firstPickTeam = teams.find((t: { is_first_pick: boolean }) => t.is_first_pick);
          firstPickCaptainPk = firstPickTeam?.captain?.pk || captainAPk;
        }
      } else {
        cy.log('HeroDraft drafting phase test data not available');
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

  describe('Drafting UI Layout', () => {
    it('should display the main drafting area', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      assertDraftingPhase(cy);
    });

    it('should show hero grid on the left', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      getHeroGrid(cy).should('be.visible');
    });

    it('should show draft panel on the right', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      getDraftPanel(cy).should('be.visible');
    });

    it('should show top bar with timers', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-topbar"]').should('be.visible');
      cy.get('[data-testid="herodraft-timers-row"]').should('be.visible');
    });
  });

  describe('Hero Grid', () => {
    it('should display heroes grouped by attribute', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-attr-section-str"]').should('be.visible');
      cy.get('[data-testid="herodraft-attr-section-agi"]').should('be.visible');
      cy.get('[data-testid="herodraft-attr-section-int"]').should('be.visible');
      cy.get('[data-testid="herodraft-attr-section-all"]').should('be.visible');
    });

    it('should have attribute labels', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-attr-label-str"]').should('contain.text', 'Strength');
      cy.get('[data-testid="herodraft-attr-label-agi"]').should('contain.text', 'Agility');
      cy.get('[data-testid="herodraft-attr-label-int"]').should('contain.text', 'Intelligence');
      cy.get('[data-testid="herodraft-attr-label-all"]').should('contain.text', 'Universal');
    });

    it('should filter heroes by search', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      searchHero(cy, 'Anti-Mage');

      // Anti-Mage should be visible and not greyed out
      cy.get('[data-hero-name="Anti-Mage"]').should('be.visible');
      // Other heroes should be greyed out or hidden
    });

    it('should clear search when input cleared', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      searchHero(cy, 'Anti-Mage');
      clearHeroSearch(cy);

      // All heroes should be visible again
      cy.get('[data-testid="herodraft-hero-list"]').find('button').should('have.length.greaterThan', 100);
    });
  });

  describe('Hero Selection', () => {
    it('should highlight selected hero', function () {
      if (!draftingDraftId || !firstPickCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(firstPickCaptainPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // Click on a hero (Anti-Mage has ID 1)
      clickHero(cy, 1);
      assertHeroSelected(cy, 1);
    });

    it('should open confirm dialog when hero clicked', function () {
      if (!draftingDraftId || !firstPickCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(firstPickCaptainPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      clickHero(cy, 1);

      getConfirmDialog(cy).should('be.visible');
    });

    it('should show correct action in confirm dialog (ban/pick)', function () {
      if (!draftingDraftId || !firstPickCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(firstPickCaptainPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // Get current action from top bar
      getCurrentAction(cy).then(($action) => {
        const actionText = $action.text().toLowerCase();
        const isBan = actionText.includes('ban');

        clickHero(cy, 1);
        assertConfirmDialogAction(cy, isBan ? 'ban' : 'pick');
      });
    });

    it('should close confirm dialog when cancelled', function () {
      if (!draftingDraftId || !firstPickCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(firstPickCaptainPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      clickHero(cy, 1);
      getConfirmDialog(cy).should('be.visible');

      cancelHeroSelection(cy);
      getConfirmDialog(cy).should('not.exist');
    });

    it('should not allow clicking heroes when not your turn', function () {
      if (!draftingDraftId || !captainAPk || !captainBPk) {
        this.skip();
        return;
      }

      // Login as the captain who is NOT currently picking
      const nonPickingCaptain = firstPickCaptainPk === captainAPk ? captainBPk : captainAPk;

      cy.loginAsUser(nonPickingCaptain);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // Click a hero - should show error or be disabled
      clickHero(cy, 1);

      // Either no dialog opens or toast error appears
      cy.wait(500);
      cy.get('[data-testid="herodraft-confirm-dialog"]').should('not.exist');
    });
  });

  describe('Confirm and Submit', () => {
    it('should submit pick and update draft panel', function () {
      if (!draftingDraftId || !firstPickCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(firstPickCaptainPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // Get current round number
      cy.get('[data-round-active="true"]').then(($active) => {
        const roundTestId = $active.attr('data-testid');
        const roundNumber = roundTestId?.match(/herodraft-round-(\d+)/)?.[1];

        if (roundNumber) {
          // Select a hero that's definitely available
          clickHero(cy, 2); // Axe
          confirmHeroSelection(cy);

          // Wait for the pick to be submitted
          cy.wait(2000);

          // The round should now show the hero
          assertRoundCompleted(cy, parseInt(roundNumber));
          assertRoundHeroId(cy, parseInt(roundNumber), 2);
        }
      });
    });

    it('should mark hero as unavailable after selection', function () {
      if (!draftingDraftId || !firstPickCaptainPk) {
        this.skip();
        return;
      }

      cy.loginAsUser(firstPickCaptainPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // Check which heroes are already unavailable
      cy.get('[data-hero-available="false"]').then(($unavailable) => {
        const unavailableCount = $unavailable.length;

        // Make a pick
        cy.get('[data-hero-available="true"]').first().click();
        confirmHeroSelection(cy);

        cy.wait(2000);

        // One more hero should be unavailable
        cy.get('[data-hero-available="false"]').should('have.length.greaterThan', unavailableCount);
      });
    });
  });

  describe('Turn Indicator', () => {
    it('should show PICKING indicator for active team', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // Either team A or team B should be picking
      cy.get('[data-testid="herodraft-topbar"]').then(($topbar) => {
        const text = $topbar.text();
        expect(text).to.include('PICKING');
      });
    });
  });

  describe('Timer Display', () => {
    it('should display grace time', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      getGraceTime(cy).should('be.visible');
      getGraceTime(cy).should('match', /\d+:\d+/);
    });

    it('should display reserve times for both teams', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-team-a-reserve-time"]').should('match', /\d+:\d+/);
      cy.get('[data-testid="herodraft-team-b-reserve-time"]').should('match', /\d+:\d+/);
    });
  });

  describe('Draft Panel', () => {
    it('should show all draft rounds', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      // Captain's mode has 24 rounds (6 bans + 5 picks per team)
      cy.get('[data-testid^="herodraft-round-"]').should('have.length.greaterThan', 0);
    });

    it('should highlight current active round', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-round-active="true"]').should('have.length', 1);
    });

    it('should show radiant header', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-panel-radiant-header"]').should('contain.text', 'RADIANT');
    });

    it('should show dire header', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginAsUser(captainAPk);
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      cy.get('[data-testid="herodraft-panel-dire-header"]').should('contain.text', 'DIRE');
    });
  });

  describe('Spectator View', () => {
    it('should allow spectators to view the draft', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginUser();
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);
      assertDraftingPhase(cy);
    });

    it('should disable hero selection for spectators', function () {
      if (!draftingDraftId) {
        this.skip();
        return;
      }

      cy.loginUser();
      cy.visit(`/herodraft/${draftingDraftId}`);
      cy.waitForHydration();

      waitForHeroDraftModal(cy);

      // All hero buttons should be disabled for spectators
      cy.get('[data-testid="herodraft-hero-grid"] button').first().should('be.disabled');
    });
  });
});
