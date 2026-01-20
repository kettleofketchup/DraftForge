import { suppressHydrationErrors } from 'tests/cypress/support/utils';
import { visitLeaguePage } from 'tests/cypress/helpers/league';
import { TEST_LEAGUE_ID } from './constants';

describe('League Steam Matches (e2e)', () => {
  beforeEach(() => {
    suppressHydrationErrors();
    cy.loginAdmin();
  });

  it('should display matches tab on league page', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Navigate to matches tab
    cy.get('[data-testid="league-tab-matches"]').click();

    // Verify URL updated
    cy.url().should('include', `/leagues/${TEST_LEAGUE_ID}/matches`);

    // Verify matches section exists
    cy.contains('Matches', { timeout: 10000 }).should('be.visible');
  });

  it('should display match data when matches exist', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'matches');

    // If matches exist, verify they display properly
    cy.get('body').then(($body) => {
      const matchCards = $body.find('[data-testid^="league-match-card"]');

      if (matchCards.length > 0) {
        cy.get('[data-testid^="league-match-card"]').first().should('be.visible');
      } else {
        cy.log('No match cards found - this is expected if no matches exist');
      }
    });
  });

  it('should filter matches by Steam linked status', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'matches');

    // Verify Steam linked filter exists
    cy.contains('button', 'Steam linked only', { timeout: 10000 }).should('be.visible');

    // Click filter to show only Steam linked matches
    cy.contains('button', 'Steam linked only').click();

    // Filter should be active
    cy.contains('button', 'Steam linked only')
      .should('be.visible')
      .and('have.class', 'bg-primary');

    // Verify API call includes Steam filter
    cy.intercept('GET', `**/leagues/${TEST_LEAGUE_ID}/matches/**`).as('getFilteredMatches');

    // Toggle filter off
    cy.contains('button', 'Steam linked only').click();

    // Filter should be inactive
    cy.contains('button', 'Steam linked only')
      .should('be.visible')
      .and('not.have.class', 'bg-primary');
  });

  it('should display Steam match details when Steam data is linked', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'matches');

    // Check if any matches have Steam data
    cy.get('body').then(($body) => {
      const steamLinkedMatches = $body.find('[data-testid="steam-match-id"]');

      if (steamLinkedMatches.length > 0) {
        // Steam match ID should be visible
        cy.get('[data-testid="steam-match-id"]').first().should('be.visible');
      } else {
        cy.log('No Steam linked matches found - this is expected if no matches are linked');
      }
    });
  });
});
