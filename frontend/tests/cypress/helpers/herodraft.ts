import type { cyType } from './types';

/**
 * HeroDraft Cypress Test Helpers
 *
 * Helper functions for testing the HeroDraft (Captain's Mode) feature.
 * Tests hero banning/picking flow with timed turns.
 */

// ============================================================================
// Modal Navigation
// ============================================================================

/**
 * Get the HeroDraft modal
 */
export const getHeroDraftModal = (cy: cyType) => {
  return cy.get('[data-testid="herodraft-modal"]', { timeout: 10000 });
};

/**
 * Wait for the HeroDraft modal to be visible
 */
export const waitForHeroDraftModal = (cy: cyType) => {
  return cy.get('[data-testid="herodraft-modal"]', { timeout: 15000 }).should('be.visible');
};

/**
 * Close the HeroDraft modal by pressing escape or clicking outside
 */
export const closeHeroDraftModal = (cy: cyType) => {
  cy.get('body').type('{esc}');
  cy.get('[data-testid="herodraft-modal"]').should('not.exist');
};

// ============================================================================
// Draft Phases
// ============================================================================

/**
 * Assert the draft is in waiting_for_captains state
 */
export const assertWaitingPhase = (cy: cyType) => {
  cy.get('[data-testid="herodraft-waiting-phase"]').should('be.visible');
  cy.get('[data-testid="herodraft-waiting-title"]').should('contain.text', 'Waiting for Captains');
};

/**
 * Assert the draft is in rolling state
 */
export const assertRollingPhase = (cy: cyType) => {
  cy.get('[data-testid="herodraft-rolling-phase"]').should('be.visible');
  cy.get('[data-testid="herodraft-rolling-title"]').should('contain.text', 'Both Captains Ready');
};

/**
 * Assert the draft is in choosing state
 */
export const assertChoosingPhase = (cy: cyType) => {
  cy.get('[data-testid="herodraft-choosing-phase"]').should('be.visible');
};

/**
 * Assert the draft is in the main drafting area
 */
export const assertDraftingPhase = (cy: cyType) => {
  cy.get('[data-testid="herodraft-main-area"]').should('be.visible');
  cy.get('[data-testid="herodraft-hero-grid-container"]').should('be.visible');
  cy.get('[data-testid="herodraft-panel-container"]').should('be.visible');
};

/**
 * Assert the draft is paused
 */
export const assertPausedState = (cy: cyType) => {
  cy.get('[data-testid="herodraft-paused-overlay"]').should('be.visible');
  cy.get('[data-testid="herodraft-paused-title"]').should('contain.text', 'Draft Paused');
};

// ============================================================================
// Captain Actions
// ============================================================================

/**
 * Click the Ready button (waiting phase)
 */
export const clickReadyButton = (cy: cyType) => {
  cy.get('[data-testid="herodraft-ready-button"]').click();
};

/**
 * Click the Flip Coin button (rolling phase)
 */
export const clickFlipCoinButton = (cy: cyType) => {
  cy.get('[data-testid="herodraft-flip-coin-button"]').click();
};

/**
 * Select a choice after winning the flip
 */
export const selectWinnerChoice = (
  cy: cyType,
  choice: 'first_pick' | 'second_pick' | 'radiant' | 'dire'
) => {
  const testIdMap = {
    first_pick: 'herodraft-choice-first-pick',
    second_pick: 'herodraft-choice-second-pick',
    radiant: 'herodraft-choice-radiant',
    dire: 'herodraft-choice-dire',
  };
  cy.get(`[data-testid="${testIdMap[choice]}"]`).click();
};

/**
 * Select a remaining choice (for the captain who lost the flip)
 */
export const selectLoserChoice = (
  cy: cyType,
  choice: 'first_pick' | 'second_pick' | 'radiant' | 'dire'
) => {
  const testIdMap = {
    first_pick: 'herodraft-remaining-first-pick',
    second_pick: 'herodraft-remaining-second-pick',
    radiant: 'herodraft-remaining-radiant',
    dire: 'herodraft-remaining-dire',
  };
  cy.get(`[data-testid="${testIdMap[choice]}"]`).click();
};

// ============================================================================
// Top Bar
// ============================================================================

/**
 * Get the DraftTopBar component
 */
export const getTopBar = (cy: cyType) => {
  return cy.get('[data-testid="herodraft-topbar"]');
};

/**
 * Assert which team is currently picking
 */
export const assertTeamAPicking = (cy: cyType) => {
  cy.get('[data-testid="herodraft-team-a-picking"]').should('be.visible');
};

export const assertTeamBPicking = (cy: cyType) => {
  cy.get('[data-testid="herodraft-team-b-picking"]').should('be.visible');
};

/**
 * Get the grace time display
 */
export const getGraceTime = (cy: cyType) => {
  return cy.get('[data-testid="herodraft-grace-time"]');
};

/**
 * Get the current action type (pick/ban)
 */
export const getCurrentAction = (cy: cyType) => {
  return cy.get('[data-testid="herodraft-current-action"]');
};

/**
 * Get team reserve time
 */
export const getTeamAReserveTime = (cy: cyType) => {
  return cy.get('[data-testid="herodraft-team-a-reserve-time"]');
};

export const getTeamBReserveTime = (cy: cyType) => {
  return cy.get('[data-testid="herodraft-team-b-reserve-time"]');
};

// ============================================================================
// Hero Grid
// ============================================================================

/**
 * Get the hero grid container
 */
export const getHeroGrid = (cy: cyType) => {
  return cy.get('[data-testid="herodraft-hero-grid"]');
};

/**
 * Search for a hero by name
 */
