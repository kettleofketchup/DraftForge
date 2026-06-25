/**
 * Dota tab — position persist + reflect (T2 GameUserProfile epic #224).
 *
 * Covers the NEW layered EditProfileModal Dota tab, which edits the
 * logged-in user's OWN DotaUserProfile.positions via
 * PATCH /api/users/me/profile/game/dota/. This is distinct from
 * 08-position-persistence.spec.ts, which guards the legacy userCard
 * `/users/<id>/` shim path (Task 9 regression) — do NOT merge the two.
 *
 * Login: the per-user fixture loginAsUser(pk) as edit_user_positions
 * (PK 2057, backend/tests/data/users.py). loginAdmin is wrong here —
 * the /profile Dota tab edits whoever is logged in, and we want a
 * dedicated user so concurrent suites don't fight over the row.
 *
 * The Dota tab reuses PositionFormFields, whose Selects carry
 * `position-choice-<role>` testids (NOT the legacy `edit-user-<role>`
 * ones the setPositionField/readPositionField helpers target), so this
 * spec drives those Selects directly via small local helpers.
 *
 * Reflect-assertion caveat: /profile has no active game, so
 * currentGameType === null and any usePlayerPositions display there
 * returns undefined — there is NO profile-page position badge to assert
 * against. The persisted change is verified by RE-OPENING the modal and
 * reading the field back (mirrors 08). Originals are captured up front
 * and restored in a finally so the row survives even if assertions fail.
 */

import { test, expect } from '../../fixtures';
import type { Page } from '@playwright/test';

// edit_user_positions — see EDIT_USER_USERS in backend/tests/data/users.py.
const EDIT_USER_POSITIONS_PK = 2057;

type PositionRole =
  | 'carry'
  | 'mid'
  | 'offlane'
  | 'soft_support'
  | 'hard_support';

/**
 * Open the EditProfileModal from /profile and switch to the Dota tab.
 * Returns once the Dota save button is visible (tab content mounted).
 */
async function openDotaTab(page: Page): Promise<void> {
  // Idempotent: if a dialog is already open (e.g. a prior step left it open, or
  // the finally restore runs after an assertion threw mid-flow), dismiss it
  // first so the edit-user-btn isn't blocked by the Radix overlay.
  const openDialog = page.getByRole('dialog');
  if (await openDialog.isVisible().catch(() => false)) {
    await page.keyboard.press('Escape');
    await expect(openDialog).toBeHidden({ timeout: 5_000 }).catch(() => {});
  }

  const editTrigger = page.locator('[data-testid="edit-user-btn"]').first();
  await expect(editTrigger).toBeVisible({ timeout: 10_000 });
  await editTrigger.click();

  const dotaTab = page.locator('[data-testid="edit-user-tab-dota"]');
  await expect(dotaTab).toBeVisible({ timeout: 5_000 });
  await dotaTab.click();

  await expect(page.locator('[data-testid="edit-user-dota-save"]')).toBeVisible({
    timeout: 5_000,
  });
}

/**
 * Read the rendered text of a PositionFormFields `position-choice-<role>`
 * SelectTrigger (the visible 0–5 preference label, or the placeholder).
 */
async function readDotaPosition(page: Page, role: PositionRole): Promise<string> {
  const trigger = page.locator(`[data-testid="position-choice-${role}"]`);
  await expect(trigger).toBeVisible({ timeout: 5_000 });
  return (await trigger.innerText()).trim();
}

/**
 * Set a `position-choice-<role>` Select to a numeric 0–5 value. Keyboard-
 * driven (focus + Enter to open, click the matching option) to sidestep the
 * tight position grid where neighboring trigger hit boxes overlap. Waits for
 * the Radix listbox to close before returning.
 */
async function setDotaPosition(
  page: Page,
  role: PositionRole,
  value: number,
): Promise<void> {
  const trigger = page.locator(`[data-testid="position-choice-${role}"]`);
  await trigger.scrollIntoViewIfNeeded();
  await trigger.focus();
  await page.keyboard.press('Enter');
  await expect(trigger).toHaveAttribute('data-state', 'open', { timeout: 5_000 });
  // Options render as "1: Favorite", "5: Least Favorite", etc. (PositionChoiceEnum).
  await page
    .getByRole('option')
    .filter({ hasText: new RegExp(`^${value}: `) })
    .click();
  await expect(trigger).toHaveAttribute('data-state', 'closed', { timeout: 5_000 });
}

