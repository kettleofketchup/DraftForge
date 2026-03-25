/**
 * Tests for Claim Profile Feature
 *
 * Verifies that a user can claim/merge a profile that was manually created
 * (e.g., by an org admin adding a user with just their Steam ID).
 *
 * Test users:
 * - claimable_profile (pk=1010): HAS Friend ID, NO Discord ID, NO username
 * - user_claimer (pk=1011): HAS Discord ID, NO Friend ID (can claim profiles)
 *
 * Claim button logic:
 * - Shows when: target HAS steam_account_id AND NO discordId, current user HAS discordId
 */

import { expect, test } from '../../fixtures';
import { API_URL } from '../../fixtures/constants';

interface ClaimableUser {
  pk: number;
  username: string | null;
  steam_account_id: number | null;
  discordId: string | null;
  nickname: string | null;
}

/** Fetch claimable user from the API by known attributes */
async function getClaimableUser(
  context: { request: { get: (url: string) => Promise<{ ok: () => boolean; json: () => Promise<unknown> }> } }
): Promise<ClaimableUser | null> {
  const response = await context.request.get(`${API_URL}/users/`);
  if (!response.ok()) return null;
  const users = (await response.json()) as ClaimableUser[];
  return users.find(u => u.nickname === 'Claimable Profile' || u.steam_account_id === 76561198099999999) ?? null;
}

/** Navigate to /users and wait for user cards to fully render */
async function goToUsersPage(page: import('@playwright/test').Page) {
  await page.goto('/users');
  await page.waitForLoadState('domcontentloaded');
  // Wait for at least one usercard to render (API data loaded + progressive render)
  await page.waitForSelector('[data-testid^="usercard-"]', { timeout: 15000 });
}

/** Search for a user by name and wait for results to settle */
async function searchForUser(page: import('@playwright/test').Page, query: string) {
  const searchInput = page.getByTestId('userSearchInput');
  await searchInput.fill(query);
  // Wait for debounce (300ms) + filter + re-render to settle
  await page.waitForTimeout(800);
}

test.describe('Claim Profile Feature', () => {
  test('user_claimer sees claim button for claimable_profile', async ({
    page,
    context,
    loginUserClaimer,
  }) => {
    await loginUserClaimer();

    // Verify claimable user exists via API
    const claimable = await getClaimableUser(context);
    expect(claimable, 'Claimable profile should exist').not.toBeNull();
    expect(claimable!.steam_account_id).not.toBeNull();
    expect(claimable!.discordId).toBeNull();

    await goToUsersPage(page);
    await searchForUser(page, 'Claimable Profile');

    // Claim button should be visible — currentUser has discordId, target has no discordId
    const claimBtn = page.getByTestId(`claim-profile-btn-${claimable!.pk}`);
    await expect(claimBtn).toBeVisible({ timeout: 10000 });
  });

  test('admin does NOT see claim button for user with Discord ID', async ({
    page,
    context,
    loginAdmin,
  }) => {
    await loginAdmin();

    // Find any user WITH Discord ID (who isn't the admin)
    const currentUserResp = await context.request.get(`${API_URL}/current_user`);
    const currentUser = (await currentUserResp.json()) as { pk: number };

    const usersResp = await context.request.get(`${API_URL}/users/`);
    const users = (await usersResp.json()) as ClaimableUser[];
    const userWithDiscord = users.find(u => u.discordId !== null && u.pk !== currentUser.pk);

    if (!userWithDiscord) {
      test.skip(true, 'No other user with Discord ID found');
      return;
    }

    await goToUsersPage(page);
    if (userWithDiscord.username) {
      await searchForUser(page, userWithDiscord.username);
    }

    // Claim button should NOT be visible — target already has Discord ID
    const claimBtn = page.getByTestId(`claim-profile-btn-${userWithDiscord.pk}`);
    await expect(claimBtn).not.toBeVisible({ timeout: 2000 });
  });

  test('logged in user CAN see claim buttons for profiles without Discord ID', async ({
    page,
    context,
    loginUser,
    loginUserClaimer,
  }) => {
    // Ensure claimable profile exists (loginUserClaimer creates it)
    await loginUserClaimer();
    const claimable = await getClaimableUser(context);

    // Now login as regular user
    await loginUser();

    await goToUsersPage(page);
    await searchForUser(page, 'Claimable');

    // Regular user with Discord ID should see claim button(s)
    const anyClaimBtn = page.locator('[data-testid^="claim-profile-btn-"]');
    const claimBtnCount = await anyClaimBtn.count();

    if (claimable) {
      expect(claimBtnCount).toBeGreaterThan(0);
    }
  });

  test('clicking claim button opens PlayerModal with claim action', async ({
    page,
    context,
    loginUserClaimer,
  }) => {
    test.setTimeout(60_000); // login + page load + modal interaction
    await loginUserClaimer();

    const claimable = await getClaimableUser(context);
    if (!claimable) {
      test.skip(true, 'Claimable profile not found');
      return;
    }

    await goToUsersPage(page);
    await searchForUser(page, 'Claimable Profile');

    // Wait for claim button and click to open PlayerModal
    const claimBtn = page.getByTestId(`claim-profile-btn-${claimable.pk}`);
    await expect(claimBtn).toBeVisible({ timeout: 10000 });

    // Click and wait for modal — retry if click doesn't register
    const modal = page.locator('[role="dialog"]');
    for (let attempt = 0; attempt < 3; attempt++) {
      await page.keyboard.press('Escape');
      await claimBtn.click({ force: true });
      if (await modal.isVisible({ timeout: 3000 }).catch(() => false)) break;
    }
    await expect(modal).toBeVisible({ timeout: 5000 });

    const claimBtnInModal = page.getByTestId(`claim-profile-modal-btn-${claimable.pk}`);
    await expect(claimBtnInModal).toBeVisible({ timeout: 5000 });
  });
});
