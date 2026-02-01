/**
 * Tests for Claim Profile Feature
 *
 * Verifies that a user with a Steam ID can claim a profile
 * that was created without a Steam ID (e.g., manually added user).
 */

import { expect, test } from '../../fixtures';
import { API_URL } from '../../fixtures/constants';

interface ClaimableUser {
  pk: number;
  username: string;
  nickname: string;
  mmr: number;
  steamid: number | null;
}

// API helper to create a claimable user (no Discord, no Steam)
async function createClaimableUser(
  context: { request: { post: (url: string, options?: { data?: unknown }) => Promise<{ ok: () => boolean; json: () => Promise<unknown> }> } },
  options?: { username?: string; nickname?: string; mmr?: number }
): Promise<ClaimableUser | null> {
  const response = await context.request.post(
    `${API_URL}/tests/create-claimable-user/`,
    { data: options || {} }
  );
  if (!response.ok()) return null;
  const data = (await response.json()) as { success: boolean; user: ClaimableUser };
  return data.user;
}

// API helper to get user by pk
async function getUser(
  context: { request: { get: (url: string) => Promise<{ ok: () => boolean; json: () => Promise<unknown> }> } },
  userPk: number
): Promise<ClaimableUser | null> {
  const response = await context.request.get(`${API_URL}/users/${userPk}/`);
  if (!response.ok()) return null;
  return (await response.json()) as ClaimableUser;
}

// API helper to add user to tournament
async function addUserToTournament(
  context: { request: { patch: (url: string, options?: { data?: unknown }) => Promise<{ ok: () => boolean; json: () => Promise<unknown> }> } },
  tournamentPk: number,
  userPks: number[]
): Promise<boolean> {
  const response = await context.request.patch(
    `${API_URL}/tournament/${tournamentPk}/`,
    { data: { user_ids: userPks } }
  );
  return response.ok();
}

// API helper to get tournament
async function getTournament(
  context: { request: { get: (url: string) => Promise<{ ok: () => boolean; json: () => Promise<unknown> }> } },
  tournamentPk: number
): Promise<{ pk: number; users: Array<{ pk: number }> } | null> {
  const response = await context.request.get(`${API_URL}/tournament/${tournamentPk}/`);
  if (!response.ok()) return null;
  return (await response.json()) as { pk: number; users: Array<{ pk: number }> };
}

