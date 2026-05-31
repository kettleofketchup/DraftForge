/**
 * Edit User on Organization Page
 *
 * @cicd smoke test verifying that editing a user's nickname on an org page
 * updates the UI successfully.
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

test.describe('Edit User on Organization Page (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Look up User Edit Org by name
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

  // Dedicated user for this spec — never use `.first()` on usercard, that
  // races with every other 15-edit-user spec that also picks index 0.
  const TARGET_USERNAME = 'edit_user_org';

  test('@cicd smoke: edit user nickname via org user card', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    // Switch to Users tab
    const usersTab = page.locator('[data-testid="org-tab-users"]');
    await expect(usersTab).toBeVisible({ timeout: 5000 });
    await usersTab.click();

    const targetCard = page.locator(`[data-testid="usercard-${TARGET_USERNAME}"]`);
    await expect(targetCard).toBeVisible({ timeout: 10000 });

    await openEditModal(page, targetCard);
    const originalNickname = await readEditField(page, 'nickname');
    const newNickname = originalNickname === 'TestNick' ? 'TestNickAlt' : 'TestNick';

    await fillEditField(page, 'nickname', newNickname);
    await saveEditModal(page);

    await expect(targetCard.getByText(newNickname).first()).toBeVisible({ timeout: 5000 });

    await restoreUserField(page, targetCard, 'nickname', originalNickname);
  });
});
