/**
 * GuildNickname round-trip regression test.
 *
 * Pins that PATCH responses include `guildNickname` so the cache merge has
 * a value to seed from on reopen. Without this, a serializer change that
 * drops the field leaves the field empty after every save (silent regression
 * because the field IS persisted server-side; just not echoed back).
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  openEditModal,
  fillEditField,
  saveEditModal,
} from '../../fixtures';

const API_URL = 'https://localhost/api';

test.describe('GuildNickname round-trip (@cicd)', () => {
  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd guildNickname persists and round-trips through the modal', async ({ page }) => {
    await visitAndWaitForHydration(page, '/users');
    const card = page.locator('[data-testid^="usercard-"]').first();
    await expect(card).toBeVisible({ timeout: 10000 });

    await openEditModal(page, card);

    const newGuild = `Guild-${Date.now()}`;

    // Capture the PATCH response so we can assert the serializer echoes
    // guildNickname back. If the serializer drops it, this spec catches it.
    const responsePromise = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'PATCH' &&
        /\/users\//.test(resp.url()) &&
        resp.status() === 200,
      { timeout: 10000 },
    );

    await fillEditField(page, 'guildNickname', newGuild);
    await saveEditModal(page);

    const resp = await responsePromise;
    const body = await resp.json();
    expect(body.guildNickname).toBe(newGuild);

    // Reopen and confirm the field is seeded from the response value
    const cardAgain = page.locator('[data-testid^="usercard-"]').first();
    await openEditModal(page, cardAgain);
    const guildInput = page.locator('[data-testid="edit-user-guildNickname"]');
    await expect(guildInput).toBeVisible({ timeout: 5000 });
    await expect(guildInput).toHaveValue(newGuild);
  });
});
