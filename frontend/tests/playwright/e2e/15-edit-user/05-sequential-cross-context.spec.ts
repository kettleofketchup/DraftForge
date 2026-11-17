/**
 * Cross-Context Cache Invalidation
 *
 * @cicd smoke test verifying that editing a user on the league page
 * invalidates cacheops so the org page shows fresh data.
 *
 * Flow: edit Friend ID on league page → navigate to org page → the org page's
 * edit modal shows the new Friend ID.
 *
 * Uses isolated "User Edit" data — does not touch other test entities.
 */

import {
  expect,
  fillEditField,
  nextSteamAccountId,
  openEditModal,
  readEditField,
  restoreUserField,
  saveEditModal,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

const USER_EDIT_ORG_NAME = 'User Edit Org';
const USER_EDIT_LEAGUE_NAME = 'User Edit League';
const ALT_STEAM_ACCOUNT_ID = 2_900_000_501;

let orgPk: number;
let leaguePk: number;

// Sequential: this spec edits a user on the league page and then asserts
// the new value is visible on the org page. Any parallel write on the
// same user would invalidate the read. `.serial` forces tests within this
// file to run in order; we also share `edit_user_alpha` with spec
// 07-sequential-multi-user (which is also `.serial`) — see USER_EDIT_USERS.
const TARGET_USERNAME = 'edit_user_alpha';

test.describe.serial('Cross-Context Cache Invalidation (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Look up org
    const orgsResp = await context.request.get(`${API_URL}/organizations/`);
    const orgs = await orgsResp.json();
    const orgList = Array.isArray(orgs) ? orgs : (orgs.results ?? []);
    const editOrg = orgList.find(
      (o: { name: string }) => o.name === USER_EDIT_ORG_NAME,
    );
    if (!editOrg)
      throw new Error(
        `Org "${USER_EDIT_ORG_NAME}" not found. Run just db::populate::all`,
      );
    orgPk = editOrg.pk;

    // Look up league
    const leaguesResp = await context.request.get(`${API_URL}/leagues/`);
    const leagues = await leaguesResp.json();
    const leagueList = Array.isArray(leagues)
      ? leagues
      : (leagues.results ?? []);
    const editLeague = leagueList.find(
      (l: { name: string }) => l.name === USER_EDIT_LEAGUE_NAME,
    );
    if (!editLeague)
      throw new Error(
        `League "${USER_EDIT_LEAGUE_NAME}" not found. Run just db::populate::all`,
      );
    leaguePk = editLeague.pk;

    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd smoke: edit on league page, verify on org page', async ({
    page,
  }) => {
    // 1. Navigate to league page and edit the Friend ID
    await visitAndWaitForHydration(page, `/leagues/${leaguePk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    const usersTab = page.locator('[data-testid="league-tab-users"]');
    await expect(usersTab).toBeVisible({ timeout: 5000 });
    await usersTab.click();

    const leagueCard = page.locator(
      `[data-testid="usercard-${TARGET_USERNAME}"]`,
    );
    await expect(leagueCard).toBeVisible({ timeout: 10000 });

    await openEditModal(page, leagueCard);
    const originalId = await readEditField(page, 'steam_account_id');
    const crossContextId = nextSteamAccountId(originalId, ALT_STEAM_ACCOUNT_ID);

    await fillEditField(page, 'steam_account_id', crossContextId);
    await saveEditModal(page);

    // 2. Navigate to org page and verify the new Friend ID is served there
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    const orgUsersTab = page.locator('[data-testid="org-tab-users"]');
    await expect(orgUsersTab).toBeVisible({ timeout: 5000 });
    await orgUsersTab.click();

    const orgUserCard = page.locator(
      `[data-testid="usercard-${TARGET_USERNAME}"]`,
    );
    await expect(orgUserCard).toBeVisible({ timeout: 10000 });

    // The org users payload carries the new Friend ID (cacheops invalidated)
    await openEditModal(page, orgUserCard);
    await expect(
      page.locator('[data-testid="edit-user-steam_account_id"]'),
    ).toHaveValue(crossContextId, {
      timeout: 10000,
    });
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-testid="edit-user-modal"]')).toBeHidden({
      timeout: 5000,
    });

    // 3. Restore original value from the org page
    await restoreUserField(page, orgUserCard, 'steam_account_id', originalId);
  });
});
