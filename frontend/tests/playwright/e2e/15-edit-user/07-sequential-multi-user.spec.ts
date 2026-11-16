/**
 * Sequential multi-user edit regression test.
 *
 * Pins the bug originally reported: editing user A then user B in succession
 * caused fields to "stick" or revert. Also pins the dirty-fields PATCH
 * behavior — only changed fields land in the request body.
 */

import {
  expect,
  fillEditField,
  nextSteamAccountId,
  openEditModal,
  readEditField,
  saveEditModal,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

const USER_EDIT_ORG_NAME = 'User Edit Org';
const ALT_STEAM_ACCOUNT_ID = 2_900_000_701;

let orgPk: number;

// Sequential: each test in this file edits one or both shared users
// (alpha + bravo) and the order matters (each test restores alpha's
// Friend ID before the next one reads it). `.serial` keeps these
// tests in declaration order; using dedicated usernames keeps them from
// racing with parallel specs in this directory.
const USER_A_USERNAME = 'edit_user_alpha';
const USER_B_USERNAME = 'edit_user_bravo';

test.describe.serial('Sequential multi-user edits (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
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
    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd edit user A and user B sequentially; both saves persist', async ({
    page,
  }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();

    const cardA = page.locator(`[data-testid="usercard-${USER_A_USERNAME}"]`);
    const cardB = page.locator(`[data-testid="usercard-${USER_B_USERNAME}"]`);
    await expect(cardA).toBeVisible({ timeout: 10000 });
    await expect(cardB).toBeVisible({ timeout: 10000 });

    // Edit user A: Friend ID + MMR
    await openEditModal(page, cardA);
    const originalIdA = await readEditField(page, 'steam_account_id');
    const newIdA = nextSteamAccountId(originalIdA, ALT_STEAM_ACCOUNT_ID);
    await fillEditField(page, 'steam_account_id', newIdA);
    await fillEditField(page, 'mmr', '6500');
    await saveEditModal(page);

    // Edit user B: MMR only
    await openEditModal(page, cardB);
    const newMmrB =
      (await readEditField(page, 'mmr')) === '5100' ? '5200' : '5100';
    await fillEditField(page, 'mmr', newMmrB);
    await saveEditModal(page);

    // Reload and verify both persist
    await page.reload();
    await page.locator('[data-testid="org-tab-users"]').click();
    await expect(cardA.getByText('6500').first()).toBeVisible({
      timeout: 5000,
    });
    await expect(cardB.getByText(newMmrB).first()).toBeVisible({
      timeout: 5000,
    });

    await openEditModal(page, cardA);
    await expect(
      page.locator('[data-testid="edit-user-steam_account_id"]'),
    ).toHaveValue(newIdA);
    await fillEditField(page, 'steam_account_id', originalIdA);
    await saveEditModal(page);
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

    const originalId = await readEditField(page, 'steam_account_id');
    const newId = nextSteamAccountId(originalId, ALT_STEAM_ACCOUNT_ID);
    await fillEditField(page, 'steam_account_id', newId);
    await saveEditModal(page);

    const patch = await patchPromise;
    const body = JSON.parse(patch.postData() || '{}');
    expect(Object.keys(body).sort()).toEqual(['steam_account_id']);
    expect(body.steam_account_id).toBe(Number(newId));

    await openEditModal(page, card);
    await fillEditField(page, 'steam_account_id', originalId);
    await saveEditModal(page);
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
