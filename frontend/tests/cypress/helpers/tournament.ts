import type { cyType } from './types';
import { getUserCard } from './users';

export const getAddPlayerButton = (cy: cyType) => {
  return cy.get(`[data-testid="tournamentAddPlayerBtn"]`);
};

export const addPlayerToTournament = (cy: cyType, username: string) => {
  getAddPlayerButton(cy)
    .scrollIntoView()
    .should('be.visible')
    .click({ force: true });

  cy.get('[data-testid="playerSearchInput"]').type(username, {
    force: true,
  });

  cy.get(`[data-testid="playerOption-${username}"]`)
    .should('be.visible')
    .click({ force: true });

  cy.get('[data-testid="playerSearchInput"]').type(username, {
    force: true,
  });

  cy.get(`[data-testid="playerOption-${username}"]`)
    .should('be.visible')
    .click({ force: true });

  cy.contains(/added|created/i, { timeout: 5000 }).should('be.visible');

  getUserCard(cy, username).scrollIntoView().should('exist').and('be.visible');
};

// Tournament creation helpers
export const getCreateTournamentButton = (cy: cyType) => {
  return cy.get('[data-testid="tournament-create-button"]');
};

export const getTournamentModal = (cy: cyType) => {
  return cy.get('[data-testid="tournament-create-modal"]');
};

export const getTournamentForm = (cy: cyType) => {
  return cy.get('[data-testid="tournament-form"]');
};

export const getTournamentNameInput = (cy: cyType) => {
  return cy.get('[data-testid="tournament-name-input"]');
};

export const getTournamentTypeSelect = (cy: cyType) => {
  return cy.get('[data-testid="tournament-type-select"]');
};

export const getTournamentDatePicker = (cy: cyType) => {
  return cy.get('[data-testid="tournament-date-picker"]');
};

export const getTournamentLeagueSelect = (cy: cyType) => {
  return cy.get('[data-testid="tournament-league-select"]');
};

export const getTournamentSubmitButton = (cy: cyType) => {
  return cy.get('[data-testid="tournament-submit-button"]');
};

export const getTournamentCancelButton = (cy: cyType) => {
  return cy.get('[data-testid="tournament-cancel-button"]');
};

export interface CreateTournamentOptions {
  name: string;
  tournamentType?: 'single_elimination' | 'double_elimination' | 'swiss';
  leaguePk?: number | null;
}

export const openCreateTournamentModal = (cy: cyType) => {
  getCreateTournamentButton(cy).should('be.visible').click();
  getTournamentModal(cy).should('be.visible');
};

export const fillTournamentForm = (
  cy: cyType,
  options: CreateTournamentOptions,
) => {
  const { name, tournamentType = 'double_elimination', leaguePk } = options;

  // Fill tournament name
  getTournamentNameInput(cy).clear().type(name);

  // Select tournament type
  getTournamentTypeSelect(cy).click();
  cy.get(`[data-testid="tournament-type-${tournamentType.replace('_elimination', '')}"]`)
    .should('be.visible')
    .click();

  // Select league if provided
  if (leaguePk !== undefined) {
    getTournamentLeagueSelect(cy).click();
    if (leaguePk === null) {
      cy.get('[data-testid="tournament-league-none"]').should('be.visible').click();
    } else {
      cy.get(`[data-testid="tournament-league-${leaguePk}"]`).should('be.visible').click();
    }
  }
};

export const submitTournamentForm = (cy: cyType) => {
  getTournamentSubmitButton(cy).click();
};

export const createTournament = (
  cy: cyType,
  options: CreateTournamentOptions,
) => {
  openCreateTournamentModal(cy);
  fillTournamentForm(cy, options);
  submitTournamentForm(cy);

  // Wait for success toast
  cy.contains(/created successfully/i, { timeout: 5000 }).should('be.visible');
};
