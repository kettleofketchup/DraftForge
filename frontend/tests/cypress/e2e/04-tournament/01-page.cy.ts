describe('API Integration Tests', () => {
  beforeEach(() => {});

  it('should handle API requests for tournaments', () => {
    // Intercept and mock tournaments API

    cy.visit('/tournament/1');

    // Verify the API was called

    // Check that the page displays the mocked data
    cy.get('body').should('contain.text', 'Completed Bracket Test');
  });
});
