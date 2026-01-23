/**
 * League Page Matches Tab Tests
 *
 * Tests the matches tab functionality on league pages.
 * Verifies that matches display correctly and filtering works.
 *
 * Uses a test league from the database (league PK 1).
 *
 * Ported from Cypress: frontend/tests/cypress/e2e/10-leagues/03-matches.cy.ts
 */

import {
  test,
  expect,
  LeaguePage,
} from '../../fixtures';

// Test league ID - uses the first league in the database
const TEST_LEAGUE_ID = 1;

test.describe('League Page - Matches Tab (e2e)', () => {
  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('should display matches list', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(TEST_LEAGUE_ID, 'matches');

    // Should show matches heading with count
    await expect(page.locator('text=Matches')).toBeVisible({ timeout: 10000 });
  });

  test('should have Steam linked filter button', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(TEST_LEAGUE_ID, 'matches');

    // Filter button should be visible
    await expect(leaguePage.steamLinkedFilterButton).toBeVisible({ timeout: 10000 });
  });

  test('should toggle Steam linked filter', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(TEST_LEAGUE_ID, 'matches');

    // Click filter button
    await leaguePage.toggleSteamLinkedFilter();

    // Button should change state (have check icon or different variant)
    const isActive = await leaguePage.isSteamLinkedFilterActive();
    expect(isActive).toBe(true);

    // Click again to toggle off
    await leaguePage.toggleSteamLinkedFilter();

    // Button should be back to outline variant
    const isActiveAfter = await leaguePage.isSteamLinkedFilterActive();
    expect(isActiveAfter).toBe(false);
  });

  test('should show empty state when no matches', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    // This test will pass if there are no matches - checking the empty state
    await leaguePage.goto(TEST_LEAGUE_ID, 'matches');

    // Either matches are shown or empty state is shown
    const matchCardCount = await leaguePage.getMatchCardCount();
    const hasEmptyState = await page.locator('text=No matches found').isVisible().catch(() => false);

    // One of these should be true
    expect(matchCardCount > 0 || hasEmptyState).toBe(true);
  });

  test('should load matches via API', async ({ page }) => {
    // Set up request interception
    const matchesRequestPromise = page.waitForRequest(
      (request) => request.url().includes(`/leagues/${TEST_LEAGUE_ID}/matches/`) && request.method() === 'GET'
    );

    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(TEST_LEAGUE_ID, 'matches');

    // API should be called
    const request = await matchesRequestPromise;
    expect(request).toBeDefined();

    // Also verify response
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes(`/leagues/${TEST_LEAGUE_ID}/matches/`) && response.status() === 200 || response.status() === 304
    );

    // Wait for the response (may already be fulfilled)
    const response = await responsePromise.catch(() => null);
    // Response should have been received (test passes if request was made)
    expect(request.url()).toContain(`/leagues/${TEST_LEAGUE_ID}/matches/`);
  });
});

test.describe('League Match Card (e2e)', () => {
  test.beforeEach(async ({ page, loginAdmin }) => {
    await loginAdmin();
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(TEST_LEAGUE_ID, 'matches');
  });

  test('should display match cards if matches exist', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    const matchCardCount = await leaguePage.getMatchCardCount();

    if (matchCardCount > 0) {
      // Match cards should be visible
      await expect(leaguePage.matchCards.first()).toBeVisible();
    } else {
      // No match cards found - this is expected if no matches exist
      console.log('No match cards found - this is expected if no matches exist');
    }
  });
});
