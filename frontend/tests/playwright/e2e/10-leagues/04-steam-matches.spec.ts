/**
 * League Steam Matches Tests
 *
 * Tests the Steam-linked match functionality on league pages.
 * Verifies that Steam match data is displayed and filtered correctly.
 *
 * Uses the first available league from the database.
 *
 * Ported from Cypress: frontend/tests/cypress/e2e/10-leagues/04-steam-matches.cy.ts
 */

import {
  test,
  expect,
  LeaguePage,
  getFirstLeague,
} from '../../fixtures';

// Will be set dynamically in beforeAll
let testLeagueId: number;

test.describe('League Steam Matches (e2e)', () => {
  test.beforeAll(async ({ browser }) => {
    // Get the first available league dynamically
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const league = await getFirstLeague(context);
    if (!league) {
      throw new Error('No leagues found in database. Run inv db.populate.all first.');
    }
    testLeagueId = league.pk;
    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('should display matches tab on league page', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Navigate to matches tab
    await leaguePage.clickMatchesTab();

    // Verify URL updated
    await expect(page).toHaveURL(new RegExp(`/leagues/${testLeagueId}/matches`));

    // Verify matches section exists - use h3 heading which shows "Matches (N)"
    await expect(page.locator('h3:has-text("Matches")')).toBeVisible({ timeout: 10000 });
  });

  test('should display match data when matches exist', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'matches');

    // If matches exist, verify they display properly
    const matchCardCount = await leaguePage.getMatchCardCount();

    if (matchCardCount > 0) {
      await expect(leaguePage.matchCards.first()).toBeVisible();
    } else {
      console.log('No match cards found - this is expected if no matches exist');
    }
  });

  test('should filter matches by Steam linked status', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'matches');

    // Verify Steam linked filter exists
    await expect(leaguePage.steamLinkedFilterButton).toBeVisible({ timeout: 10000 });

    // Click filter to show only Steam linked matches
    await leaguePage.toggleSteamLinkedFilter();

    // Filter should be active
    const isActive = await leaguePage.isSteamLinkedFilterActive();
    expect(isActive).toBe(true);

    // Toggle filter off
    await leaguePage.toggleSteamLinkedFilter();

    // Filter should be inactive
    const isActiveAfter = await leaguePage.isSteamLinkedFilterActive();
    expect(isActiveAfter).toBe(false);
  });

  test('should display Steam match details when Steam data is linked', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'matches');

    // Check if any matches have Steam data
    const steamMatchIdLocator = page.locator('[data-testid="steam-match-id"]');
    const steamLinkedMatchCount = await steamMatchIdLocator.count();

    if (steamLinkedMatchCount > 0) {
      // Steam match ID should be visible
      await expect(steamMatchIdLocator.first()).toBeVisible();
    } else {
      console.log('No Steam linked matches found - this is expected if no matches are linked');
    }
  });
});
