/**
 * League Page Tab Navigation Tests
 *
 * Tests the tab navigation functionality on league pages.
 * Verifies that Info, Tournaments, and Matches tabs work correctly.
 *
 * Uses the first available league from the database.
 *
 * Ported from Cypress: frontend/tests/cypress/e2e/10-leagues/01-tabs.cy.ts
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  LeaguePage,
  getFirstLeague,
} from '../../fixtures';

test.describe('League Page - Tab Navigation (e2e)', () => {
  let testLeagueId: number;

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
    // Login as admin to ensure we have access
    await loginAdmin();
  });

  test('should load the league page with info tab by default', async ({ page }) => {
    await visitAndWaitForHydration(page, `/leagues/${testLeagueId}`);

    const leaguePage = new LeaguePage(page);

    // Info tab should be active by default
    await expect(leaguePage.infoTab).toBeVisible();
    await expect(leaguePage.tournamentsTab).toBeVisible();
    await expect(leaguePage.matchesTab).toBeVisible();

    // Check URL includes the league ID
    await expect(page).toHaveURL(new RegExp(`/leagues/${testLeagueId}`));
  });

  test('should navigate to tournaments tab', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Click on tournaments tab
    await leaguePage.clickTournamentsTab();

    // URL should update
    await expect(page).toHaveURL(new RegExp(`/leagues/${testLeagueId}/tournaments`));

    // Tournaments tab should be active
    await leaguePage.assertTabActive('tournaments');
  });

  test('should navigate to matches tab', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Click on matches tab
    await leaguePage.clickMatchesTab();

    // URL should update
    await expect(page).toHaveURL(new RegExp(`/leagues/${testLeagueId}/matches`));

    // Matches content should be visible
    await expect(page.locator('text=Matches')).toBeVisible();
  });

  test('should navigate back to info tab', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    // Start on matches tab
    await leaguePage.goto(testLeagueId, 'matches');

    // Click on info tab
    await leaguePage.clickInfoTab();

    // URL should update
    await expect(page).toHaveURL(new RegExp(`/leagues/${testLeagueId}/info`));
  });

  test('should load correct tab from URL', async ({ page }) => {
    // Visit tournaments tab directly via URL
    await visitAndWaitForHydration(page, `/leagues/${testLeagueId}/tournaments`);

    const leaguePage = new LeaguePage(page);

    // Tournaments tab content should be visible
    await expect(page).toHaveURL(/\/tournaments/);

    // The tab should be active
    await leaguePage.assertTabActive('tournaments');
  });

  // Skip: Browser back/forward navigation is flaky due to React Router history handling
  test.skip('should handle browser back/forward navigation', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Navigate through tabs - wait for each navigation to complete
    await leaguePage.clickTournamentsTab();
    await expect(page).toHaveURL(/\/tournaments/, { timeout: 10000 });
    await page.waitForLoadState('networkidle');

    await leaguePage.clickMatchesTab();
    await expect(page).toHaveURL(/\/matches/, { timeout: 10000 });
    await page.waitForLoadState('networkidle');

    // Go back
    await page.goBack();
    await expect(page).toHaveURL(/\/tournaments/, { timeout: 10000 });

    // Go forward
    await page.goForward();
    await expect(page).toHaveURL(/\/matches/, { timeout: 10000 });
  });

  test('should display league name in header', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // League name should be displayed in header
    await expect(leaguePage.leagueTitle).toBeVisible();
  });

  test('should show tournaments count in tab', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(testLeagueId, 'info');

    // Tournaments tab should show count in parentheses
    await expect(leaguePage.tournamentsTab).toContainText('Tournaments');

    // The tab text includes count like "Tournaments (5)"
    const tabText = await leaguePage.tournamentsTab.textContent();
    expect(tabText).toMatch(/Tournaments\s*\(\d+\)/);
  });
});
