import { Page, expect } from '@playwright/test';

/**
 * Shared helpers for interacting with AddUserModal across tests.
 *
 * The AddUserModal is used for:
 * - Adding members to organizations (Users tab → Add Member)
 * - Adding members to leagues (Users tab → Add Member)
 * - Adding players to tournaments (Players tab → Add Player)
 * - Adding admins/staff via AdminTeamSection (Edit modal → Add Admin/Staff)
 *
 * Key data-testids:
 * - `add-user-modal` — modal container
 * - `add-user-search` — search input
 * - `add-user-btn-{username}` — per-user add button
 * - `site-user-result-{username}` — per-user result row
 */

/** Wait for the AddUserModal to be visible and ready for interaction. */
export async function waitForAddUserModal(page: Page, timeout = 5000): Promise<void> {
  const modal = page.locator('[data-testid="add-user-modal"]');
  await expect(modal).toBeVisible({ timeout });
  // Wait for the search input to be ready
  await expect(page.locator('[data-testid="add-user-search"]')).toBeVisible({ timeout });
}

/** Close the AddUserModal by pressing Escape. */
export async function closeAddUserModal(page: Page): Promise<void> {
  await page.keyboard.press('Escape');
  await expect(page.locator('[data-testid="add-user-modal"]')).not.toBeVisible({ timeout: 3000 });
}

/**
 * Search for a user in the AddUserModal.
 * Assumes the modal is already open.
 *
 * @param page - Playwright page
 * @param query - Search query (min 3 chars)
 */
export async function searchUser(page: Page, query: string): Promise<void> {
  const searchInput = page.locator('[data-testid="add-user-search"]');
  await searchInput.fill(query);
  // Wait for search results to appear (heading "Site Users" appears on desktop)
  await expect(
    page.locator('text=/Site Users|Searching/i').first()
  ).toBeVisible({ timeout: 5000 });
}

/**
 * Search for and add a user in the AddUserModal.
 * Assumes the modal is already open.
 *
 * @param page - Playwright page
 * @param username - Username to search for and add
 */
export async function searchAndAddUser(page: Page, username: string): Promise<void> {
  // Type the username in the search field
  await searchUser(page, username);

  // Wait for and click the add button for the specific user
  const addBtn = page.locator(`[data-testid="add-user-btn-${username}"]`);
  await addBtn.waitFor({ state: 'visible', timeout: 10000 });
  await addBtn.click();

  // Wait for success toast
  await expect(
    page.locator('text=/added/i').first()
  ).toBeVisible({ timeout: 5000 });
}

/**
 * Verify a user result row shows "Already added" state.
 *
 * @param page - Playwright page
 * @param username - Username to check
 */
export async function expectUserAlreadyAdded(page: Page, username: string): Promise<void> {
  const userRow = page.locator(`[data-testid="site-user-result-${username}"]`);
  await expect(userRow).toBeVisible({ timeout: 5000 });
  await expect(userRow.locator('text=/already added/i')).toBeVisible({ timeout: 3000 });
}
