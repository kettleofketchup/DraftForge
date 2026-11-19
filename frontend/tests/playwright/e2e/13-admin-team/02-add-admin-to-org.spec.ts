/**
 * Admin Team Section - Add Admin to Organization
 *
 * Tests the AddUserModal integration in the org Settings tab (Admin Team).
 * This is the key regression test for the nested dialog bug fix:
 * - autoFocus timing conflict with Radix FocusScope was causing
 *   the AddUserModal to immediately close when opened.
 *
 * Test users (from populate):
 * - loginOrgAdmin: Admin of org 1 (DTX), pk=1020
 * - REGULAR_USER: pk=1003, username="bucketoffish55" (not an admin)
 *
 * Prerequisites:
 * - Test environment running (just test::up)
 * - Database populated (just db::populate::all)
 */

import { expect, test, visitAndWaitForHydration } from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';
import {
  closeAddUserModal,
  expectUserAlreadyAdded,
  searchAndAddUser,
  searchUser,
  waitForAddUserModal,
} from '../../helpers/add-user';

/** Username of regular test user (pk=1003) who is NOT an org admin. */
const ADDABLE_USERNAME = 'bucketoffish55';

/** Helper: get org PK from league 1 detail endpoint. */
async function getOrgPk(
  context: import('@playwright/test').BrowserContext,
): Promise<number> {
  const resp = await context.request.get(`${API_URL}/leagues/1/`);
  if (!resp.ok()) throw new Error(`Failed to fetch league 1: ${resp.status()}`);
  const data = await resp.json();
  return typeof data.organization === 'object'
    ? data.organization.pk
    : data.organization;
}

/** Helper: reset org admin team to known state via test endpoint. */
async function resetOrgAdminTeam(
  context: import('@playwright/test').BrowserContext,
  orgPk: number,
): Promise<void> {
  const resp = await context.request.post(
    `${API_URL}/tests/org/${orgPk}/reset-admin-team/`,
  );
  if (!resp.ok()) {
    console.warn(`[reset] Failed to reset org admin team: ${resp.status()}`);
  }
}

/** Helper: open the org Settings tab (via Edit) on the Admin Team section. */
async function openEditOrgModal(
  page: import('@playwright/test').Page,
): Promise<void> {
  const editBtn = page.locator('[data-testid="edit-organization-button"]');
  await expect(editBtn).toBeVisible({ timeout: 5000 });
  await editBtn.click();
  await expect(page.locator('[data-testid="org-settings-tab"]')).toBeVisible({
    timeout: 5000,
  });
  // Edit opens the org Settings tab; the admin team is its own section there.
  await page.getByTestId('org-settings-tab-admins').click();
}

/** Helper: scroll to Admin Team section and click Add Admin. */
async function clickAddAdmin(
  page: import('@playwright/test').Page,
): Promise<void> {
  const addAdminBtn = page.locator('[data-testid="add-admin-btn"]');
  await addAdminBtn.scrollIntoViewIfNeeded();
  await expect(addAdminBtn).toBeVisible({ timeout: 5000 });
  await addAdminBtn.click();
}

test.describe('Add Admin to Organization (@cicd)', () => {
  let orgPk: number;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    orgPk = await getOrgPk(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    // Reset admin team to known state before each test
    await resetOrgAdminTeam(context, orgPk);
  });

  test('@cicd AddUserModal stays open when adding admin (nested dialog regression)', async ({
    page,
    loginOrgAdmin,
  }) => {
    await loginOrgAdmin();

    // Navigate to org page
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    // Open org settings on the Admin Team section
    await openEditOrgModal(page);

    // Click Add Admin to open AddUserModal
    await clickAddAdmin(page);

    // KEY ASSERTION: AddUserModal should stay open (was closing immediately before fix)
    await waitForAddUserModal(page);

    // Verify search input is usable
    const searchInput = page.locator('[data-testid="add-user-search"]');
    await expect(searchInput).toBeVisible();
    await expect(searchInput).toBeFocused({ timeout: 3000 });

    // Close AddUserModal
    await closeAddUserModal(page);

    // Verify the settings page is still showing after closing AddUserModal
    await expect(page.locator('[data-testid="org-settings-tab"]')).toBeVisible({
      timeout: 3000,
    });
  });

  test('@cicd Can search and add a user as admin', async ({
    page,
    loginOrgAdmin,
  }) => {
    await loginOrgAdmin();

    // Navigate to org page
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    // Open org settings → Add Admin → AddUserModal
    await openEditOrgModal(page);
    await clickAddAdmin(page);
    await waitForAddUserModal(page);

    // Search for and add the regular user as admin
    await searchAndAddUser(page, ADDABLE_USERNAME);

    // Close AddUserModal
    await closeAddUserModal(page);

    // Verify the settings page is still showing
    await expect(page.locator('[data-testid="org-settings-tab"]')).toBeVisible({
      timeout: 3000,
    });

    // Verify the user now appears in the admin team list
    // Allow time for the org refetch cycle to complete and update the admin list
    const newAdminRow = page.locator(
      `[data-testid="team-member-${ADDABLE_USERNAME}"]`,
    );
    await expect(newAdminRow).toBeVisible({ timeout: 10000 });
    await newAdminRow.scrollIntoViewIfNeeded();
  });

  test('@cicd Already-added user shows correct state', async ({
    page,
    loginOrgAdmin,
  }) => {
    await loginOrgAdmin();

    // Navigate to org page
    await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    // Open org settings → Add Admin → AddUserModal
    await openEditOrgModal(page);
    await clickAddAdmin(page);
    await waitForAddUserModal(page);

    // Search for the org_admin_tester who is already an admin
    await searchUser(page, 'org_admin');
    await expectUserAlreadyAdded(page, 'org_admin_tester');

    // Close AddUserModal
    await closeAddUserModal(page);
  });
});
