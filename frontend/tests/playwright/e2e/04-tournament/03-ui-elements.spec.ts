/**
 * Tournament UI Elements Tests (E2E)
 *
 * Tests for tournament page UI elements and interactions.
 * Ported from Cypress: frontend/tests/cypress/e2e/04-tournament/03-ui-elements.cy.ts
 */

import {
  test,
  expect,
  getTournamentByKey,
  TournamentPage,
} from '../../fixtures';

test.describe('Tournament UI Elements (e2e)', () => {
  let tournamentPk: number;

  test.beforeAll(async ({ browser }) => {
    // Get tournament PK before tests run
    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
    });
    const tournament = await getTournamentByKey(context, 'completed_bracket');
    if (tournament) {
      tournamentPk = tournament.pk;
    } else {
      // Fallback to tournament 1 if lookup fails
      tournamentPk = 1;
    }
    await context.close();
  });

  test.beforeEach(async ({ loginAdmin, page }) => {
    // Login as admin before each test
    await loginAdmin();

    // Navigate to tournament players page
    await page.goto(`/tournament/${tournamentPk}/players`);

    // Wait for page to load
    await page
      .locator('[data-testid="tournamentDetailPage"]')
      .waitFor({ state: 'visible', timeout: 15000 });
  });

  test('should have all tournament page elements with proper test identifiers', async ({
    page,
  }) => {
    const tournamentPage = new TournamentPage(page);

    // Check main page elements
    await expect(tournamentPage.detailPage).toBeVisible();
    await expect(tournamentPage.title).toBeVisible();

    // Check tab navigation
    await expect(tournamentPage.tabsList).toBeVisible();
    await expect(tournamentPage.playersTab).toBeVisible();
    await expect(tournamentPage.teamsTab).toBeVisible();
    await expect(tournamentPage.bracketTab).toBeVisible();

    // Default should be players tab
    await expect(tournamentPage.playersTabContent).toBeVisible();
  });

  test('should have working add player UI elements', async ({ page }) => {
    const tournamentPage = new TournamentPage(page);

    // Open the add player dropdown
    await tournamentPage.addPlayerButton.scrollIntoViewIfNeeded();
    await expect(tournamentPage.addPlayerButton).toBeVisible();
    await tournamentPage.addPlayerButton.click({ force: true });

    // Verify the modal/dialog appears with search input
    await expect(tournamentPage.playerSearchInput).toBeVisible();

    // Verify the input accepts text
    await tournamentPage.playerSearchInput.fill('test');
    await expect(tournamentPage.playerSearchInput).toHaveValue('test');

    // Close by clicking cancel
    await page.getByText('Cancel').click({ force: true });
  });

  test('should be able to remove a player from tournament', async ({
    page,
  }) => {
    // Find the first player with a remove button (not the admin)
    const removeButton = page
      .locator('[data-testid^="removePlayerBtn-"]')
      .first();

    // Wait for remove button to be available
    await removeButton.waitFor({ state: 'visible', timeout: 10000 });
    await removeButton.scrollIntoViewIfNeeded();

    // Get the data-testid to extract username
    const testId = await removeButton.getAttribute('data-testid');
    expect(testId).toBeTruthy();

    // Extract username from data-testid="removePlayerBtn-{username}"
    const username = testId!.replace('removePlayerBtn-', '');

    // Click the remove button
    await removeButton.click({ force: true });

    // Check for success toast message
    await expect(page.getByText(/removed|deleted/i)).toBeVisible({
      timeout: 5000,
    });

    // Verify the user card is no longer visible
    await expect(
      page.locator(`[data-testid="usercard-${username}"]`)
    ).not.toBeVisible();
  });
});
