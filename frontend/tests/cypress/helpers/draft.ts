import type { cyType } from './types';

/**
 * Get the draft modal trigger button
 */
export const getDraftButton = (cy: cyType) => {
  return cy.get('button').contains(/Live Draft|Start Draft/i);
};

/**
 * Open the draft modal
 */
export const openDraftModal = (cy: cyType) => {
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
  getPickButton(cy, username).click({ force: true });
  // Confirm the pick in the alert dialog
  cy.get('[role="alertdialog"]').should('be.visible');
  cy.get('[role="alertdialog"]').contains('Confirm Pick').click({ force: true });
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
 */
export const getFloatingDraftIndicator = (cy: cyType) => {
  return cy.get('[data-testid="floating-draft-indicator"]');
};

/**
 * Get the draft notification badge (on user avatar)
 */
export const getDraftNotificationBadge = (cy: cyType) => {
  return cy.get('[data-testid="draft-notification-badge"]');
};

/**
 * Navigate to tournament with auto-open draft modal
 */
export const visitTournamentWithDraftOpen = (cy: cyType, tournamentPk: number) => {
  cy.visit(`/tournament/${tournamentPk}?draft=open`);
  cy.get('[role="dialog"]').should('be.visible');
};
