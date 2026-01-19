import type { cyType } from './types';

// Tab navigation helpers
export const getInfoTab = (cy: cyType) => {
  return cy.get('[data-testid="league-tab-info"]');
};

export const getTournamentsTab = (cy: cyType) => {
  return cy.get('[data-testid="league-tab-tournaments"]');
};

export const getMatchesTab = (cy: cyType) => {
  return cy.get('[data-testid="league-tab-matches"]');
};

// Edit modal helpers
export const getEditButton = (cy: cyType) => {
  return cy.get('[data-testid="edit-league-button"]');
};

export const getEditModal = (cy: cyType) => {
  return cy.get('[data-testid="edit-league-modal"]');
};

export const getNameInput = (cy: cyType) => {
  return cy.get('[data-testid="league-name-input"]');
};

export const getPrizeInput = (cy: cyType) => {
  return cy.get('[data-testid="league-prize-input"]');
};

export const getDescriptionInput = (cy: cyType) => {
  return cy.get('[data-testid="league-description-input"]');
};

export const getRulesInput = (cy: cyType) => {
  return cy.get('[data-testid="league-rules-input"]');
};

export const getSubmitButton = (cy: cyType) => {
  return cy.get('[data-testid="league-submit-button"]');
};

// Navigate to league page with specific tab
export const visitLeaguePage = (
  cy: cyType,
  leagueId: number,
  tab: 'info' | 'tournaments' | 'matches' = 'info',
) => {
  cy.visit(`/leagues/${leagueId}/${tab}`);
  cy.get('body').should('be.visible');
  cy.wait(500); // Wait for React hydration
};

// Open edit modal
export const openEditModal = (cy: cyType) => {
  getEditButton(cy).should('be.visible').click();
  getEditModal(cy).should('be.visible');
};

// Fill edit form
export const fillEditForm = (
  cy: cyType,
  options: {
    name?: string;
    prizePool?: string;
    description?: string;
    rules?: string;
  },
) => {
  if (options.name !== undefined) {
    getNameInput(cy).clear().type(options.name);
  }
  if (options.prizePool !== undefined) {
    getPrizeInput(cy).clear().type(options.prizePool);
  }
  if (options.description !== undefined) {
    getDescriptionInput(cy).clear().type(options.description);
  }
  if (options.rules !== undefined) {
    getRulesInput(cy).clear().type(options.rules);
  }
};

// Submit edit form
export const submitEditForm = (cy: cyType) => {
  getSubmitButton(cy).click();
};
