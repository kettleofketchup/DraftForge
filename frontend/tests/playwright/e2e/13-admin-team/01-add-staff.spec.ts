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
    const editBtn = page.locator('button', { hasText: 'Edit' });
    await expect(editBtn).toBeVisible({ timeout: 5000 });
    await editBtn.click();

    // Wait for modal to open
    await expect(page.locator('[data-testid="edit-organization-modal"]')).toBeVisible({ timeout: 5000 });

    // Expand Admin Team section if collapsed
    const adminTeamHeader = page.locator('button', { hasText: 'Admin Team' });
    await expect(adminTeamHeader).toBeVisible({ timeout: 5000 });

    // Check if Staff section is visible (section is expanded)
    const staffHeading = page.locator('h4', { hasText: 'Staff' });
    if (!(await staffHeading.isVisible())) {
      await adminTeamHeader.click();
    }
    await expect(staffHeading).toBeVisible({ timeout: 3000 });

    // Click "Add Staff" button
    const addStaffBtn = page.locator('button', { hasText: 'Add Staff' });
    await expect(addStaffBtn).toBeVisible({ timeout: 3000 });
    await addStaffBtn.click();

    // AddUserModal should open
    const modal = page.locator('[data-testid="add-user-modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });

    // Search for the regular user (username: bucketoffish55)
    const searchInput = modal.locator('[data-testid="add-user-search"]');
    await expect(searchInput).toBeVisible();
    await searchInput.fill('bucket');

    // Wait for search results
    await expect(modal.getByRole('heading', { name: 'Site Users' })).toBeVisible({ timeout: 5000 });

    // Wait for a result with the username to appear and click Add
    const userResult = modal.locator('text=bucketoffish55').first();
    await expect(userResult).toBeVisible({ timeout: 10000 });

    // Find the Add button near this user result
    const addBtn = modal.locator('button', { hasText: 'Add' }).first();
    await expect(addBtn).toBeVisible({ timeout: 3000 });
    await addBtn.click();

    // Should show success toast
    await expect(page.locator('[data-sonner-toast][data-type="success"]')).toBeVisible({ timeout: 10000 });

    // Close the AddUserModal
    await page.keyboard.press('Escape');

    // Verify the user now appears in the Staff section
    const staffSection = page.locator('div', { has: staffHeading });
    await expect(staffSection.locator('text=bucketoffish55')).toBeVisible({ timeout: 5000 });

    // Cleanup: remove the user from org staff via API
    await removeOrgStaffMember(page.context(), orgPk, 1003);
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

    // Expand Admin Team section if collapsed
    const adminTeamHeader = page.locator('button', { hasText: 'Admin Team' });
    await expect(adminTeamHeader).toBeVisible({ timeout: 5000 });

    const staffHeading = page.locator('h4', { hasText: 'Staff' });
    if (!(await staffHeading.isVisible())) {
      await adminTeamHeader.click();
    }
    await expect(staffHeading).toBeVisible({ timeout: 3000 });

    // Click "Add Staff" button
    const addStaffBtn = page.locator('button', { hasText: 'Add Staff' });
    await expect(addStaffBtn).toBeVisible({ timeout: 3000 });
    await addStaffBtn.click();

    // AddUserModal should open
    const modal = page.locator('[data-testid="add-user-modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });

    // Search for the regular user
    const searchInput = modal.locator('[data-testid="add-user-search"]');
    await expect(searchInput).toBeVisible();
    await searchInput.fill('bucket');

    // Wait for search results
    await expect(modal.getByRole('heading', { name: 'Site Users' })).toBeVisible({ timeout: 5000 });

    const userResult = modal.locator('text=bucketoffish55').first();
    await expect(userResult).toBeVisible({ timeout: 10000 });

    // Click Add
    const addBtn = modal.locator('button', { hasText: 'Add' }).first();
    await expect(addBtn).toBeVisible({ timeout: 3000 });
    await addBtn.click();

    // Should show success toast
    await expect(page.locator('[data-sonner-toast][data-type="success"]')).toBeVisible({ timeout: 10000 });

    // Close the AddUserModal
    await page.keyboard.press('Escape');

    // Verify the user now appears in the Staff section
    const staffSection = page.locator('div', { has: staffHeading });
    await expect(staffSection.locator('text=bucketoffish55')).toBeVisible({ timeout: 5000 });

    // Cleanup: remove the user from league staff via API
    await removeLeagueStaffMember(page.context(), leaguePk, 1003);
  });
});
