/**
 * AddUserModal Smoke Tests
 *
 * @cicd smoke tests verifying the AddUserModal opens, searches, and displays
 * results on Organization, League, and Tournament pages.
 *
 * Uses admin login (superuser has access everywhere).
 * Fetches dynamic IDs for the first available league (which gives us org + league),
 * and uses getTournamentByKey for a known tournament.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getFirstLeague,
  getTournamentByKey,
} from '../../fixtures';

const API_URL = 'https://localhost/api';

let orgPk: number;
let leaguePk: number;
let tournamentPk: number;

test.describe('AddUserModal Smoke Tests', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Get first league (gives us both org and league PKs)
    const league = await getFirstLeague(context);
    if (!league) throw new Error('No leagues found. Run just db::populate::all');
    leaguePk = league.pk;

    // Fetch league detail to get org PK (organization is a nested object)
    const leagueResp = await context.request.get(`${API_URL}/leagues/${leaguePk}/`);
    const leagueData = await leagueResp.json();
    orgPk = typeof leagueData.organization === 'object'
      ? leagueData.organization.pk
      : leagueData.organization;

    // Get a tournament
    const tournament = await getTournamentByKey(context, 'bracket_unset_winner');
    if (!tournament) throw new Error('No bracket_unset_winner tournament found');
    tournamentPk = tournament.pk;

    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd smoke: org add-member modal opens and searches', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);

    // Wait for org page to load (title appears)
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    // Switch to Users tab
    const usersTab = page.locator('[data-testid="org-tab-users"]');
    await expect(usersTab).toBeVisible({ timeout: 5000 });
    await usersTab.click();

    // Wait for Add Member button and click it
    const addBtn = page.locator('[data-testid="org-add-member-btn"]');
    await expect(addBtn).toBeVisible({ timeout: 10000 });
    await addBtn.click();

    // Modal should open
    const modal = page.locator('[data-testid="add-user-modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });

    // Search input should be present
    const searchInput = modal.locator('[data-testid="add-user-search"]');
    await expect(searchInput).toBeVisible();

    // Type a search query (3+ chars to trigger search)
    await searchInput.fill('test');

    // Wait for search results section to render (desktop heading or empty state)
    await expect(modal.getByRole('heading', { name: 'Site Users' })).toBeVisible({ timeout: 5000 });

    // Close modal with Escape
    await page.keyboard.press('Escape');
    await expect(modal).not.toBeVisible();
  });

  test('@cicd smoke: league add-member modal opens and searches', async ({ page }) => {
    await visitAndWaitForHydration(page, `/leagues/${leaguePk}`);

    // Wait for league page to load
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    // Switch to Users tab
    const usersTab = page.locator('[data-testid="league-tab-users"]');
    await expect(usersTab).toBeVisible({ timeout: 5000 });
    await usersTab.click();

    // Wait for Add Member button and click it
    const addBtn = page.locator('[data-testid="league-add-member-btn"]');
    await expect(addBtn).toBeVisible({ timeout: 10000 });
    await addBtn.click();

    // Modal should open
    const modal = page.locator('[data-testid="add-user-modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });

    // Search input should be present
    const searchInput = modal.locator('[data-testid="add-user-search"]');
    await expect(searchInput).toBeVisible();

    // Type a search query
    await searchInput.fill('test');

    // Wait for search results section to render
    await expect(modal.getByRole('heading', { name: 'Site Users' })).toBeVisible({ timeout: 5000 });

    // Close modal
    await page.keyboard.press('Escape');
    await expect(modal).not.toBeVisible();
  });

  test('@cicd smoke: tournament add-player modal opens and searches', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);

    // Wait for tournament page to load
    await expect(page.locator('[data-testid="tournamentDetailPage"]')).toBeVisible({ timeout: 15000 });

    // Should land on players tab by default
    const addBtn = page.locator('[data-testid="tournamentAddPlayerBtn"]');
    await expect(addBtn).toBeVisible({ timeout: 10000 });
    await addBtn.click();

    // Modal should open
    const modal = page.locator('[data-testid="add-user-modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });

    // Search input should be present
    const searchInput = modal.locator('[data-testid="add-user-search"]');
    await expect(searchInput).toBeVisible();

    // Type a search query
    await searchInput.fill('test');

    // Wait for search results section to render
    await expect(modal.getByRole('heading', { name: 'Site Users' })).toBeVisible({ timeout: 5000 });

    // Close modal
    await page.keyboard.press('Escape');
    await expect(modal).not.toBeVisible();
  });
});
