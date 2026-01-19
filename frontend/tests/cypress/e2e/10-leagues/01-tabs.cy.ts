import {
  suppressHydrationErrors,
  visitAndWaitForHydration,
} from 'tests/cypress/support/utils';
import {
  getInfoTab,
  getTournamentsTab,
  getMatchesTab,
  visitLeaguePage,
} from 'tests/cypress/helpers/league';
import { TEST_LEAGUE_ID } from './constants';

describe('League Page - Tab Navigation (e2e)', () => {
  beforeEach(() => {
    suppressHydrationErrors();
    // Login as admin to ensure we have access
    cy.loginAdmin();
  });

  it('should load the league page with info tab by default', () => {
    visitAndWaitForHydration(`/leagues/${TEST_LEAGUE_ID}`);

    // Info tab should be active by default
    getInfoTab(cy).should('be.visible');
    getTournamentsTab(cy).should('be.visible');
    getMatchesTab(cy).should('be.visible');

    // Check URL includes the league ID
    cy.url().should('include', `/leagues/${TEST_LEAGUE_ID}`);
  });

  it('should navigate to tournaments tab', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Click on tournaments tab
    getTournamentsTab(cy).click();

    // URL should update
    cy.url().should('include', `/leagues/${TEST_LEAGUE_ID}/tournaments`);

    // Tournaments content should be visible
    cy.contains('Tournaments').should('be.visible');
  });

  it('should navigate to matches tab', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Click on matches tab
    getMatchesTab(cy).click();

    // URL should update
    cy.url().should('include', `/leagues/${TEST_LEAGUE_ID}/matches`);

    // Matches content should be visible
    cy.contains('Matches').should('be.visible');
  });

  it('should navigate back to info tab', () => {
    // Start on matches tab
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'matches');

    // Click on info tab
    getInfoTab(cy).click();

    // URL should update
    cy.url().should('include', `/leagues/${TEST_LEAGUE_ID}/info`);
  });

  it('should load correct tab from URL', () => {
    // Visit tournaments tab directly via URL
    visitAndWaitForHydration(`/leagues/${TEST_LEAGUE_ID}/tournaments`);

    // Tournaments tab content should be visible
    cy.url().should('include', '/tournaments');

    // The tab should be active
    getTournamentsTab(cy).should('have.attr', 'data-state', 'active');
  });

  it('should handle browser back/forward navigation', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Navigate through tabs
    getTournamentsTab(cy).click();
    cy.url().should('include', '/tournaments');

    getMatchesTab(cy).click();
    cy.url().should('include', '/matches');

    // Go back
    cy.go('back');
    cy.url().should('include', '/tournaments');

    // Go forward
    cy.go('forward');
    cy.url().should('include', '/matches');
  });

  it('should display league name in header', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // League name should be displayed in header
    cy.get('h1').should('be.visible');
  });

  it('should show tournaments count in tab', () => {
    visitLeaguePage(cy, TEST_LEAGUE_ID, 'info');

    // Tournaments tab should show count in parentheses
    getTournamentsTab(cy).should('contain.text', 'Tournaments');
    // The tab text includes count like "Tournaments (5)"
    getTournamentsTab(cy).invoke('text').should('match', /Tournaments\s*\(\d+\)/);
  });
});
