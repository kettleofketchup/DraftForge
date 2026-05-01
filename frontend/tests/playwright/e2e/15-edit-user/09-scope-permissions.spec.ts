/**
 * Scope-aware permission gating.
 *
 * The legacy modal hard-coded `is_staff || is_superuser`, locking out
 * non-Django-staff org admins. The new scope-aware gate lets org admins
 * edit on their org page (org scope) but NOT on user profile pages
 * (global scope = superuser-only).
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
} from '../../fixtures';

const API_URL = 'https://localhost/api';
const USER_EDIT_ORG_NAME = 'User Edit Org';
let orgPk: number;
let targetUserPk: number;

test.describe('Scope permissions (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const orgs = await (await context.request.get(`${API_URL}/organizations/`)).json();
    const orgList = Array.isArray(orgs) ? orgs : orgs.results ?? [];
    const editOrg = orgList.find((o: { name: string }) => o.name === USER_EDIT_ORG_NAME);
    orgPk = editOrg.pk;
    const usersResp = await context.request.get(`${API_URL}/organizations/${orgPk}/users/`);
    const users = await usersResp.json();
    // Pick a target user that is neither the test actor (pk=1020 / org_admin_tester)
    // nor the global admin (pk=1, who has is_superuser=true and would render the
    // edit button regardless of scope, defeating the assertion).
    targetUserPk = users.find(
      (u: any) =>
        u.pk !== 1020 && u.pk !== 1 && u.username !== 'org_admin_tester'
    ).pk;
    await context.close();
  });

  test('org admin (non-superuser) sees edit button on org page', async ({
    page,
    loginOrgAdmin,
  }) => {
    await loginOrgAdmin();
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const card = page.locator('[data-testid^="usercard-"]').first();
    await expect(card).toBeVisible({ timeout: 10000 });
    await expect(card.locator('[data-testid="edit-user-btn"]')).toBeVisible();
  });

  test('org admin (non-superuser) does NOT see edit button on /user/:pk profile page', async ({
    page,
    loginOrgAdmin,
  }) => {
    await loginOrgAdmin();
    await visitAndWaitForHydration(page, `/user/${targetUserPk}`);
    await expect(page.locator('h1, [data-testid="user-profile-heading"]').first()).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator('[data-testid="edit-user-btn"]')).toHaveCount(0);
  });

  test('superuser on /user/:pk does NOT see MMR field in edit modal', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();
    await visitAndWaitForHydration(page, `/user/${targetUserPk}`);
    const editBtn = page.locator('[data-testid="edit-user-btn"]');
    await expect(editBtn).toBeVisible({ timeout: 10000 });
    await editBtn.click();
    await expect(page.locator('[data-testid="edit-user-nickname"]')).toBeVisible();
    await expect(page.locator('[data-testid="edit-user-mmr"]')).toHaveCount(0);
  });
});
