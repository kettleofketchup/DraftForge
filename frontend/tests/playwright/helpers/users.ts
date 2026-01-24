import type { Page, Locator } from '@playwright/test';

/**
 * Get the user card element for a specific username.
 *
 * @param page - Playwright Page instance
 * @param username - The username to find
 * @returns Locator for the user card element
 */
export function getUserCard(page: Page, username: string): Locator {
  return page.locator(`[data-testid="usercard-${username}"]`);
}

/**
 * Get the remove button for a specific user.
 *
 * @param page - Playwright Page instance
 * @param username - The username whose remove button to find
 * @returns Locator for the remove button element
 */
export function getUserRemoveButton(page: Page, username: string): Locator {
  return page.locator(`[data-testid="removePlayerBtn-${username}"]`);
}

/**
 * Wait for a user card to be visible on the page.
 *
 * @param page - Playwright Page instance
 * @param username - The username to wait for
 * @param timeout - Maximum time to wait (default: 10000ms)
 */
export async function waitForUserCard(
  page: Page,
  username: string,
  timeout = 10000
): Promise<void> {
  await getUserCard(page, username).waitFor({
    state: 'visible',
    timeout,
  });
}

/**
 * Remove a user by clicking their remove button.
 *
 * @param page - Playwright Page instance
 * @param username - The username to remove
 */
export async function removeUser(page: Page, username: string): Promise<void> {
  await getUserRemoveButton(page, username).click();
}
