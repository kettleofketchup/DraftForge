/**
 * Edit MMR Smoke Test
 *
 * @cicd smoke test verifying that editing a user's MMR on an org page
 * sends the PATCH to the org-scoped endpoint and updates the UI.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getFirstLeague,
} from '../../fixtures';

const API_URL = 'https://localhost/api';

let orgPk: number;

test.describe('Edit Org User MMR (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    const league = await getFirstLeague(context);
    if (!league) throw new Error('No leagues found. Run just db::populate::all');

    const leagueResp = await context.request.get(`${API_URL}/leagues/${league.pk}/`);
    const leagueData = await leagueResp.json();
    orgPk =
      typeof leagueData.organization === 'object'
        ? leagueData.organization.pk
        : leagueData.organization;

    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd smoke: edit user MMR via org user card', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    // Switch to Users tab
    const usersTab = page.locator('[data-testid="org-tab-users"]');
    await expect(usersTab).toBeVisible({ timeout: 5000 });
    await usersTab.click();

    // Wait for user cards to load
    const firstUserCard = page.locator('[data-testid^="usercard-"]').first();
    await expect(firstUserCard).toBeVisible({ timeout: 10000 });

    // Find the edit button on the first user card and click it
    const editBtn = firstUserCard.locator('[data-testid="edit-user-btn"]');
    await expect(editBtn).toBeVisible({ timeout: 5000 });
    await editBtn.click();

    // Wait for the edit modal to open — find the MMR input
    const mmrInput = page.locator('[data-testid="edit-user-mmr"]');
    await expect(mmrInput).toBeVisible({ timeout: 5000 });

    // Read original MMR value
    const originalMmr = await mmrInput.inputValue();

    // Set a new MMR value (use a distinctive value to verify the update)
    const newMmr = originalMmr === '9999' ? '8888' : '9999';

    // Intercept the PATCH request to verify it goes to the org endpoint
    const patchPromise = page.waitForRequest((req) =>
      req.method() === 'PATCH' && req.url().includes(`/organizations/${orgPk}/users/`)
    );

    // Clear and type new MMR
    await mmrInput.click();
    await mmrInput.fill(newMmr);

    // Click Save
    const saveBtn = page.getByRole('button', { name: 'Save Changes' });
    await saveBtn.click();

    // Verify the PATCH went to org-scoped endpoint (not /users/{pk}/)
    const patchReq = await patchPromise;
    expect(patchReq.url()).toContain(`/organizations/${orgPk}/users/`);

    // Verify the response is successful
    const response = await patchReq.response();
    expect(response).not.toBeNull();
    expect(response!.status()).toBe(200);

    // Verify the MMR value updated in the UI
    await expect(page.getByText(newMmr)).toBeVisible({ timeout: 5000 });

    // Restore original MMR by re-editing
    const userCardAfter = page.locator('[data-testid^="usercard-"]').first();
    const editBtnAfter = userCardAfter.locator('[data-testid="edit-user-btn"]');
    await expect(editBtnAfter).toBeVisible({ timeout: 5000 });
    await editBtnAfter.click();

    const mmrInputAfter = page.locator('[data-testid="edit-user-mmr"]');
    await expect(mmrInputAfter).toBeVisible({ timeout: 5000 });
    await mmrInputAfter.click();
    await mmrInputAfter.fill(originalMmr || '0');

    const saveBtnAfter = page.getByRole('button', { name: 'Save Changes' });
    await saveBtnAfter.click();

    // Wait for save to complete
    await page.waitForTimeout(1000);
  });
});