test.describe('Claim Profile Feature', () => {
  test('user with Steam ID can claim profile without Steam ID via tournament', async ({
    page,
    context,
    loginAdmin,
  }) => {
    // Login as admin (who has Steam ID via kettleofketchup fixture)
    const adminInfo = await loginAdmin();
    expect(adminInfo).toBeTruthy();
    expect(adminInfo!.user.pk).toBeTruthy();

    // Verify admin has Steam ID
    const adminUser = await getUser(context, adminInfo!.user.pk);
    if (!adminUser?.steamid) {
      console.log('Admin user does not have Steam ID - skipping test');
      test.skip();
      return;
    }

    // Create a claimable user (no Discord, no Steam)
    const claimableUser = await createClaimableUser(context, {
      nickname: 'Claimable Test User',
      mmr: 4500,
    });
    expect(claimableUser).not.toBeNull();
    expect(claimableUser!.steamid).toBeNull();

    console.log(`Created claimable user: ${claimableUser!.username} (pk=${claimableUser!.pk})`);

    // Get tournament 1 and add the claimable user
    const tournament = await getTournament(context, 1);
    expect(tournament).not.toBeNull();

    const existingUserPks = tournament!.users.map(u => u.pk);
    const success = await addUserToTournament(context, 1, [...existingUserPks, claimableUser!.pk]);
    expect(success).toBe(true);

    console.log(`Added claimable user to tournament 1`);

    // Navigate to tournament page
    await page.goto(`/tournament/1`);
    await page.waitForLoadState('networkidle');

    // Click Players tab
    const playersTab = page.locator('[data-testid="players-tab"]');
    if (await playersTab.isVisible({ timeout: 3000 }).catch(() => false)) {
      await playersTab.click();
      await page.waitForTimeout(500);
    }

    // Find the claimable user's card
    const userCard = page.locator(`[data-testid="usercard-${claimableUser!.username}"]`);
    await expect(userCard).toBeVisible({ timeout: 10000 });

    // Look for claim button on the card
    const claimBtnOnCard = page.locator(`[data-testid="claim-profile-btn-${claimableUser!.pk}"]`);
    const claimVisibleOnCard = await claimBtnOnCard.isVisible({ timeout: 3000 }).catch(() => false);

    if (claimVisibleOnCard) {
      // Click claim button on card (opens modal)
      await claimBtnOnCard.click();
      await page.waitForTimeout(500);
    }

    // Look for view profile button and click it to open modal
    const viewProfileBtn = userCard.locator('button[title="View Profile"]');
    if (await viewProfileBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await viewProfileBtn.click();
      await page.waitForTimeout(500);
    }

    // Now look for claim button in modal
    const claimBtnInModal = page.locator(`[data-testid="claim-profile-modal-btn-${claimableUser!.pk}"]`);
    await expect(claimBtnInModal).toBeVisible({ timeout: 5000 });

    // Click claim button
    await claimBtnInModal.click();

    // Wait for toast/success message
    const successToast = page.locator('text=Profile claimed');
    await expect(successToast).toBeVisible({ timeout: 10000 });

    // Verify the claimable user was deleted (merged into current user)
    const deletedUser = await getUser(context, claimableUser!.pk);
    expect(deletedUser).toBeNull(); // User should be deleted after claim

    console.log('Profile claimed successfully - user merged and deleted!');
  });

  test('claim button not shown when target user has Steam ID', async ({
    page,
    context,
    loginAdmin,
  }) => {
    // Login as admin
    await loginAdmin();

    // Get any user that has a Steam ID (but is not admin)
    const response = await context.request.get(`${API_URL}/users/`);
    const users = (await response.json()) as Array<{ pk: number; username: string; steamid: number | null }>;
    const userWithSteam = users.find(u => u.steamid !== null && u.username !== 'kettleofketchup');

    if (!userWithSteam) {
      console.log('No other users with Steam ID found, skipping test');
      test.skip();
      return;
    }

    // Get tournament and check if user is in it
    const tournament = await getTournament(context, 1);
    const userInTournament = tournament?.users.some(u => u.pk === userWithSteam.pk);

    if (!userInTournament) {
      // Add user to tournament
      const existingUserPks = tournament!.users.map(u => u.pk);
      await addUserToTournament(context, 1, [...existingUserPks, userWithSteam.pk]);
    }

    // Navigate to tournament page
    await page.goto(`/tournament/1`);
    await page.waitForLoadState('networkidle');

    // Click Players tab
    const playersTab = page.locator('[data-testid="players-tab"]');
    if (await playersTab.isVisible({ timeout: 3000 }).catch(() => false)) {
      await playersTab.click();
      await page.waitForTimeout(500);
    }

    // Find the user's card
    const userCard = page.locator(`[data-testid="usercard-${userWithSteam.username}"]`);

    if (await userCard.isVisible({ timeout: 5000 }).catch(() => false)) {
      // Claim button should NOT be visible on card
      const claimBtnOnCard = page.locator(`[data-testid="claim-profile-btn-${userWithSteam.pk}"]`);
      await expect(claimBtnOnCard).not.toBeVisible({ timeout: 2000 });

      // Open modal and verify claim button not there either
      const viewProfileBtn = userCard.locator('button[title="View Profile"]');
      if (await viewProfileBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
        await viewProfileBtn.click();
        await page.waitForTimeout(500);

        const claimBtnInModal = page.locator(`[data-testid="claim-profile-modal-btn-${userWithSteam.pk}"]`);
        await expect(claimBtnInModal).not.toBeVisible({ timeout: 2000 });
      }
    }
  });
});
