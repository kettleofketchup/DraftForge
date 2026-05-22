/**
 * Edit Profile — Base tab of the new layered EditProfileModal.
 *
 * Covers T1 (BaseUserProfile epic):
 *   - Nickname edit dual-writes to userCacheStore + userStore.currentUser
 *     so the navbar / profile header / user lists update without a reload.
 *   - The navbar UserAvatar's `alt` text comes from getDisplayName(currentUser),
 *     so a successful PATCH should update it too — this is what verifies
 *     userStore.patchCurrentUser is wired.
 *   - The ErrorBoundary + toast handle a failed PATCH gracefully without
 *     leaving the user stuck in a broken modal state.
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
  test('user can change nickname and see it reflect in profile header AND navbar avatar without refresh', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();
    await page.goto('/profile');

    // /profile redirects to /user/<currentUserPk>. Wait for the header H1.
    const headerNickname = page.locator('[data-testid="user-card-nickname"]').first();
    await expect(headerNickname).toBeVisible({ timeout: 15_000 });

    // Navbar avatar: alt text === currentUser.nickname || username (getDisplayName).
    // Locator targets the inner <img> since alt is an <img> attribute.
    const navAvatar = page.locator('[data-testid="user-avatar"] img').first();

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

      // Dual-write verification (1/2) — the profile header (sourced via the
      // user query, which is invalidated + refetched on save) reflects the
      // new nickname. Auto-retrying assertion handles the microtask race.
      await expect(headerNickname).toHaveText(newNickname, { timeout: 10_000 });

      // Dual-write verification (2/2) — userStore.patchCurrentUser updates
      // currentUser, which feeds the navbar UserAvatar's alt text. If
      // patchCurrentUser is broken, the alt stays as the old nickname.
      await expect(navAvatar).toHaveAttribute('alt', newNickname, { timeout: 10_000 });
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

  test('failing PATCH shows an error toast and leaves the modal usable for retry', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();
    await page.goto('/profile');

    await expect(
      page.locator('[data-testid="user-card-nickname"]').first(),
    ).toBeVisible({ timeout: 15_000 });

    const editTrigger = page.locator('[data-testid="edit-user-btn"]').first();
    await editTrigger.click();

    const nicknameInput = page.locator('[data-testid="edit-user-nickname"]');
    await expect(nicknameInput).toBeVisible({ timeout: 5_000 });

    // Intercept the PATCH and force a 500 — verifies the mutation onError
    // path: toast appears, the modal stays open (not crashed into the
    // ErrorBoundary fallback, which is reserved for render-phase errors
    // and useSuspenseQuery failures, not mutation failures).
    await page.route('**/api/users/me/profile/base/', (route) => {
      if (route.request().method() === 'PATCH') {
        return route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'simulated server error' }),
        });
      }
      return route.continue();
    });

    await nicknameInput.fill('WillFail');
    await page.locator('[data-testid="edit-user-save"]').click();

    // Error toast (sonner) — copy is "Failed to update profile" per BaseTab.tsx onError.
    await expect(page.getByText(/failed to update profile/i)).toBeVisible({
      timeout: 10_000,
    });

    // Modal is still open and the input is still editable — user can retry.
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(nicknameInput).toBeEditable();

    // Clean up the route override so the close-and-cancel path doesn't
    // accidentally try to PATCH again.
    await page.unroute('**/api/users/me/profile/base/');

    // Cancel — no restore needed since the failed PATCH didn't persist.
    await page.locator('[data-testid="edit-user-btn"]').first().scrollIntoViewIfNeeded();
    await page.getByRole('dialog').getByRole('button', { name: /cancel/i }).click();
    await expect(page.getByRole('dialog')).toBeHidden({ timeout: 5_000 });
  });
});
