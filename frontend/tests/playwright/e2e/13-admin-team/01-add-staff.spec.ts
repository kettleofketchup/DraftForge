/**
 * Admin Team - Add Staff Smoke Tests
 *
 * @cicd sanity tests verifying that org admins and league admins can add
 * staff members through the AdminTeamSection's AddUserModal in the
 * Edit Organization / Edit League modals.
 *
 * Test users (from populate):
 * - loginOrgAdmin: Admin of org 1 (DTX)
 * - loginLeagueAdmin: Admin of league 1
 * - REGULAR_USER (pk=1003, username="bucketoffish55"): Searchable target
 *
 * Prerequisites:
 * - Test environment running (just test::up)
 * - Database populated (just db::populate::all)
 */

import { test, expect, visitAndWaitForHydration } from '../../fixtures';

const API_URL = 'https://localhost/api';
const TARGET_USERNAME = 'bucketoffish55';
const TARGET_USER_PK = 1003;

/** Helper: get org PK from league 1 detail endpoint. */
async function getOrgAndLeaguePks(context: import('@playwright/test').BrowserContext) {
  const resp = await context.request.get(`${API_URL}/leagues/1/`);
  if (!resp.ok()) throw new Error(`Failed to fetch league 1: ${resp.status()}`);
  const data = await resp.json();
  const orgPk = typeof data.organization === 'object' ? data.organization.pk : data.organization;
  return { orgPk, leaguePk: data.pk as number };
}

/** Helper: remove a user from org staff via API (cleanup). */
async function removeOrgStaffMember(context: import('@playwright/test').BrowserContext, orgPk: number, userPk: number) {
  await context.request.delete(`${API_URL}/organizations/${orgPk}/staff/${userPk}/`);
}

/** Helper: remove a user from league staff via API (cleanup). */
async function removeLeagueStaffMember(context: import('@playwright/test').BrowserContext, leaguePk: number, userPk: number) {
  await context.request.delete(`${API_URL}/leagues/${leaguePk}/staff/${userPk}/`);
}

test.describe('Admin Team - Add Staff (@cicd)', () => {
  let orgPk: number;
  let leaguePk: number;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const pks = await getOrgAndLeaguePks(context);
    orgPk = pks.orgPk;
    leaguePk = pks.leaguePk;
    await context.close();
  });

  test('@cicd org admin can add staff via AdminTeamSection modal', async ({ page, loginOrgAdmin }) => {
    await loginOrgAdmin();

    // Navigate to org page
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    // Click Edit button to open EditOrganizationModal
    const editBtn = page.locator('[data-testid="edit-organization-button"]');
    await expect(editBtn).toBeVisible({ timeout: 5000 });
    await editBtn.click();

    // Wait for modal to open
    await expect(page.locator('[data-testid="edit-organization-modal"]')).toBeVisible({ timeout: 5000 });

    // Click "Add Staff" button
    const addStaffBtn = page.locator('[data-testid="add-staff-btn"]');
    await expect(addStaffBtn).toBeVisible({ timeout: 5000 });
    await addStaffBtn.click();

    // AddUserModal should open (nested inside EditOrganizationModal)
    await expect(page.locator('[data-testid="add-user-modal"]')).toBeVisible({ timeout: 5000 });

    // Click the search input to give it focus (Playwright's click works with nested dialogs)
    const searchInput = page.locator('[data-testid="add-user-search"]');
    await expect(searchInput).toBeVisible({ timeout: 5000 });
    await searchInput.click();

    // Type using page.keyboard - sends CDP-level key events to the focused element.
    // We use this instead of fill()/pressSequentially() which fail in nested Radix
    // Dialog contexts due to focus trap interference.
    await page.keyboard.type('bucket', { delay: 80 });

    // Diagnostic: log input value
    const inputVal = await searchInput.inputValue();
    console.log(`[test] Input value after keyboard.type: "${inputVal}"`);

    // Wait for search result to appear via data-testid
    const addBtn = page.locator(`[data-testid="add-user-btn-${TARGET_USERNAME}"]`);
    await expect(addBtn).toBeVisible({ timeout: 15000 });

    // Click the Add button for this user
    await addBtn.click();

    // Should show success toast
    await expect(page.locator('[data-sonner-toast][data-type="success"]')).toBeVisible({ timeout: 10000 });

    // Close the AddUserModal
    await page.keyboard.press('Escape');

    // Verify the user now appears in the Admin Team section
    await expect(page.locator(`[data-testid="team-member-${TARGET_USERNAME}"]`)).toBeVisible({ timeout: 5000 });

    // Cleanup: remove the user from org staff via API
    await removeOrgStaffMember(page.context(), orgPk, TARGET_USER_PK);
  });

  test('@cicd league admin can add staff via AdminTeamSection modal', async ({ page, loginLeagueAdmin }) => {
    await loginLeagueAdmin();

    // Navigate to league page
    await visitAndWaitForHydration(page, `/leagues/${leaguePk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    // Click Edit League button
    const editBtn = page.locator('[data-testid="edit-league-button"]');
    await expect(editBtn).toBeVisible({ timeout: 5000 });
    await editBtn.click();

    // Wait for edit modal
    await expect(page.locator('[data-testid="edit-league-modal-heading"]')).toBeVisible({ timeout: 5000 });

    // Click "Add Staff" button
    const addStaffBtn = page.locator('[data-testid="add-staff-btn"]');
    await expect(addStaffBtn).toBeVisible({ timeout: 5000 });
    await addStaffBtn.click();

    // AddUserModal should open
    await expect(page.locator('[data-testid="add-user-modal"]')).toBeVisible({ timeout: 5000 });

    // Click the search input to give it focus
    const searchInput = page.locator('[data-testid="add-user-search"]');
    await expect(searchInput).toBeVisible({ timeout: 5000 });
    await searchInput.click();

    // Type using page.keyboard
    await page.keyboard.type('bucket', { delay: 80 });

    // Wait for search result to appear via data-testid
    const addBtn = page.locator(`[data-testid="add-user-btn-${TARGET_USERNAME}"]`);
    await expect(addBtn).toBeVisible({ timeout: 15000 });

    // Click Add
    await addBtn.click();

    // Should show success toast
    await expect(page.locator('[data-sonner-toast][data-type="success"]')).toBeVisible({ timeout: 10000 });

    // Close the AddUserModal
    await page.keyboard.press('Escape');

    // Verify the user now appears in the Admin Team section
    await expect(page.locator(`[data-testid="team-member-${TARGET_USERNAME}"]`)).toBeVisible({ timeout: 5000 });

    // Cleanup: remove the user from league staff via API
    await removeLeagueStaffMember(page.context(), leaguePk, TARGET_USER_PK);
  });
});
