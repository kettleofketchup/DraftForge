/**
 * After an org-scoped PATCH (returns slim OrgUserSerializer payload),
 * the cached user entry must still expose `username`, `discordId`,
 * `is_staff`, etc. from the prior cache state — i.e., upsert
 * merges scope-divergent payloads instead of replacing the entry.
 *
 * useUserCacheStore.upsert (frontend/app/store/userCacheStore.ts) routes
 * through toUserEntry → pick() which only copies keys present in the
 * incoming payload, so absent keys preserve existing values. This spec
 * pins that property by:
 *   1. Visiting /user/:pk to prime the cache with the FULL UserSerializer
 *      payload (includes username, discordId, is_staff, etc.).
 *   2. Editing the same user from the org page (PATCH returns slim
 *      OrgUserSerializer — no username, no discordId, no is_staff).
 *   3. Returning to /user/:pk and asserting the username still renders.
 *      If upsert clobbered with the slim payload, username would be
 *      undefined and the Profile Details row would not appear.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  openEditModal,
  fillEditField,
  saveEditModal,
} from '../../fixtures';

const API_URL = 'https://localhost/api';
const USER_EDIT_ORG_NAME = 'User Edit Org';
let orgPk: number;
let targetUserPk: number;
let targetUsername: string;

test.describe('User cache merge after org PATCH (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const orgs = await (await context.request.get(`${API_URL}/organizations/`)).json();
    const orgList = Array.isArray(orgs) ? orgs : orgs.results ?? [];
    const editOrg = orgList.find((o: { name: string }) => o.name === USER_EDIT_ORG_NAME);
    orgPk = editOrg.pk;
    const usersResp = await context.request.get(`${API_URL}/organizations/${orgPk}/users/`);
    const users = await usersResp.json();
    // Skip the global superuser (pk=1) and the org-admin actor (pk=1020) —
    // see 09-scope-permissions.spec.ts for the same filter pattern.
    const target = users.find(
      (u: { pk: number; username?: string }) =>
        u.pk !== 1 && u.pk !== 1020 && u.username && u.username !== 'org_admin_tester',
    );
    if (!target) throw new Error('No suitable target user in User Edit Org');
    targetUserPk = target.pk;
    targetUsername = target.username;
    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd profile-page username survives an org-scoped PATCH', async ({ page }) => {
    // 1. Prime the cache with the FULL UserSerializer payload by visiting
    //    the profile page. The Profile Details card renders user.username
    //    in a dedicated row; that row only appears if the cached entry
    //    still has the username field.
    await visitAndWaitForHydration(page, `/user/${targetUserPk}`);
    await expect(
      page.getByText(targetUsername, { exact: true }).first(),
    ).toBeVisible({ timeout: 10000 });

    // 2. Switch to the org page and edit the user. The org PATCH endpoint
    //    returns the slim OrgUserSerializer (no username/discordId/is_staff).
    //    If upsert replaced instead of merged, the cached entry would lose
    //    those fields.
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const card = page.locator(`[data-testid="usercard-${targetUsername}"]`);
    await expect(card).toBeVisible({ timeout: 10000 });
    await openEditModal(page, card);
    await fillEditField(page, 'nickname', `MergeTest-${Date.now()}`);
    await saveEditModal(page);

    // 3. Return to the profile page. The username must still render —
    //    proving the slim PATCH response merged into the cached entry
    //    rather than replacing it.
    await visitAndWaitForHydration(page, `/user/${targetUserPk}`);
    await expect(
      page.getByText(targetUsername, { exact: true }).first(),
    ).toBeVisible({ timeout: 5000 });
  });
});
