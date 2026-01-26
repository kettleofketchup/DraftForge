/**
 * Snake Draft Demo - Full Flow Video Recording
 *
 * Records a complete snake draft from start to finish for documentation.
 * Snake draft has a predictable pattern where pick order reverses each round.
 *
 * Video output: 1:1 aspect ratio (800x800) for docs and social media.
 */

import { test, expect } from '@playwright/test';
import { loginAsDiscordId, waitForHydration } from '../fixtures/auth';

const API_URL = 'https://localhost/api';
const BASE_URL = 'https://localhost';

interface TournamentData {
  pk: number;
  name: string;
  teams: Array<{
    pk: number;
    name: string;
    captain: { pk: number; username: string };
    draft_order: number;
  }>;
  draft?: {
    pk: number;
    draft_style: string;
    state: string;
  };
}

test.describe('Snake Draft Demo', () => {
  test('Complete Snake Draft Flow', async ({ page, context }) => {
    // Increase timeout for full demo recording
    test.setTimeout(300_000);

    // Get a tournament with snake draft setup
    const response = await context.request.get(
      `${API_URL}/tests/tournament-by-key/completed_bracket/`,
      { failOnStatusCode: false, timeout: 10000 }
    );

    if (!response.ok()) {
      throw new Error(
        `Failed to get tournament data. Run 'inv db.populate.all' first.`
      );
    }

    const tournament: TournamentData = await response.json();
    console.log(`Demo: ${tournament.name} (pk=${tournament.pk})`);

    // Reset the draft to initial state
    await context.request.post(
      `${API_URL}/tests/tournament/${tournament.pk}/reset-draft/`,
      { failOnStatusCode: false }
    );

    // Login as admin for full control
    await loginAsDiscordId(context, '764290890617192469');

    // Navigate to tournament
    await page.goto(`${BASE_URL}/tournament/${tournament.pk}`);
    await waitForHydration(page);

    // Pause for title shot
    await page.waitForTimeout(1500);

    // Click Teams tab
    const teamsTab = page.locator('[data-testid="teamsTab"]');
    await teamsTab.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // Open draft modal
    const startDraftButton = page.locator(
      'button:has-text("Start Draft"), button:has-text("Live Draft")'
    );
    await startDraftButton.first().click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();
    await page.waitForTimeout(1000);

    // Set draft style to Snake
    const draftStyleButton = page.locator('button:has-text("Draft Style")');
    if (await draftStyleButton.isVisible().catch(() => false)) {
      await draftStyleButton.click();
      await page.waitForTimeout(500);

      // Select Snake
      const snakeOption = page.locator(
        'button:has-text("Snake"), [value="snake"], text=/snake/i'
      );
      await snakeOption.first().click();
      await page.waitForTimeout(500);

      // Confirm selection
      const confirmBtn = page.locator(
        'button:has-text("Confirm"), button:has-text("Apply")'
      );
      if (await confirmBtn.isVisible().catch(() => false)) {
        await confirmBtn.click();
      }
      await page.waitForLoadState('networkidle');
    }

    // Start/Restart draft
    const restartButton = page.locator('button:has-text("Restart Draft")');
    if (await restartButton.isVisible().catch(() => false)) {
      await restartButton.click();

      // Confirm restart
      const alertDialog = page.locator('[role="alertdialog"]');
      if (await alertDialog.isVisible().catch(() => false)) {
        const confirmBtn = alertDialog.locator(
          'button:has-text("Confirm"), button:has-text("Restart")'
        );
        await confirmBtn.first().click();
      }
      await page.waitForLoadState('networkidle');
    }

    await page.waitForTimeout(1500);

    // Perform picks - snake draft follows predictable pattern
    // Round 1: 1 → 2 → 3 → 4
    // Round 2: 4 → 3 → 2 → 1
    // etc.
    const maxPicks = 16; // 4 teams x 4 players each
    let picksMade = 0;
    let currentRound = 1;

    for (let i = 0; i < maxPicks; i++) {
      const dialogEl = page.locator('[role="dialog"]');
      const pickButtons = dialogEl.locator('button:has-text("Pick")');
      const pickCount = await pickButtons.count();

      if (pickCount === 0) {
        console.log(`No more picks available after ${picksMade} picks`);
        break;
      }

      // Determine round for logging
      const pickInRound = (picksMade % 4) + 1;
      if (pickInRound === 1 && picksMade > 0) {
        currentRound++;
      }

      console.log(
        `Round ${currentRound}, Pick ${pickInRound}: Making pick ${picksMade + 1}/${maxPicks}`
      );

      // Click first available pick
      await pickButtons.first().click();
      await page.waitForTimeout(300);

      // Handle confirmation
      const confirmDialog = page.locator('[role="alertdialog"]');
      if (await confirmDialog.isVisible().catch(() => false)) {
        const pickConfirmBtn = confirmDialog.locator(
          'button:has-text("Confirm"), button:has-text("Pick")'
        );
        if (await pickConfirmBtn.isVisible().catch(() => false)) {
          await pickConfirmBtn.first().click();
        }
      }

      await page.waitForLoadState('networkidle');

      // Longer pause at round boundaries
      if (pickInRound === 4) {
        await page.waitForTimeout(1500); // Round complete pause
      } else {
        await page.waitForTimeout(600); // Normal pick pause
      }

      picksMade++;
    }

    // Final pause to show completed draft
    await page.waitForTimeout(3000);

    console.log(
      `Snake Draft Demo complete! Made ${picksMade} picks across ${currentRound} rounds.`
    );
  });
});
