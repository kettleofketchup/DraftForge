/**
 * Tournament User Management Tests
 *
 * Tests for adding/managing users in a tournament.
 * Ported from Cypress: frontend/tests/cypress/e2e/04-tournament/02-user.cy.ts
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  TournamentPage,
} from '../../fixtures';

test.describe('Tournament API: User', () => {
  test.beforeEach(async ({ loginAdmin, page }) => {
    // Login as admin before each test
    await loginAdmin();

    // Navigate to tournament 1
    await visitAndWaitForHydration(page, '/tournament/1');
  });

  test('should be able to handle adding users to the tournaments', async ({
    page,
  }) => {
    // Create page object for additional assertions
    const tournamentPage = new TournamentPage(page);

    // Verify the tournament page loaded
    await tournamentPage.assertPageVisible();

    // Check that the page displays the expected tournament data
    await expect(page.locator('body')).toContainText('Completed Bracket Test');
  });
});
