/**
 * Bracket Unset Winner Tests
 *
 * Tests the ability to unset a bracket match winner, clearing the result
 * and removing the team from downstream matches.
 *
 * Uses dedicated 'bracket_unset_winner' tournament with:
 * - 4 teams in double elimination bracket
 * - All games pending (no completed games)
 * - Teams assigned to first round games
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
    const tournament = await getTournamentByKey(context, 'bracket_unset_winner');

    if (!tournament) {
      throw new Error('Could not find bracket_unset_winner tournament');
    }

    tournamentPk = tournament.pk;
    await context.close();
  });

  test.beforeEach(async ({ loginStaff }) => {
    await loginStaff();
  });

  test('@cicd sanity: staff can set and unset bracket winner', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });

    // Wait for bracket to fully render
    await page.waitForLoadState('networkidle');

    // Debug: Check if user is logged in via API call from browser
    const userApiResponse = await page.evaluate(async () => {
      try {
        const response = await fetch('/api/v1/users/me/', {
          credentials: 'include',
        });
        if (response.ok) {
          return await response.json();
        }
        return { error: `HTTP ${response.status}` };
      } catch (e) {
        return { error: String(e) };
      }
    });
    console.log('User from /api/v1/users/me/:', JSON.stringify(userApiResponse, null, 2));

    // Find a match with teams and Set Winner buttons
    const matchNodes = page.locator('[data-testid="bracket-match-node"]');
    const nodeCount = await matchNodes.count();
    console.log(`Found ${nodeCount} match nodes`);
    const dialog = page.locator('[data-testid="matchStatsModal"]');

    let foundMatch = false;
    for (let i = 0; i < Math.min(nodeCount, 6); i++) {
      await matchNodes.nth(i).click({ force: true });

      const isVisible = await dialog.isVisible().catch(() => false);
      console.log(`Node ${i}: dialog visible = ${isVisible}`);
      if (!isVisible) continue;

      // Debug: Get dialog content to see what's shown
      const dialogContent = await dialog.textContent();
      console.log(`Node ${i} dialog content (first 300 chars):`, dialogContent?.substring(0, 300));

      // Check for Set Winner buttons (only visible when match has teams)
      const setWinnerButton = dialog.locator('[data-testid="radiantWinsButton"]');
      const btnVisible = await setWinnerButton.isVisible({ timeout: 1000 }).catch(() => false);
      console.log(`Node ${i}: setWinnerButton visible = ${btnVisible}`);

      if (btnVisible) {
        foundMatch = true;

        // Set a winner (radiant)
        await setWinnerButton.click();

        // Unset Winner button should now appear
        const unsetButton = dialog.locator('[data-testid="unsetWinnerButton"]');
        await expect(unsetButton).toBeVisible({ timeout: 5000 });

        // Click Unset Winner to clear the result
        await unsetButton.click();

        // Set Winner buttons should reappear after unsetting
        await expect(setWinnerButton).toBeVisible({ timeout: 5000 });
        break;
      }

      // Close modal and try next node
      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});
    }

    expect(foundMatch, 'Could not find a match with teams and Set Winner buttons').toBe(true);
  });

  test('staff can unset a bracket game winner', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });

    // Wait for nodes to render
    await page.waitForLoadState('networkidle');

    // Find a match with teams and set winner buttons (status !== 'completed')
    const matchNodes = page.locator('[data-testid="bracket-match-node"]');
    const nodeCount = await matchNodes.count();

    let foundMatch = false;
    let matchIndex = -1;
    for (let i = 0; i < Math.min(nodeCount, 5); i++) {
      await matchNodes.nth(i).click({ force: true });

      const dialog = page.locator('[data-testid="matchStatsModal"]');
      const isVisible = await dialog.isVisible().catch(() => false);

      if (isVisible) {
        // Check for Set Winner buttons (only visible when match is NOT completed)
        const winButtons = dialog.locator(
          '[data-testid="radiantWinsButton"], [data-testid="direWinsButton"]'
        );
        const winButtonCount = await winButtons.count();

        if (winButtonCount >= 2) {
          foundMatch = true;
          matchIndex = i;

          // Set a winner first - clicking sets status to 'completed' and advances winner
          await winButtons.first().click();

          // Wait for state to settle
          await page.waitForTimeout(500);

          break;
        }

        // Close modal and try next node
        await page.keyboard.press('Escape');
        await dialog.waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});
      }
    }

    expect(foundMatch, 'Could not find a pending match with Set Winner buttons in the bracket').toBe(true);

    // Close the current modal
    const dialog = page.locator('[data-testid="matchStatsModal"]');
    if (await dialog.isVisible().catch(() => false)) {
      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});
    }

    // Reopen the same match to see updated state
    await matchNodes.nth(matchIndex).click({ force: true });
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Debug: Check if the match shows as completed (has "Final" badge or winner indicator)
    // The modal should now show the match as completed with a winner
    const dialogContent = await dialog.textContent();
    console.log('Dialog content after setting winner:', dialogContent?.substring(0, 500));

    // Now the Unset Winner button should be visible
    const unsetButton = dialog.locator('[data-testid="unsetWinnerButton"]');
    await expect(unsetButton).toBeVisible({ timeout: 5000 });

    // Click Unset Winner to clear the result
    await unsetButton.click();

    // Wait for state to settle
    await page.waitForTimeout(500);

    // Close and reopen to see updated state
    await page.keyboard.press('Escape');
    await dialog.waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});

    await matchNodes.nth(matchIndex).click({ force: true });
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // After unsetting, the Set Winner buttons should reappear
    const winButtons = dialog.locator(
      '[data-testid="radiantWinsButton"], [data-testid="direWinsButton"]'
    );
    await expect(winButtons.first()).toBeVisible({ timeout: 5000 });

    // Unset Winner button should be hidden again
    await expect(unsetButton).not.toBeVisible();

    // Should show unsaved changes
    await expect(page.locator('text=Unsaved changes')).toBeVisible({ timeout: 5000 });
  });
});
