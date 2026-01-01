import type { cyType } from './types';

export const getUserCard = (cy: cyType, username: string) => {
  return cy.get(`[data-testid="usercard-${username}"]`);
};

export const getUserRemoveButton = (cy: cyType, username: string) => {
  return cy.get(`[data-testid="removePlayerBtn-${username}"]`);
};
