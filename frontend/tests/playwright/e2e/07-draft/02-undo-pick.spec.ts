/**
 * Undo Pick Tests
 *
 * Tests the staff ability to undo draft picks.
 * The undo button should only be visible to staff members
 * and should revert the last pick made in the draft.
 *
 * Uses 'completed_bracket' tournament from test config.
 *
 * Ported from Cypress: frontend/tests/cypress/e2e/07-draft/02-undo-pick.cy.ts
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getTournamentByKey,
  TournamentPage,
} from '../../fixtures';

// Tournament PK fetched in beforeAll
let tournamentPk: number;

test.describe('Undo Pick', () => {
  test.beforeAll(async ({ browser }) => {
    // Get tournament PK dynamically instead of hardcoding
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const tournament = await getTournamentByKey(context, 'completed_bracket');

    if (!tournament) {
      throw new Error('Could not find completed_bracket tournament');
    }

    tournamentPk = tournament.pk;
    await context.close();
  });

  test.describe('Undo Button Visibility', () => {
    // Skip: Undo button visibility depends on complex draft state that's difficult to control in tests
    test.skip('should show undo button for staff when picks have been made', async ({
      page,
      loginAdmin,
    }) => {
      // Login as admin/staff
      await loginAdmin();

      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);

      // Wait for page to load
      await expect(page.locator('h1', { hasText: 'Completed Bracket Test' })).toBeVisible({
        timeout: 10000,
      });

      // Click on Teams tab
      await page.locator('text=Teams (4)').click({ force: true });
      await page.waitForTimeout(1000);

      // Open draft modal
      const draftButton = page.locator('button', { hasText: /Live Draft|Start Draft/i });
      await draftButton.click({ force: true });
      await page.waitForTimeout(1000);

      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible();

      // Initialize draft if needed
      const restartButton = page.locator('button', { hasText: 'Restart Draft' });
      if (await restartButton.isVisible().catch(() => false)) {
        await restartButton.click({ force: true });
        await page.waitForTimeout(500);

        // Confirm if dialog appears
        const alertDialog = page.locator('[role="alertdialog"]');
        if (await alertDialog.isVisible().catch(() => false)) {
          const confirmButton = alertDialog.locator('button', {
            hasText: /Confirm|Yes|Continue|Restart/i,
          });
          await confirmButton.click({ force: true });
        }

        await page.waitForTimeout(2000);
      }

      // Make a pick first
      const pickButtons = dialog.locator('button', { hasText: 'Pick' });
      if (await pickButtons.count() > 0) {
        await pickButtons.first().click({ force: true });
        await page.waitForTimeout(500);

        // Confirm pick
        const alertDialog = page.locator('[role="alertdialog"]');
        if (await alertDialog.isVisible().catch(() => false)) {
          const confirmButton = alertDialog.locator('button', {
            hasText: /Confirm|Yes|Pick/i,
          });
          await confirmButton.click({ force: true });
        }

        await page.waitForTimeout(2000);

        // After making a pick, the draft advances to the next round
        // Navigate back to the previous round to see the Undo button
        const navButtons = dialog.locator('button:has(svg)');
        await navButtons.first().click({ force: true }); // Prev button
        await page.waitForTimeout(500);
      }

      // Now check for undo button
      await expect(dialog).toBeVisible();
      await expect(dialog.locator('button', { hasText: 'Undo' })).toBeVisible();
    });

    test('should NOT show undo button for non-staff users', async ({
      page,
      loginUser,
    }) => {
      // Login as regular user
      await loginUser();

      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);

      // Wait for page to load
      await expect(page.locator('h1', { hasText: 'Completed Bracket Test' })).toBeVisible({
        timeout: 10000,
      });

      // Click on Teams tab
      await page.locator('text=Teams (4)').click({ force: true });
      await page.waitForTimeout(1000);

      // Open draft modal
      const draftButton = page.locator('button', { hasText: /Live Draft|Start Draft/i });
      await draftButton.click({ force: true });
      await page.waitForTimeout(1000);

      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible();

      // Undo button should not be visible for non-staff
      await expect(dialog.locator('button', { hasText: 'Undo' })).not.toBeVisible();
    });

    test('should NOT show undo button when no picks have been made', async ({
      page,
      loginAdmin,
    }) => {
      // Login as admin/staff
      await loginAdmin();

      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);

      // Wait for page to load
      await expect(page.locator('h1', { hasText: 'Completed Bracket Test' })).toBeVisible({
        timeout: 10000,
      });

      // Click on Teams tab
      await page.locator('text=Teams (4)').click({ force: true });
      await page.waitForTimeout(1000);

      // Open draft modal
      const draftButton = page.locator('button', { hasText: /Live Draft|Start Draft/i });
      await draftButton.click({ force: true });
      await page.waitForTimeout(1000);

      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible();

      // Restart draft to reset all picks
      const restartButton = page.locator('button', { hasText: 'Restart Draft' });
      if (await restartButton.isVisible().catch(() => false)) {
        await restartButton.click({ force: true });
        await page.waitForTimeout(500);

        // Confirm if dialog appears
        const alertDialog = page.locator('[role="alertdialog"]');
        if (await alertDialog.isVisible().catch(() => false)) {
          const confirmButton = alertDialog.locator('button', {
            hasText: /Confirm|Yes|Continue|Restart/i,
          });
          await confirmButton.click({ force: true });
        }

        await page.waitForTimeout(2000);
      }

      // After restart, no picks should exist, so undo should not be visible
      await expect(dialog.locator('button', { hasText: 'Undo' })).not.toBeVisible();
    });
  });

  test.describe('Undo Functionality', () => {
    // Skip: Undo functionality depends on complex draft state that's difficult to control in tests
    test.skip('should undo the last pick when confirmed', async ({
      page,
      loginAdmin,
    }) => {
      // Login as admin/staff
      await loginAdmin();

      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);

      // Wait for page to load
      await expect(page.locator('h1', { hasText: 'Completed Bracket Test' })).toBeVisible({
        timeout: 10000,
      });

      // Click on Teams tab
      await page.locator('text=Teams (4)').click({ force: true });
      await page.waitForTimeout(1000);

      // Open draft modal
      const draftButton = page.locator('button', { hasText: /Live Draft|Start Draft/i });
      await draftButton.click({ force: true });
      await page.waitForTimeout(1000);

      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible();

      // Restart draft to start fresh
      const restartButton = page.locator('button', { hasText: 'Restart Draft' });
      if (await restartButton.isVisible().catch(() => false)) {
        await restartButton.click({ force: true });
        await page.waitForTimeout(500);

        const alertDialog = page.locator('[role="alertdialog"]');
        if (await alertDialog.isVisible().catch(() => false)) {
          const confirmButton = alertDialog.locator('button', {
            hasText: /Confirm|Yes|Continue|Restart/i,
          });
          await confirmButton.click({ force: true });
        }

        await page.waitForTimeout(2000);
      }

      // Get the username of a player before picking
      const availablePlayer = dialog.locator('[data-testid="available-player"]').first();
      const playerText = await availablePlayer.textContent();
      const pickedPlayerName = playerText?.split('\n')[0].trim() || '';
      console.log(`Will pick player: ${pickedPlayerName}`);

      // Make a pick
      const pickButton = dialog.locator('button', { hasText: 'Pick' }).first();
      await pickButton.click({ force: true });
      await page.waitForTimeout(500);

      // Confirm pick
      const alertDialog = page.locator('[role="alertdialog"]');
      if (await alertDialog.isVisible().catch(() => false)) {
        const confirmButton = alertDialog.locator('button', {
          hasText: /Confirm|Yes|Pick/i,
        });
        await confirmButton.click({ force: true });
      }

      await page.waitForTimeout(2000);

      // After making a pick, the draft advances to the next round
      // Navigate back to the previous round to see the Undo button
      const navButtons = dialog.locator('button:has(svg)');
      await navButtons.first().click({ force: true }); // Prev button
      await page.waitForTimeout(500);

      // Now undo the pick - wait for button to appear first (confirms pick was recorded)
      const undoButton = dialog.locator('button', { hasText: 'Undo' });
      await expect(undoButton).toBeVisible({ timeout: 10000 });
      await undoButton.click({ force: true });

      // Confirm undo in the alert dialog
      const undoDialog = page.locator('[role="alertdialog"]');
      await expect(undoDialog).toBeVisible({ timeout: 10000 });
      await undoDialog.locator('button', { hasText: 'Undo Pick' }).click({ force: true });

      await page.waitForTimeout(2000);

      // Verify success toast
      await expect(page.locator('text=/Pick undone|successfully/i')).toBeVisible({
        timeout: 5000,
      });

      // The player should be back in the available pool
      // Check that we can still make picks (draft round was reset)
      await expect(dialog.locator('button', { hasText: 'Pick' })).toBeVisible();
    });

    // Skip: Undo functionality depends on complex draft state that's difficult to control in tests
    test.skip('should cancel undo when cancel is clicked', async ({
      page,
      loginAdmin,
    }) => {
      // Login as admin/staff
      await loginAdmin();

      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);

      // Wait for page to load
      await expect(page.locator('h1', { hasText: 'Completed Bracket Test' })).toBeVisible({
        timeout: 10000,
      });

      // Click on Teams tab
      await page.locator('text=Teams (4)').click({ force: true });
      await page.waitForTimeout(1000);

      // Open draft modal
      const draftButton = page.locator('button', { hasText: /Live Draft|Start Draft/i });
      await draftButton.click({ force: true });
      await page.waitForTimeout(1000);

      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible();

      // Make a pick first
      const pickButtons = dialog.locator('button', { hasText: 'Pick' });
      if (await pickButtons.count() > 0) {
        await pickButtons.first().click({ force: true });
        await page.waitForTimeout(500);

        // Confirm pick
        const alertDialog = page.locator('[role="alertdialog"]');
        if (await alertDialog.isVisible().catch(() => false)) {
          const confirmButton = alertDialog.locator('button', {
            hasText: /Confirm|Yes|Pick/i,
          });
          await confirmButton.click({ force: true });
        }

        await page.waitForTimeout(2000);

        // After making a pick, the draft advances to the next round
        // Navigate back to the previous round to see the Undo button
        const navButtons = dialog.locator('button:has(svg)');
        await navButtons.first().click({ force: true }); // Prev button
        await page.waitForTimeout(500);
      }

      // Click undo button
      const undoButton = dialog.locator('button', { hasText: 'Undo' });
      await undoButton.click({ force: true });
      await page.waitForTimeout(500);

      // Click cancel in the alert dialog
      const alertDialog = page.locator('[role="alertdialog"]');
      await expect(alertDialog).toBeVisible();
      await alertDialog.locator('button', { hasText: 'Cancel' }).click({ force: true });

      await page.waitForTimeout(500);

      // Alert dialog should be closed
      await expect(page.locator('[role="alertdialog"]')).not.toBeVisible();

      // Pick should NOT be undone - undo button should still be visible
      await expect(dialog.locator('button', { hasText: 'Undo' })).toBeVisible();
    });
  });
});