test.describe('Edit Profile — Dota tab positions (new layered modal)', () => {
  test('user can change a Dota position and have it persist + reflect on re-open', async ({
    page,
    loginAsUser,
  }) => {
    await loginAsUser(EDIT_USER_POSITIONS_PK);
    // Wider viewport so the 5-column position grid renders without the trigger
    // hit boxes overlapping (mirrors 08-position-persistence.spec.ts).
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto('/profile');

    // /profile redirects to /user/<currentUserPk>; wait for the header.
    await expect(
      page.locator('[data-testid="user-card-nickname"]').first(),
    ).toBeVisible({ timeout: 15_000 });

    // Capture the ORIGINAL carry value first so we can restore it later.
    await openDotaTab(page);
    const originalCarry = await readDotaPosition(page, 'carry');

    // Pick a target that's guaranteed different from the original so the form
    // is dirty and the PATCH actually fires. The trigger text starts with
    // "<n>: " — if carry is already 1 ("1: Favorite"), target 5 instead.
    const targetCarry = originalCarry.startsWith('1:') ? 5 : 1;

    try {
      await setDotaPosition(page, 'carry', targetCarry);

      const patchPromise = page.waitForRequest(
        (req) =>
          req.method() === 'PATCH' &&
          /\/users\/me\/profile\/game\/dota\//.test(req.url()),
        { timeout: 15_000 },
      );

      await page.locator('[data-testid="edit-user-dota-save"]').click();

      // Assert the PATCH body carries the new carry preference.
      const patch = await patchPromise;
      const body = JSON.parse(patch.postData() || '{}');
      expect(body.positions).toBeDefined();
      expect(body.positions.carry).toBe(targetCarry);

      // Success toast (sonner) — copy from DotaTab.tsx onSuccess.
      await expect(page.getByText(/dota profile updated/i)).toBeVisible({
        timeout: 10_000,
      });

      // The modal closes on success (DotaTab calls onClose()).
      await expect(page.getByRole('dialog')).toBeHidden({ timeout: 5_000 });

      // Reflect-assertion: /profile has no active-game position badge, so
      // re-open the modal + Dota tab and read carry back from the field.
      await openDotaTab(page);
      const reopenedCarry = await readDotaPosition(page, 'carry');
      expect(reopenedCarry).toMatch(new RegExp(`^${targetCarry}: `));

      // Close without changing anything (cancel — re-opened modal is dirty-free).
      await page
        .getByRole('dialog')
        .getByRole('button', { name: /cancel/i })
        .click();
      await expect(page.getByRole('dialog')).toBeHidden({ timeout: 5_000 });
    } finally {
      // Restore the original carry value. Map the captured trigger text
      // ("<n>: …") back to its numeric value; default to 0 if unparseable.
      const restoreValue = Number.parseInt(originalCarry, 10);
      await openDotaTab(page);
      await setDotaPosition(
        page,
        'carry',
        Number.isNaN(restoreValue) ? 0 : restoreValue,
      );
      await page.locator('[data-testid="edit-user-dota-save"]').click();
      // Best-effort: if nothing changed (restore == current) the modal may
      // skip the PATCH; tolerate either close path.
      await expect(page.getByRole('dialog'))
        .toBeHidden({ timeout: 10_000 })
        .catch(async () => {
          await page.keyboard.press('Escape');
        });
    }
  });

  test('failing PATCH shows an error toast and leaves the modal open for retry', async ({
    page,
    loginAsUser,
  }) => {
    await loginAsUser(EDIT_USER_POSITIONS_PK);
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto('/profile');

    await expect(
      page.locator('[data-testid="user-card-nickname"]').first(),
    ).toBeVisible({ timeout: 15_000 });

    await openDotaTab(page);

    // Force a 500 on the game-dota PATCH — verifies the mutation onError path:
    // error toast appears and the modal stays open (mutation failures do NOT
    // trip the render-phase ErrorBoundary).
    await page.route('**/api/users/me/profile/game/dota/', (route) => {
      if (route.request().method() === 'PATCH') {
        return route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'simulated server error' }),
        });
      }
      return route.continue();
    });

    // Change carry so the form is dirty and the PATCH fires.
    const originalCarry = await readDotaPosition(page, 'carry');
    const targetCarry = originalCarry.startsWith('1:') ? 5 : 1;
    await setDotaPosition(page, 'carry', targetCarry);
    await page.locator('[data-testid="edit-user-dota-save"]').click();

    // Error toast (sonner) — copy from DotaTab.tsx onError.
    await expect(page.getByText(/failed to update dota profile/i)).toBeVisible({
      timeout: 10_000,
    });

    // Modal stays open and usable for a retry.
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(
      page.locator('[data-testid="edit-user-dota-save"]'),
    ).toBeVisible();

    // Drop the override so the cancel path doesn't try to PATCH again.
    await page.unroute('**/api/users/me/profile/game/dota/');

    // Cancel — the failed PATCH didn't persist, so no restore is needed.
    await page
      .getByRole('dialog')
      .getByRole('button', { name: /cancel/i })
      .click();
    await expect(page.getByRole('dialog')).toBeHidden({ timeout: 5_000 });
  });
});
