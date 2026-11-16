/**
 * Edit Profile — Base tab of the layered EditProfileModal.
 *
 * Names come from Discord, so the Base tab has nothing to edit: it shows the
 * synced Discord name read-only with no input and no save button. The profile
 * header and the navbar avatar's alt text show the same resolved name (no org
 * context on /profile: Discord name, then username).
 *
 * Logs in as edit_user_charlie (pk 2052, Discord name "Edit Charlie"), which
 * no other spec uses. Nothing is written, so there is nothing to restore.
 */

import { expect, test } from '../../fixtures';

const CHARLIE_PK = 2052;
const CHARLIE_USERNAME = 'edit_user_charlie';
const CHARLIE_DISCORD_NAME = 'Edit Charlie';

test.describe('Edit Profile — Base tab (@cicd)', () => {
  test('@cicd smoke: Base tab shows the synced Discord name read-only', async ({
    page,
    loginAsUser,
  }) => {
    await loginAsUser(CHARLIE_PK);
    await page.goto('/profile');

    // /profile redirects to /user/<currentUserPk>.
    const header = page
      .locator('[data-testid="user-card-display-name"]')
      .first();
    await expect(header).toHaveText(CHARLIE_DISCORD_NAME, { timeout: 15_000 });
    await expect(page.getByText(`@${CHARLIE_USERNAME}`).first()).toBeVisible();

    const navAvatar = page.locator('[data-testid="user-avatar"] img').first();
    await expect(navAvatar).toHaveAttribute('alt', CHARLIE_DISCORD_NAME, {
      timeout: 10_000,
    });

    await page.locator('[data-testid="edit-user-btn"]').first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    await expect(dialog.getByTestId('profile-discord-name')).toHaveText(
      CHARLIE_DISCORD_NAME,
      {
        timeout: 10_000,
      },
    );
    await expect(dialog.getByText(/Synced from Discord/)).toBeVisible();
    await expect(dialog.locator('[role="tabpanel"] input')).toHaveCount(0);
    await expect(
      page.locator('[data-testid="edit-user-nickname"]'),
    ).toHaveCount(0);
    await expect(page.locator('[data-testid="edit-user-save"]')).toHaveCount(0);

    await dialog
      .locator('[role="tabpanel"]')
      .getByRole('button', { name: 'Close' })
      .click();
    await expect(dialog).toBeHidden({ timeout: 5_000 });
  });
});
