/**
 * Scope-aware permission gating.
 *
 * The legacy modal hard-coded `is_staff || is_superuser`, locking out
 * non-Django-staff org admins. The new scope-aware gate lets org admins
 * edit on their org page (org scope) but NOT on user profile pages
 * (global scope = superuser-only).
 */

import {
  expect,
  loginAdmin as loginAdminContext,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

const USER_EDIT_ORG_NAME = 'User Edit Org';
// Dedicated non-staff member of User Edit Org, used by no other spec —
// see USER_EDIT_USERS in backend/tests/data/users.py.
const TARGET_USERNAME = 'edit_user_scope';
let orgPk: number;
let targetUserPk: number;

test.describe('Scope permissions (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    // The org member list is restricted to members and org staff.
    await loginAdminContext(context);
    const orgs = await (
      await context.request.get(`${API_URL}/organizations/`)
    ).json();
    const orgList = Array.isArray(orgs) ? orgs : (orgs.results ?? []);
    const editOrg = orgList.find(
      (o: { name: string }) => o.name === USER_EDIT_ORG_NAME,
    );
    if (!editOrg)
      throw new Error(
        `Org "${USER_EDIT_ORG_NAME}" not found. Run just db::populate::all`,
      );
    orgPk = editOrg.pk;
    const usersResp = await context.request.get(
      `${API_URL}/organizations/${orgPk}/users/`,
    );
    const users = await usersResp.json();
    const target = users.find(
      (u: { username?: string }) => u.username === TARGET_USERNAME,
    );
    if (!target)
      throw new Error(`Target user "${TARGET_USERNAME}" not in User Edit Org`);
    targetUserPk = target.pk;
    await context.close();
  });

  test('org admin (non-superuser) sees edit button on org page', async ({
    page,
    loginOrgAdmin,
  }) => {
    await loginOrgAdmin();
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const card = page.locator(`[data-testid="usercard-${TARGET_USERNAME}"]`);
    await expect(card).toBeVisible({ timeout: 10000 });
    await expect(card.locator('[data-testid="edit-user-btn"]')).toBeVisible();
  });

  test('org admin (non-superuser) does NOT see edit button on /user/:pk profile page', async ({
    page,
    loginOrgAdmin,
  }) => {
    await loginOrgAdmin();
    await visitAndWaitForHydration(page, `/user/${targetUserPk}`);
    await expect(
      page.locator('h1, [data-testid="user-profile-heading"]').first(),
    ).toBeVisible({
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
    await expect(
      page.locator('[data-testid="edit-user-nickname"]'),
    ).toBeVisible();
    await expect(page.locator('[data-testid="edit-user-mmr"]')).toHaveCount(0);
  });
});
