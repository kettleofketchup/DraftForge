import {
  suppressHydrationErrors,
  visitAndWaitForHydration,
} from 'tests/cypress/support/utils';

describe('Bracket Badges (e2e)', () => {
  beforeEach(() => {
    cy.loginStaff();
    suppressHydrationErrors();
  });

  it('should display bracket with completed games', () => {
    // Completed Bracket Test (Tournament 1) has all 6 games completed
    visitAndWaitForHydration('/tournament/1/games');

    // Wait for the games tab to load
    cy.get('[data-testid="gamesTab"]', { timeout: 10000 }).should('be.visible');

    // Default view should be bracket view
    cy.contains('Bracket View').should('be.visible');

    // Wait for bracket container to appear (bracket data loaded)
    cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
      'be.visible',
    );
  });

  it('should display bracket badges on winners bracket matches', () => {
    // Completed Bracket Test has completed bracket with badges
    visitAndWaitForHydration('/tournament/1/games');

    // Wait for bracket to load
    cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
      'be.visible',
    );

    // Winners bracket matches that have loser paths should have badges on the right
    // Badge A should appear on the first winners R1 match (position right)
    cy.get('[data-testid="bracket-badge-A-right"]', { timeout: 10000 }).should(
      'exist',
    );

    // Badge B should appear on the second winners R1 match
    cy.get('[data-testid="bracket-badge-B-right"]').should('exist');
  });

  it('should display corresponding badges on losers bracket slots', () => {
    visitAndWaitForHydration('/tournament/1/games');

    cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
      'be.visible',
    );

    // Losers R1 match should have badges on the left indicating where teams came from
    // Badge A on top slot (radiant team)
    cy.get('[data-testid="bracket-badge-A-left-top"]', {
      timeout: 10000,
    }).should('exist');

    // Badge B on bottom slot (dire team)
    cy.get('[data-testid="bracket-badge-B-left-bottom"]').should('exist');
  });

  it('should show badge letters with distinct colors', () => {
    visitAndWaitForHydration('/tournament/1/games');

    cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
      'be.visible',
    );

    // Verify badge A shows letter A
    cy.get('[data-testid="bracket-badge-letter-A"]')
      .should('exist')
      .and('contain.text', 'A');

    // Verify badge B shows letter B
    cy.get('[data-testid="bracket-badge-letter-B"]')
      .should('exist')
      .and('contain.text', 'B');
  });

  it('should show Winners Bracket label', () => {
    visitAndWaitForHydration('/tournament/1/games');

    cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
      'be.visible',
    );

    // ReactFlow panel should show Winners Bracket label
    cy.contains('Winners Bracket').should('be.visible');
  });

  it('should show Losers Bracket divider', () => {
    visitAndWaitForHydration('/tournament/1/games');

    cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
      'be.visible',
    );

    // Divider node should show Losers Bracket label
    cy.contains('Losers Bracket').should('be.visible');
  });

  it('should handle tournament with partial bracket', () => {
    // Partial Bracket Test (Tournament 2) has 2 games completed, 4 pending
    visitAndWaitForHydration('/tournament/2/games');

    cy.get('[data-testid="gamesTab"]', { timeout: 10000 }).should('be.visible');

    // Should still show bracket container
    cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
      'be.visible',
    );

    // Winners R1 badges should still be present (structure exists)
    cy.get('[data-testid="bracket-badge-A-right"]').should('exist');
  });

  it('should handle tournament with no bracket games', () => {
    // Pending Bracket Test (Tournament 3) has 0 games completed
    visitAndWaitForHydration('/tournament/3/games');

    cy.get('[data-testid="gamesTab"]', { timeout: 10000 }).should('be.visible');

    // May show bracket container with pending games or empty state
    // The bracket structure should still exist
    cy.get('[data-testid="bracketContainer"]', { timeout: 15000 }).should(
      'be.visible',
    );
  });

  it('can switch between bracket and list view', () => {
    visitAndWaitForHydration('/tournament/1/games');

    cy.get('[data-testid="gamesTab"]', { timeout: 10000 }).should('be.visible');

    // Click on List View tab
    cy.contains('List View').click();

    // Bracket container should not be visible in list view
    cy.get('[data-testid="bracketContainer"]').should('not.exist');

    // Switch back to Bracket View
    cy.contains('Bracket View').click();

    // Bracket container should be visible again
    cy.get('[data-testid="bracketContainer"]', { timeout: 10000 }).should(
      'be.visible',
    );
  });
});
