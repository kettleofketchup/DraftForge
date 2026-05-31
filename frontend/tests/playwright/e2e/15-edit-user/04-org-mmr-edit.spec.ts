/**
 * Edit User MMR on Organization Page
 *
 * @cicd smoke test verifying that editing a user's MMR on an org page
 * updates the UI. This exercises the org-scoped PATCH endpoint
 * (`/api/organizations/{orgPk}/users/{orgUserPk}/`) which only allows MMR.
 *
 * Uses isolated "User Edit Org" data — does not touch other test entities.
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

let orgPk: number;

test.describe('Edit User MMR on Organization Page (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    const orgsResp = await context.request.get(`${API_URL}/organizations/`);
    const orgs = await orgsResp.json();
    const orgList = Array.isArray(orgs) ? orgs : orgs.results ?? [];
    const editOrg = orgList.find((o: { name: string }) => o.name === USER_EDIT_ORG_NAME);
    if (!editOrg) throw new Error(`Org "${USER_EDIT_ORG_NAME}" not found. Run just db::populate::all`);
    orgPk = editOrg.pk;

    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  // Dedicated user — see USER_EDIT_USERS in backend/tests/data/users.py.
  const TARGET_USERNAME = 'edit_user_mmr';

  test('@cicd smoke: edit user MMR via org user card', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    const usersTab = page.locator('[data-testid="org-tab-users"]');
    await expect(usersTab).toBeVisible({ timeout: 5000 });
    await usersTab.click();

    const targetCard = page.locator(`[data-testid="usercard-${TARGET_USERNAME}"]`);
    await expect(targetCard).toBeVisible({ timeout: 10000 });

    await openEditModal(page, targetCard);
    const originalMmr = await readEditField(page, 'mmr');
    const newMmr = originalMmr === '9999' ? '8888' : '9999';

    await fillEditField(page, 'mmr', newMmr);
    await saveEditModal(page);

    // Allow store refresh + cache invalidation
    await expect(targetCard.getByText(newMmr).first()).toBeVisible({ timeout: 10000 });

    await restoreUserField(page, targetCard, 'mmr', originalMmr);
  });
});
