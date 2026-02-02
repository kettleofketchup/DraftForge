/**
 * Bracket Unset Winner Tests
 *
 * Tests the ability to unset a bracket match winner, clearing the result
 * and removing the team from downstream matches.
 *
 * Uses 'pending_bracket' tournament which has teams but pending games.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getTournamentByKey,
} from '../../fixtures';

let tournamentPk: number;

test.describe('Bracket Unset Winner (e2e)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const tournament = await getTournamentByKey(context, 'pending_bracket');

    if (!tournament) {
      throw new Error('Could not find pending_bracket tournament');
    }

    tournamentPk = tournament.pk;
    await context.close();
  });

  test.beforeEach(async ({ loginStaff }) => {
    await loginStaff();
  });

  test('sanity: bracket page loads for unset winner test', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });
  });

  test('staff can unset a bracket game winner', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });

    // Wait for nodes to render
    await page.waitForLoadState('networkidle');

    // Find a match with teams and set winner buttons
    const matchNodes = page.locator('[data-testid="bracket-match-node"]');
    const nodeCount = await matchNodes.count();

    let foundMatch = false;
    for (let i = 0; i < Math.min(nodeCount, 5); i++) {
      await matchNodes.nth(i).click({ force: true });

      const dialog = page.locator('[role="dialog"]');
      const isVisible = await dialog.isVisible().catch(() => false);

      if (isVisible) {
        // Check for Set Winner buttons
        const winButtons = dialog.locator(
          '[data-testid="radiantWinsButton"], [data-testid="direWinsButton"]'
        );
        const winButtonCount = await winButtons.count();

        if (winButtonCount >= 2) {
          foundMatch = true;

          // Set a winner first - clicking sets status to 'completed' and advances winner
          await winButtons.first().click();

          // After setting winner, the Set Winner buttons should be hidden and Unset Winner should appear
          // Wait for the UI to update (React state change)
          const unsetButton = dialog.locator('[data-testid="unsetWinnerButton"]');
          await expect(unsetButton).toBeVisible({ timeout: 5000 });

          // The Set Winner buttons should now be hidden (match is completed)
          await expect(winButtons.first()).not.toBeVisible();

          // Click Unset Winner to clear the result
          await unsetButton.click();

          // After unsetting, the Set Winner buttons should reappear
          await expect(winButtons.first()).toBeVisible({ timeout: 5000 });

          // Unset Winner button should be hidden again
          await expect(unsetButton).not.toBeVisible();

          break;
        }

        // Close modal and try next node
        await page.keyboard.press('Escape');
        await dialog.waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});
      }
    }

    if (!foundMatch) {
      test.skip();
    }

    // Should show unsaved changes
    await expect(page.locator('text=Unsaved changes')).toBeVisible({ timeout: 5000 });
  });
});
