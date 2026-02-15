/**
 * Cross-Context Cache Invalidation
 *
 * @cicd smoke test verifying that editing a user on the league page
 * invalidates cacheops so the org page shows fresh data.
 *
 * Flow: edit nickname on league page → navigate to org page → verify new nickname.
 *
 * Uses isolated "User Edit" data — does not touch other test entities.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  openEditModal,
  readEditField,
  fillEditField,
  saveEditModal,
  restoreUserField,
} from '../../fixtures';

const API_URL = 'https://localhost/api';
const USER_EDIT_ORG_NAME = 'User Edit Org';
const USER_EDIT_LEAGUE_NAME = 'User Edit League';

let orgPk: number;
let leaguePk: number;

test.describe('Cross-Context Cache Invalidation (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Look up org
    const orgsResp = await context.request.get(`${API_URL}/organizations/`);
    const orgs = await orgsResp.json();
    const orgList = Array.isArray(orgs) ? orgs : orgs.results ?? [];
    const editOrg = orgList.find((o: { name: string }) => o.name === USER_EDIT_ORG_NAME);
    if (!editOrg) throw new Error(`Org "${USER_EDIT_ORG_NAME}" not found. Run just db::populate::all`);
    orgPk = editOrg.pk;

    // Look up league
    const leaguesResp = await context.request.get(`${API_URL}/leagues/`);
    const leagues = await leaguesResp.json();
    const leagueList = Array.isArray(leagues) ? leagues : leagues.results ?? [];
    const editLeague = leagueList.find((l: { name: string }) => l.name === USER_EDIT_LEAGUE_NAME);
    if (!editLeague) throw new Error(`League "${USER_EDIT_LEAGUE_NAME}" not found. Run just db::populate::all`);
    leaguePk = editLeague.pk;

    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd smoke: edit on league page, verify on org page', async ({ page }) => {
    // 1. Navigate to league page and edit nickname
    await visitAndWaitForHydration(page, `/leagues/${leaguePk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    const usersTab = page.locator('[data-testid="league-tab-users"]');
    await expect(usersTab).toBeVisible({ timeout: 5000 });
    await usersTab.click();

    const firstUserCard = page.locator('[data-testid^="usercard-"]').first();
    await expect(firstUserCard).toBeVisible({ timeout: 10000 });

    await openEditModal(page, firstUserCard);
    const originalNickname = await readEditField(page, 'nickname');
    const crossContextNick = originalNickname === 'CrossCtx' ? 'CrossCtxAlt' : 'CrossCtx';

    await fillEditField(page, 'nickname', crossContextNick);
    await saveEditModal(page);

    // 2. Navigate to org page and verify the new nickname is visible
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    const orgUsersTab = page.locator('[data-testid="org-tab-users"]');
    await expect(orgUsersTab).toBeVisible({ timeout: 5000 });
    await orgUsersTab.click();

    const orgUserCard = page.locator('[data-testid^="usercard-"]').first();
    await expect(orgUserCard).toBeVisible({ timeout: 10000 });

    // The new nickname should be visible on the org page (cacheops invalidated)
    await expect(page.getByText(crossContextNick).first()).toBeVisible({ timeout: 10000 });

    // 3. Restore original value from the org page
    await restoreUserField(page, orgUserCard, 'nickname', originalNickname);
  });
});
