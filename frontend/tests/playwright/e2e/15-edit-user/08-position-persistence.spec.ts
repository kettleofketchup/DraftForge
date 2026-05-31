/**
 * Position dropdown persistence regression test.
 *
 * Covers the uncontrolled-Select bug: position changes were silently
 * dropped because the legacy <Select> had no `value` prop. The new
 * controlled implementation must round-trip both visible state and
 * server payload.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  openEditModal,
  saveEditModal,
  setPositionField,
  readPositionField,
} from '../../fixtures';

const API_URL = 'https://localhost/api';
const USER_EDIT_ORG_NAME = 'User Edit Org';
let orgPk: number;

test.describe('Position dropdown persistence (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const orgs = await (await context.request.get(`${API_URL}/organizations/`)).json();
    const orgList = Array.isArray(orgs) ? orgs : orgs.results ?? [];
    orgPk = orgList.find((o: { name: string }) => o.name === USER_EDIT_ORG_NAME)?.pk;
    if (!orgPk) throw new Error('User Edit Org not found');
    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  // Dedicated user — see USER_EDIT_USERS in backend/tests/data/users.py.
  const TARGET_USERNAME = 'edit_user_positions';

  test('@cicd position changes persist in PATCH and re-render correctly', async ({ page }) => {
    // Use a wider viewport so the 5-column position grid (xl:grid-cols-5
    // ≥ 1280px) renders without the SelectTrigger buttons visually overlapping
    // — at the default 1280×720 viewport the modal's inner grid renders at
    // lg:grid-cols-3 and the trigger hit boxes spill into one another.
    await page.setViewportSize({ width: 1600, height: 900 });
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();
    const targetCard = page.locator(`[data-testid="usercard-${TARGET_USERNAME}"]`);
    await expect(targetCard).toBeVisible({ timeout: 10000 });

    // Step 1: reset carry+hard_support to 0 so the next set is guaranteed to
    // make `formState.isDirty` true (the modal short-circuits and skips PATCH
    // when no fields changed; previous runs may have left non-zero values).
    await openEditModal(page, targetCard);
    await setPositionField(page, 'carry', 0);
    await setPositionField(page, 'hard_support', 0);
    // Best-effort reset: if both were already 0, the modal closes without a
    // PATCH (still leaves us in the desired baseline state).
    const resetSaveBtn = page.getByRole('button', { name: 'Save Changes' });
    await resetSaveBtn.click();
    await expect(page.locator('[role="dialog"]')).toBeHidden({ timeout: 5000 }).catch(async () => {
      await page.keyboard.press('Escape');
    });

    // Step 2: now apply the real target values and assert the PATCH body.
    await openEditModal(page, targetCard);
    await setPositionField(page, 'carry', 1);
    await setPositionField(page, 'hard_support', 5);

    const patchPromise = page.waitForRequest(
      (req) => req.method() === 'PATCH' && /\/users\//.test(req.url()),
      { timeout: 15000 },
    );

    await saveEditModal(page);

    const patch = await patchPromise;
    const body = JSON.parse(patch.postData() || '{}');
    expect(body.positions).toBeDefined();
    expect(body.positions.carry).toBe(1);
    expect(body.positions.hard_support).toBe(5);

    // Re-open and confirm the trigger displays the new selection (not placeholder)
    await openEditModal(page, targetCard);
    const carryDisplay = await readPositionField(page, 'carry');
    expect(carryDisplay).toContain('Favorite');
    const supportDisplay = await readPositionField(page, 'hard_support');
    expect(supportDisplay).toContain('Least Favorite');
  });
});
