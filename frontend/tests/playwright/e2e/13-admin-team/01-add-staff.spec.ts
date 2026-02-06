/**
 * Admin Team Section - Smoke Tests
 *
 * @cicd sanity tests verifying that the AdminTeamSection correctly renders
 * inside the Edit Organization / Edit League modals, showing existing
 * team members and management buttons.
 *
 * Test users (from populate):
 * - loginOrgAdmin: Admin of org 1 (DTX)
 * - loginLeagueAdmin: Admin of league 1
 *
 * Prerequisites:
 * - Test environment running (just test::up)
 * - Database populated (just db::populate::all)
 */

import { test, expect, visitAndWaitForHydration } from '../../fixtures';
import { loginAsDiscordId } from '../../fixtures/auth';

const API_URL = 'https://localhost/api';

/** Discord ID of the league admin test user (PK 1030, league 1 admin). */
const LEAGUE_ADMIN_DISCORD_ID = '100000000000000008';

/** Helper: get org PK from league 1 detail endpoint. */
async function getOrgAndLeaguePks(context: import('@playwright/test').BrowserContext) {
  const resp = await context.request.get(`${API_URL}/leagues/1/`);
  if (!resp.ok()) throw new Error(`Failed to fetch league 1: ${resp.status()}`);
  const data = await resp.json();
  const orgPk = typeof data.organization === 'object' ? data.organization.pk : data.organization;
  return { orgPk, leaguePk: data.pk as number };
}

test.describe('Admin Team Section (@cicd)', () => {
  let orgPk: number;
  let leaguePk: number;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const pks = await getOrgAndLeaguePks(context);
    orgPk = pks.orgPk;
    leaguePk = pks.leaguePk;
    await context.close();
  });

  test('@cicd AdminTeamSection renders in EditOrganizationModal', async ({ page, loginOrgAdmin }) => {
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

    // Scroll to and verify the Admin Team section renders with its header
    const adminTeamHeader = page.getByText('Admin Team');
    await adminTeamHeader.scrollIntoViewIfNeeded();
    await expect(adminTeamHeader).toBeVisible({ timeout: 5000 });

    // Verify team member rows are rendered (from populate data)
    const teamMembers = page.locator('[data-testid^="team-member-"]');
    await expect(teamMembers.first()).toBeVisible({ timeout: 5000 });
    const memberCount = await teamMembers.count();
    expect(memberCount).toBeGreaterThanOrEqual(1);

    // Verify management buttons are present for admin users
    const addAdminBtn = page.locator('[data-testid="add-admin-btn"]');
    await addAdminBtn.scrollIntoViewIfNeeded();
    await expect(addAdminBtn).toBeVisible({ timeout: 5000 });
    await expect(page.locator('[data-testid="add-staff-btn"]')).toBeVisible({ timeout: 5000 });
  });

  test('@cicd AdminTeamSection renders in EditLeagueModal', async ({ context, page }) => {
    // Login as league admin via Discord ID (the loginLeagueAdmin fixture endpoint is unreliable)
    await loginAsDiscordId(context, LEAGUE_ADMIN_DISCORD_ID);

    // Navigate to league page
    await visitAndWaitForHydration(page, `/leagues/${leaguePk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    // Click Edit League button
    const editBtn = page.locator('[data-testid="edit-league-button"]');
    await expect(editBtn).toBeVisible({ timeout: 5000 });
    await editBtn.click();

    // Wait for edit modal
    await expect(page.locator('[data-testid="edit-league-modal-heading"]')).toBeVisible({ timeout: 5000 });

    // Scroll to and verify the Admin Team section renders with its header
    const adminTeamHeader = page.getByText('Admin Team');
    await adminTeamHeader.scrollIntoViewIfNeeded();
    await expect(adminTeamHeader).toBeVisible({ timeout: 5000 });

    // Verify management buttons are present for admin users
    const addAdminBtn = page.locator('[data-testid="add-admin-btn"]');
    await addAdminBtn.scrollIntoViewIfNeeded();
    await expect(addAdminBtn).toBeVisible({ timeout: 5000 });
    await expect(page.locator('[data-testid="add-staff-btn"]')).toBeVisible({ timeout: 5000 });
  });
});
