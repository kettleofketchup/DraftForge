import {
  suppressHydrationErrors,
} from 'tests/cypress/support/utils';
import {
  getMatchesTab,
  visitLeaguePage,
} from 'tests/cypress/helpers/league';
import { TEST_LEAGUE_ID } from './constants';

describe('League Page - Matches Tab (e2e)', () => {
  beforeEach(() => {
    suppressHydrationErrors();
    cy.loginAdmin();
  });

  it('should display matches list', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'matches');

    // Should show matches heading with count
    cy.contains('Matches', { timeout: 10000 }).should('be.visible');
  });

  it('should have Steam linked filter button', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'matches');

    // Filter button should be visible
    cy.contains('button', 'Steam linked only', { timeout: 10000 }).should('be.visible');
  });

  it('should toggle Steam linked filter', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'matches');

    // Click filter button
    cy.contains('button', 'Steam linked only').click();

    // Button should change state (have check icon or different variant)
    cy.contains('button', 'Steam linked only')
      .should('be.visible')
      .and('have.class', 'bg-primary');

    // Click again to toggle off
    cy.contains('button', 'Steam linked only').click();

    // Button should be back to outline variant
    cy.contains('button', 'Steam linked only')
      .should('be.visible')
      .and('not.have.class', 'bg-primary');
  });

  it('should show empty state when no matches', () => {
    // This test will pass if there are no matches - checking the empty state
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'matches');

    // Either matches are shown or empty state is shown
    cy.get('body').then(($body) => {
      const hasMatches = $body.find('[data-testid="league-match-card"]').length > 0;
      const hasEmptyState = $body.text().includes('No matches found');

      // One of these should be true
      expect(hasMatches || hasEmptyState).to.be.true;
    });
  });

  it('should load matches via API', () => {
    // Intercept the API call
    cy.intercept('GET', `**/leagues/${TEST_LEAGUE_ID}/matches/**`).as('getMatches');

    visitLeaguePage(cy, TEST_LEAGUE_ID, 'matches');

    // API should be called
    cy.wait('@getMatches', { timeout: 10000 }).then((interception) => {
      expect(interception.response?.statusCode).to.be.oneOf([200, 304]);
    });
  });
});

describe('League Match Card (e2e)', () => {
  beforeEach(() => {
    suppressHydrationErrors();
    cy.loginAdmin();
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'matches');
  });

  it('should display match cards if matches exist', () => {
    cy.get('body').then(($body) => {
      const matchCards = $body.find('[data-testid^="league-match-card"]');

      if (matchCards.length > 0) {
        // Match cards should be visible
        cy.get('[data-testid^="league-match-card"]').first().should('be.visible');
      } else {
        cy.log('No match cards found - this is expected if no matches exist');
      }
    });
  });
});
