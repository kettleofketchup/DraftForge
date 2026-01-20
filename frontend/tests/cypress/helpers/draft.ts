import type { cyType } from './types';

/**
 * Wait for the user to be logged in (avatar visible in navbar)
 * This ensures currentUser is populated in the store before checking draft state
 */
export const waitForUserLoggedIn = (cy: cyType) => {
  // Wait for the profile avatar to appear, indicating user data is loaded
  cy.get('.avatar img', { timeout: 15000 }).should('be.visible');
};

/**
 * Get the draft modal trigger button
 */
export const getDraftButton = (cy: cyType) => {
  return cy.get('button').contains(/Live Draft|Start Draft/i);
};

/**
 * Open the draft modal
 * Note: The draft button is only visible on the Teams tab
 */
export const openDraftModal = (cy: cyType) => {
  // First navigate to Teams tab where the draft button is located
  cy.get('[data-testid="teamsTab"]', { timeout: 10000 }).click();
  cy.wait(500); // Wait for tab content to load

  getDraftButton(cy).click({ force: true });
  cy.get('[role="dialog"]').should('be.visible');
};

/**
 * Get available player row by username
 */
export const getAvailablePlayer = (cy: cyType, username: string) => {
  return cy.get(`[data-testid="available-player"]`).contains(username);
};

/**
 * Get the pick button for a specific player
 */
export const getPickButton = (cy: cyType, username: string) => {
  return cy.contains(username).parent().find('button').contains('Pick');
};

/**
 * Pick a player and confirm the selection
 */
export const pickPlayer = (cy: cyType, username: string) => {
  getPickButton(cy, username).scrollIntoView().click({ force: true });
  // Confirm the pick in the alert dialog with increased timeout
  cy.get('[role="alertdialog"]', { timeout: 10000 }).should('be.visible');
  cy.get('[role="alertdialog"]')
    .contains('Confirm Pick')
    .click({ force: true });
};

/**
 * Get the turn indicator element
 */
export const getTurnIndicator = (cy: cyType) => {
  return cy.get('.p-4.rounded-lg.text-center');
};

/**
 * Check if it's the current user's turn
 */
export const assertMyTurn = (cy: cyType) => {
  getTurnIndicator(cy).should('contain.text', "It's YOUR turn to pick!");
};

/**
 * Check if waiting for another captain
 */
export const assertWaitingForCaptain = (cy: cyType, captainName: string) => {
  getTurnIndicator(cy).should('contain.text', `Waiting for ${captainName}`);
};

/**
 * Get the floating draft indicator
 * Note: Uses longer timeout to account for user fetch + active draft polling
 */
export const getFloatingDraftIndicator = (cy: cyType) => {
  return cy.get('[data-testid="floating-draft-indicator"]', { timeout: 15000 });
};

/**
 * Get the draft notification badge (on user avatar)
 * Note: Uses longer timeout to account for user fetch + active draft polling
 */
export const getDraftNotificationBadge = (cy: cyType) => {
  return cy.get('[data-testid="draft-notification-badge"]', { timeout: 15000 });
};

/**
 * Navigate to tournament with auto-open draft modal
 */
export const visitTournamentWithDraftOpen = (cy: cyType, tournamentPk: number) => {
  cy.visit(`/tournament/${tournamentPk}?draft=open`);
  cy.waitForHydration();
  // Wait for dialog to appear - may take time for draft data to load
  cy.get('[role="dialog"]', { timeout: 15000 }).should('be.visible');
};
