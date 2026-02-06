/**
 * Admin Team - Staff Display Tests
 *
 * @cicd sanity tests verifying that the AdminTeamSection correctly displays
 * staff members in the Edit Organization / Edit League modals.
 *
 * Strategy: Add staff via API, then verify AdminTeamSection renders them.
 * This avoids Playwright + nested Radix Dialog focus trap issues with the
 * AddUserModal search input.
 *
 * Test users (from populate):
 * - loginOrgAdmin: Admin of org 1 (DTX)
 * - loginLeagueAdmin: Admin of league 1
 * - REGULAR_USER (pk=1003, username="bucketoffish55"): Target user
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

/** Helper: get CSRF token from context cookies. */
async function getCsrfToken(context: import('@playwright/test').BrowserContext): Promise<string> {
  const cookies = await context.cookies();
  return cookies.find(c => c.name === 'csrftoken')?.value || '';
}

/** Helper: add a user to org staff via API. */
async function addOrgStaffMember(context: import('@playwright/test').BrowserContext, orgPk: number, userPk: number) {
  const csrfToken = await getCsrfToken(context);
  const resp = await context.request.post(`${API_URL}/organizations/${orgPk}/staff/`, {
    data: { user_id: userPk },
    headers: { 'X-CSRFToken': csrfToken },
  });
  if (!resp.ok()) throw new Error(`Failed to add org staff: ${resp.status()}`);
}

/** Helper: remove a user from org staff via API (cleanup). */
async function removeOrgStaffMember(context: import('@playwright/test').BrowserContext, orgPk: number, userPk: number) {
  const csrfToken = await getCsrfToken(context);
  await context.request.delete(`${API_URL}/organizations/${orgPk}/staff/${userPk}/`, {
    headers: { 'X-CSRFToken': csrfToken },
  });
}

/** Helper: add a user to league staff via API. */
async function addLeagueStaffMember(context: import('@playwright/test').BrowserContext, leaguePk: number, userPk: number) {
  const csrfToken = await getCsrfToken(context);
  const resp = await context.request.post(`${API_URL}/leagues/${leaguePk}/staff/`, {
    data: { user_id: userPk },
    headers: { 'X-CSRFToken': csrfToken },
  });
  if (!resp.ok()) throw new Error(`Failed to add league staff: ${resp.status()}`);
}

/** Helper: remove a user from league staff via API (cleanup). */
async function removeLeagueStaffMember(context: import('@playwright/test').BrowserContext, leaguePk: number, userPk: number) {
  const csrfToken = await getCsrfToken(context);
  await context.request.delete(`${API_URL}/leagues/${leaguePk}/staff/${userPk}/`, {
    headers: { 'X-CSRFToken': csrfToken },
  });
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

  test('@cicd org admin can see staff in AdminTeamSection', async ({ page, loginOrgAdmin }) => {
    await loginOrgAdmin();

    // Add staff via API first
    await addOrgStaffMember(page.context(), orgPk, TARGET_USER_PK);

    // Verify via API that the staff was actually added
    const orgResp = await page.context().request.get(`${API_URL}/organizations/${orgPk}/`);
    const orgData = await orgResp.json();
    console.log(`[diag] org staff count: ${orgData.staff?.length ?? 'undefined'}`);
    console.log(`[diag] org staff PKs: ${JSON.stringify(orgData.staff?.map((s: { pk: number }) => s.pk))}`);
    console.log(`[diag] org admins count: ${orgData.admins?.length ?? 'undefined'}`);

    try {
      // Navigate to org page
      await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
      await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

      // Click Edit button to open EditOrganizationModal
      const editBtn = page.locator('[data-testid="edit-organization-button"]');
      await expect(editBtn).toBeVisible({ timeout: 5000 });
      await editBtn.click();

      // Wait for modal to open
      await expect(page.locator('[data-testid="edit-organization-modal"]')).toBeVisible({ timeout: 5000 });

      // Diagnostic: check what's in the modal DOM
      const adminTeamHeader = page.locator('text=Admin Team');
      const hasAdminTeam = await adminTeamHeader.count();
      console.log(`[diag] "Admin Team" header found: ${hasAdminTeam}`);

      const staffHeader = page.locator('text=Staff');
      const hasStaffHeader = await staffHeader.count();
      console.log(`[diag] "Staff" header found: ${hasStaffHeader}`);

      const teamMembers = page.locator('[data-testid^="team-member-"]');
      const memberCount = await teamMembers.count();
      console.log(`[diag] team-member elements: ${memberCount}`);
      for (let i = 0; i < memberCount; i++) {
        const testId = await teamMembers.nth(i).getAttribute('data-testid');
        console.log(`[diag]   member ${i}: ${testId}`);
      }

      // Verify the user appears in the Admin Team section's staff list
      await expect(page.locator(`[data-testid="team-member-${TARGET_USERNAME}"]`)).toBeVisible({ timeout: 10000 });
    } finally {
      // Cleanup: remove the user from org staff via API
      await removeOrgStaffMember(page.context(), orgPk, TARGET_USER_PK);
    }
  });

  test('@cicd league admin can see staff in AdminTeamSection', async ({ page, loginLeagueAdmin }) => {
    await loginLeagueAdmin();

    // Add staff via API first
    await addLeagueStaffMember(page.context(), leaguePk, TARGET_USER_PK);

    try {
      // Navigate to league page
      await visitAndWaitForHydration(page, `/leagues/${leaguePk}`);
      await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

      // Click Edit League button
      const editBtn = page.locator('[data-testid="edit-league-button"]');
      await expect(editBtn).toBeVisible({ timeout: 5000 });
      await editBtn.click();

      // Wait for edit modal
      await expect(page.locator('[data-testid="edit-league-modal-heading"]')).toBeVisible({ timeout: 5000 });

      // Verify the user appears in the Admin Team section's staff list
      await expect(page.locator(`[data-testid="team-member-${TARGET_USERNAME}"]`)).toBeVisible({ timeout: 5000 });
    } finally {
      // Cleanup: remove the user from league staff via API
      await removeLeagueStaffMember(page.context(), leaguePk, TARGET_USER_PK);
    }
  });
});
