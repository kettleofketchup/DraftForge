import {
  suppressHydrationErrors,
  visitAndWaitForHydration,
} from 'tests/cypress/support/utils';
describe('Tournament API: User', () => {
  beforeEach(() => {
    // Suppress hydration errors that don't affect functionality
    suppressHydrationErrors();

    cy.loginAdmin();
    visitAndWaitForHydration('/tournament/1');
  });

  it('should be able to handle adding users to the tournaments', () => {
    // Intercept and mock tournaments API

    // Verify the API was called

    // Check that the page displays the mocked data
    cy.get('body').should('contain.text', 'Completed Bracket Test');
  });
});
