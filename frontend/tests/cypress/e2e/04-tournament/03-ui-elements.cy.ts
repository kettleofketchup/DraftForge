import {
  suppressHydrationErrors,
  visitAndWaitForHydration,
} from 'tests/cypress/support/utils';

import { getAddPlayerButton } from 'tests/cypress/helpers/tournament';
import { getUserCard, getUserRemoveButton } from 'tests/cypress/helpers/users';

describe('Tournament UI Elements (e2e)', () => {
  let tournamentPk: number;

  before(() => {
    cy.getTournamentByKey('completed_bracket').then((response) => {
      tournamentPk = response.body.pk;
    });
  });

  beforeEach(() => {
    cy.loginAdmin();
    visitAndWaitForHydration(`/tournament/${tournamentPk}/players`);
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
    cy.get('[data-testid="bracketTab"]').should('be.visible');

    // Default should be players tab
    cy.get('[data-testid="playersTabContent"]').should('be.visible');
  });

  it('should have working add player UI elements', () => {
    // Open the add player dropdown
    getAddPlayerButton(cy).scrollIntoView().should('be.visible').click({ force: true });

    // Verify the modal/dialog appears with search input
    cy.get('[data-testid="playerSearchInput"]').should('be.visible');

    // Verify the input accepts text
    cy.get('[data-testid="playerSearchInput"]').type('test', { force: true });
    cy.get('[data-testid="playerSearchInput"]').should('have.value', 'test');

    // Close by clicking cancel or outside
    cy.contains('Cancel').click({ force: true });
  });

  it('should be able to remove a player from tournament', () => {
    // Find the first player with a remove button (not the admin)
    cy.get('[data-testid^="removePlayerBtn-"]', { timeout: 10000 })
      .first()
      .scrollIntoView()
      .should('be.visible')
      .invoke('attr', 'data-testid')
      .then((testId) => {
        // Extract username from data-testid="removePlayerBtn-{username}"
        const username = (testId as string).replace('removePlayerBtn-', '');

        // Click the remove button
        cy.get(`[data-testid="${testId}"]`).click({ force: true });

        // Check for success toast message
        cy.contains(/removed|deleted/i, { timeout: 5000 }).should('be.visible');

        // Verify the user card is no longer visible
        cy.get(`[data-testid="usercard-${username}"]`).should('not.exist');
      });
  });
});