export const searchHero = (cy: cyType, heroName: string) => {
  cy.get('[data-testid="herodraft-hero-search"]').clear().type(heroName);
};

/**
 * Clear the hero search
 */
export const clearHeroSearch = (cy: cyType) => {
  cy.get('[data-testid="herodraft-hero-search"]').clear();
};

/**
 * Click on a hero by ID
 */
export const clickHero = (cy: cyType, heroId: number) => {
  cy.get(`[data-testid="herodraft-hero-${heroId}"]`).click();
};

/**
 * Click on a hero by name (first searches, then clicks)
 */
export const selectHeroByName = (cy: cyType, heroName: string) => {
  searchHero(cy, heroName);
  cy.get(`[data-hero-name="${heroName}"]`).click();
};

/**
 * Assert a hero is available for selection
 */
export const assertHeroAvailable = (cy: cyType, heroId: number) => {
  cy.get(`[data-testid="herodraft-hero-${heroId}"]`)
    .should('have.attr', 'data-hero-available', 'true');
};

/**
 * Assert a hero is unavailable (already picked/banned)
 */
export const assertHeroUnavailable = (cy: cyType, heroId: number) => {
  cy.get(`[data-testid="herodraft-hero-${heroId}"]`)
    .should('have.attr', 'data-hero-available', 'false');
  cy.get(`[data-testid="herodraft-hero-${heroId}-unavailable"]`).should('be.visible');
};

/**
 * Assert a hero is selected (highlighted)
 */
export const assertHeroSelected = (cy: cyType, heroId: number) => {
  cy.get(`[data-testid="herodraft-hero-${heroId}"]`)
    .should('have.attr', 'data-hero-selected', 'true');
};

// ============================================================================
// Confirm Dialog
// ============================================================================

/**
 * Get the confirm pick/ban dialog
 */
export const getConfirmDialog = (cy: cyType) => {
  return cy.get('[data-testid="herodraft-confirm-dialog"]');
};

/**
 * Confirm the hero selection
 */
export const confirmHeroSelection = (cy: cyType) => {
  cy.get('[data-testid="herodraft-confirm-submit"]').click();
};

/**
 * Cancel the hero selection
 */
export const cancelHeroSelection = (cy: cyType) => {
  cy.get('[data-testid="herodraft-confirm-cancel"]').click();
};

/**
 * Assert the confirm dialog shows the correct action (pick/ban)
 */
export const assertConfirmDialogAction = (cy: cyType, action: 'pick' | 'ban') => {
  cy.get('[data-testid="herodraft-confirm-title"]')
    .should('contain.text', action === 'ban' ? 'Ban' : 'Pick');
};

// ============================================================================
// Draft Panel
// ============================================================================

/**
 * Get the draft panel
 */
export const getDraftPanel = (cy: cyType) => {
  return cy.get('[data-testid="herodraft-panel"]');
};

/**
 * Assert a round is active (currently being drafted)
 */
export const assertRoundActive = (cy: cyType, roundNumber: number) => {
  cy.get(`[data-testid="herodraft-round-${roundNumber}"]`)
    .should('have.attr', 'data-round-active', 'true');
};

/**
 * Assert a round is completed
 */
export const assertRoundCompleted = (cy: cyType, roundNumber: number) => {
  cy.get(`[data-testid="herodraft-round-${roundNumber}"]`)
    .should('have.attr', 'data-round-state', 'completed');
};

/**
 * Assert a specific hero was selected for a round
 */
export const assertRoundHeroId = (cy: cyType, roundNumber: number, heroId: number) => {
  cy.get(`[data-testid="herodraft-round-${roundNumber}-hero"]`)
    .should('have.attr', 'data-hero-id', String(heroId));
};

// ============================================================================
// Connection Status
// ============================================================================

/**
 * Assert the WebSocket is connected (no reconnecting message)
 */
export const assertConnected = (cy: cyType) => {
  cy.get('[data-testid="herodraft-reconnecting"]').should('not.exist');
};

/**
 * Assert the WebSocket is reconnecting
 */
export const assertReconnecting = (cy: cyType) => {
  cy.get('[data-testid="herodraft-reconnecting"]').should('be.visible');
};

// ============================================================================
// Captain Status (waiting phase)
// ============================================================================

/**
 * Assert a captain's ready status in the waiting phase
 */
export const assertCaptainReady = (cy: cyType, teamId: number) => {
  cy.get(`[data-testid="herodraft-ready-status-${teamId}"]`)
    .should('contain.text', 'Ready');
};

export const assertCaptainNotReady = (cy: cyType, teamId: number) => {
  cy.get(`[data-testid="herodraft-ready-status-${teamId}"]`)
    .should('contain.text', 'Not Ready');
};

// ============================================================================
// Utility
// ============================================================================

/**
 * Wait for draft state to update via WebSocket
 */
export const waitForDraftUpdate = (cy: cyType, timeout = 5000) => {
  // Wait for a visual indicator that the state updated
  cy.wait(500); // Small buffer for WebSocket message to arrive
};

/**
 * Wait for a specific draft state
 */
export const waitForDraftState = (
  cy: cyType,
  state: 'waiting_for_captains' | 'rolling' | 'choosing' | 'drafting' | 'paused' | 'completed',
  timeout = 10000
) => {
  const stateToTestIdMap = {
    waiting_for_captains: 'herodraft-waiting-phase',
    rolling: 'herodraft-rolling-phase',
    choosing: 'herodraft-choosing-phase',
    drafting: 'herodraft-main-area',
    paused: 'herodraft-paused-overlay',
    completed: 'herodraft-main-area', // completed still shows main area
  };
  cy.get(`[data-testid="${stateToTestIdMap[state]}"]`, { timeout }).should('be.visible');
};
