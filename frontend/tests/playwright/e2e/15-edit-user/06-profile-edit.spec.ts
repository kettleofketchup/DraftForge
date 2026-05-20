/**
 * Edit Profile — Base tab of the new layered EditProfileModal.
 *
 * Covers T1 (BaseUserProfile epic):
 *   - Nickname edit dual-writes to userCacheStore + userStore.currentUser
 *     so the navbar / profile header / user lists update without a reload.
 *
 * Avatar is NOT user-editable in this modal — it's synced from Discord
 * server-side (BaseUserProfile.avatar stores the Discord avatar hash,
 * not a URL). T2/T3 don't change that. If a future ticket adds
 * user-uploaded avatars, add a separate spec for it.
 *
 * Logs in as the admin user (PK 1001, kettleofketchup) and only edits that
 * user's OWN profile via /profile → EditProfileModal. Original values are
 * captured in a try/finally so the row is restored even if assertions fail
 * — never call this test flaky.
 */

import { test, expect } from '../../fixtures';

test.describe('Edit Profile — Base tab (new layered modal)', () => {
  test('user can change nickname and see it reflect in profile header without refresh', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();
    await page.goto('/profile');

    // /profile redirects to /user/<currentUserPk>. Wait for the header H1.
    const headerNickname = page.locator('[data-testid="user-card-nickname"]').first();
    await expect(headerNickname).toBeVisible({ timeout: 15_000 });

    const editTrigger = page.locator('[data-testid="edit-user-btn"]').first();
    await expect(editTrigger).toBeVisible({ timeout: 10_000 });
    await editTrigger.click();

    const nicknameInput = page.locator('[data-testid="edit-user-nickname"]');
    await expect(nicknameInput).toBeVisible({ timeout: 5_000 });
    const originalNickname = await nicknameInput.inputValue();

    const newNickname = `Renamed-${Date.now()}`;
    try {
      await nicknameInput.fill(newNickname);
      await page.locator('[data-testid="edit-user-save"]').click();

      // Toast confirms the PATCH landed.
      await expect(page.getByText(/profile updated/i)).toBeVisible({ timeout: 10_000 });
      await expect(page.getByRole('dialog')).toBeHidden({ timeout: 5_000 });

      // Dual-write verification — the profile header (sourced via the user
      // query, which is invalidated + refetched on save) reflects the new
      // nickname. Auto-retrying assertion handles the microtask race.
      await expect(headerNickname).toHaveText(newNickname, { timeout: 10_000 });
    } finally {
      // Restore — open the modal again and write the original value back.
      await editTrigger.click();
      await expect(nicknameInput).toBeVisible({ timeout: 5_000 });
      await nicknameInput.fill(originalNickname);
      await page.locator('[data-testid="edit-user-save"]').click();
      await expect(page.getByText(/profile updated/i)).toBeVisible({ timeout: 10_000 });
      await expect(page.getByRole('dialog')).toBeHidden({ timeout: 5_000 });
    }
  });
});
