/**
 * Sequential multi-user edit regression test.
 *
 * Pins the bug originally reported: editing user A then user B in succession
 * caused fields to "stick" or revert. Also pins the dirty-fields PATCH
 * behavior — only changed fields land in the request body.
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

// Sequential: each test in this file edits one or both shared users
// (alpha + bravo) and the order matters (an earlier nickname change is
// asserted against by a later test via getByText). `.serial` keeps these
// tests in declaration order; using dedicated usernames keeps them from
// racing with parallel specs in this directory.
const USER_A_USERNAME = 'edit_user_alpha';
const USER_B_USERNAME = 'edit_user_bravo';

test.describe.serial('Sequential multi-user edits (@cicd)', () => {
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

  test('@cicd edit user A and user B sequentially; both saves persist', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();

    const cardA = page.locator(`[data-testid="usercard-${USER_A_USERNAME}"]`);
    const cardB = page.locator(`[data-testid="usercard-${USER_B_USERNAME}"]`);
    await expect(cardA).toBeVisible({ timeout: 10000 });
    await expect(cardB).toBeVisible({ timeout: 10000 });

    // Edit user A: nickname + MMR
    await openEditModal(page, cardA);
    const newNickA = `SeqA-${Date.now()}`;
    await fillEditField(page, 'nickname', newNickA);
    await fillEditField(page, 'mmr', '6500');
    await saveEditModal(page);

    // Edit user B: nickname only
    await openEditModal(page, cardB);
    const newNickB = `SeqB-${Date.now()}`;
    await fillEditField(page, 'nickname', newNickB);
    await saveEditModal(page);

    // Reload and verify both persist
    await page.reload();
    await page.locator('[data-testid="org-tab-users"]').click();
    await expect(cardA.getByText(newNickA).first()).toBeVisible({ timeout: 5000 });
    await expect(cardB.getByText(newNickB).first()).toBeVisible({ timeout: 5000 });
  });

  test('@cicd PATCH body contains only dirty fields', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const card = page.locator(`[data-testid="usercard-${USER_A_USERNAME}"]`);
    await expect(card).toBeVisible({ timeout: 10000 });

    await openEditModal(page, card);

    const patchPromise = page.waitForRequest(
      (req) => req.method() === 'PATCH' && /\/users\//.test(req.url()),
      { timeout: 10000 },
    );

    const newNick = `Dirty-${Date.now()}`;
    await fillEditField(page, 'nickname', newNick);
    await saveEditModal(page);

    const patch = await patchPromise;
    const body = JSON.parse(patch.postData() || '{}');
    expect(Object.keys(body).sort()).toEqual(['nickname']);
    expect(body.nickname).toBe(newNick);
  });

  test('@cicd save with no changes does not fire a PATCH', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const card = page.locator(`[data-testid="usercard-${USER_A_USERNAME}"]`);
    await expect(card).toBeVisible({ timeout: 10000 });

    await openEditModal(page, card);

    let patchCount = 0;
    page.on('request', (req) => {
      if (req.method() === 'PATCH' && /\/users\//.test(req.url())) patchCount++;
    });

    await page.getByRole('button', { name: 'Save Changes' }).click();
    await page.waitForTimeout(800);
    expect(patchCount).toBe(0);
  });
});
