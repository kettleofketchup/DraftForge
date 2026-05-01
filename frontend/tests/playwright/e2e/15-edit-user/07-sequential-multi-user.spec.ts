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

test.describe('Sequential multi-user edits (@cicd)', () => {
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

    const userCards = page.locator('[data-testid^="usercard-"]');
    await expect(userCards.first()).toBeVisible({ timeout: 10000 });

    // Edit user A: nickname + MMR
    const cardA = userCards.nth(0);
    await openEditModal(page, cardA);
    const newNickA = `SeqA-${Date.now()}`;
    await fillEditField(page, 'nickname', newNickA);
    await fillEditField(page, 'mmr', '6500');
    await saveEditModal(page);

    // Edit user B: nickname only
    const cardB = userCards.nth(1);
    await openEditModal(page, cardB);
    const newNickB = `SeqB-${Date.now()}`;
    await fillEditField(page, 'nickname', newNickB);
    await saveEditModal(page);

    // Reload and verify both persist
    await page.reload();
    await page.locator('[data-testid="org-tab-users"]').click();
    await expect(page.getByText(newNickA).first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(newNickB).first()).toBeVisible({ timeout: 5000 });
  });

  test('@cicd PATCH body contains only dirty fields', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const userCards = page.locator('[data-testid^="usercard-"]');
    await expect(userCards.first()).toBeVisible({ timeout: 10000 });

    const card = userCards.first();
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
    const card = page.locator('[data-testid^="usercard-"]').first();
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
