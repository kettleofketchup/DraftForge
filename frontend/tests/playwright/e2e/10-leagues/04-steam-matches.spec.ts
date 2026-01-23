/**
 * League Steam Matches Tests
 *
 * Tests the Steam-linked match functionality on league pages.
 * Verifies that Steam match data is displayed and filtered correctly.
 *
 * Uses a test league from the database (league PK 1).
 *
 * Ported from Cypress: frontend/tests/cypress/e2e/10-leagues/04-steam-matches.cy.ts
 */

import {
  test,
  expect,
  LeaguePage,
} from '../../fixtures';

// Test league ID - uses the first league in the database
const TEST_LEAGUE_ID = 1;

test.describe('League Steam Matches (e2e)', () => {
  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('should display matches tab on league page', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(TEST_LEAGUE_ID, 'info');

    // Navigate to matches tab
    await leaguePage.clickMatchesTab();

    // Verify URL updated
    await expect(page).toHaveURL(new RegExp(`/leagues/${TEST_LEAGUE_ID}/matches`));

    // Verify matches section exists
    await expect(page.locator('text=Matches')).toBeVisible({ timeout: 10000 });
  });

  test('should display match data when matches exist', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(TEST_LEAGUE_ID, 'matches');

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
    await leaguePage.goto(TEST_LEAGUE_ID, 'matches');

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
    await leaguePage.goto(TEST_LEAGUE_ID, 'matches');

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
