import {
  suppressHydrationErrors,
  visitAndWaitForHydration,
} from 'tests/cypress/support/utils';
import { playername } from './constants';
describe('Tournament UI Elements (e2e)', () => {
  beforeEach(() => {
    cy.loginAdmin();

    visitAndWaitForHydration('/tournament/1/players');
    suppressHydrationErrors();
  });

  it('should have all tournament page elements with proper test identifiers', () => {
    // Check main page elements
    cy.get('[data-testid="tournamentDetailPage"]').should('be.visible');
    cy.get('[data-testid="tournamentTitle"]').should('be.visible');

    // Check tab navigation
    cy.get('[data-testid="tournamentTabsList"]').should('be.visible');
    cy.get('[data-testid="playersTab"]').should('be.visible');
    cy.get('[data-testid="teamsTab"]').should('be.visible');
    cy.get('[data-testid="gamesTab"]').should('be.visible');

    // Default should be players tab
    cy.get('[data-testid="playersTabContent"]').should('be.visible');
  });

  it(`should check if ${playername} user is already in tournament`, () => {
    // Check if the specific user is already in the tournament

    if (
      !cy
        .get(`[data-testid="usercard-${playername}"]`)
        .scrollIntoView()
        .should('be.visible')
    ) {
      cy.get(`[data-testid="tournamentAddPlayerBtn"]`)
        .should('be.visible')
        .click({ force: true });
      cy.get('[data-testid="playerSearchInput"]').type(playername, {
        force: true,
      });
      cy.get(`[data-testid="playerOption-${playername}"]`)
        .should('be.visible')
        .click({ force: true });

      cy.contains(/added|created/i, { timeout: 5000 }).should('be.visible');
    }

    cy.get(`[data-testid^="playerRemoveBtn-${playername}"]`)
      .should('exist')
      .and('be.visible');
  });

  it(`should remove ${playername} from tournament`, () => {
    // Find and click the specific remove button for kettleofketchup
    cy.get(`[data-testid="removePlayerBtn-${playername}"]`)
      .scrollIntoView()
      .should('be.visible')
      .click({ force: true });

    // Check for success toast message
    cy.contains(/removed|deleted/i, { timeout: 5000 }).should('be.visible');
  });

  it(`should add ${playername} to tournament`, () => {
    // Find and click the specific add button for kettleofketchup
    cy.get(`[data-testid="tournamentAddPlayerBtn"]`)
      .should('be.visible')
      .click({ force: true });
    cy.get('[data-testid="playerSearchInput"]').type(playername, {
      force: true,
    });
    cy.get(`[data-testid="playerOption-${playername}"]`)
      .should('be.visible')
      .click({ force: true });

    cy.contains(/added/i, { timeout: 5000 }).should('be.visible');
  });
});
