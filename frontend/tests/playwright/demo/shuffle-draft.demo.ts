/**
 * Shuffle Draft Demo - Full Flow Video Recording
 *
 * Records a complete shuffle draft from start to finish for documentation.
 * Shuffle draft picks based on lowest team MMR - after each pick,
 * the team with lowest total MMR picks next.
 *
 * Video output: 1:1 aspect ratio (800x800) for docs and social media.
 * Named output: shuffle_draft.webm
 */

import { test, expect } from '@playwright/test';
import { loginAsDiscordId, waitForHydration } from '../fixtures/auth';
import * as path from 'path';

const API_URL = 'https://localhost/api';
const BASE_URL = 'https://localhost';
const VIDEO_OUTPUT_DIR = 'demo-results/videos';

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

test.describe('Shuffle Draft Demo', () => {
  test('Complete Shuffle MMR Draft Flow', async ({ page, context }) => {
    // Increase timeout for full demo recording
    test.setTimeout(300_000);

    // Get shuffle draft tournament
    const response = await context.request.get(
      `${API_URL}/tests/tournament-by-key/shuffle_draft_captain_turn/`,
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
    await loginAsDiscordId(context, '764290890617192469'); // Admin Discord ID

    // Navigate to tournament
    await page.goto(`${BASE_URL}/tournament/${tournament.pk}`);
    await waitForHydration(page);

    // Pause for title shot
    await page.waitForTimeout(1500);

    // Click Teams tab
    const teamsTab = page.locator('[data-testid="teamsTab"]');
    await teamsTab.click();
    await page.waitForTimeout(1500);

    // Open draft modal
    const startDraftButton = page.locator(
      'button:has-text("Start Draft"), button:has-text("Live Draft")'
    );
    await startDraftButton.first().click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();
    await page.waitForTimeout(1000);

    // Set draft style to Shuffle
    const draftStyleButton = page.locator('button:has-text("Draft Style")');
    if (await draftStyleButton.isVisible().catch(() => false)) {
      await draftStyleButton.click();
      await page.waitForTimeout(500);

      // Select Shuffle
      const shuffleOption = page.locator(
        'button:has-text("Shuffle"), [value="shuffle"], text=/shuffle/i'
      );
      await shuffleOption.first().click();
      await page.waitForTimeout(500);

      // Confirm selection
      const confirmBtn = page.locator(
        'button:has-text("Confirm"), button:has-text("Apply")'
      );
      if (await confirmBtn.isVisible().catch(() => false)) {
        await confirmBtn.click();
      }
      await page.waitForTimeout(1000);
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
      await page.waitForTimeout(1000);
    }

    await page.waitForTimeout(1500);

    // Perform picks - shuffle draft will show MMR-based ordering
    const maxPicks = 16; // 4 teams x 4 players each
    let picksMade = 0;

    for (let i = 0; i < maxPicks; i++) {
      const dialogEl = page.locator('[role="dialog"]');
      const pickButtons = dialogEl.locator('button:has-text("Pick")');
      const pickCount = await pickButtons.count();

      if (pickCount === 0) {
        console.log(`No more picks available after ${picksMade} picks`);
        break;
      }

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

      await page.waitForTimeout(1000);
      await page.waitForTimeout(800); // Pause between picks for video

      picksMade++;
      console.log(`Pick ${picksMade}/${maxPicks} completed`);

      // Check for tie resolution overlay (unique to shuffle draft)
      const tieOverlay = page.locator('[data-testid="tie-resolution-overlay"]');
      if (await tieOverlay.isVisible().catch(() => false)) {
        console.log('Tie resolution in progress...');
        await page.waitForTimeout(2000); // Let dice animation play

        const continueBtn = tieOverlay.locator('button:has-text("Continue")');
        if (await continueBtn.isVisible().catch(() => false)) {
          await continueBtn.click();
          await page.waitForTimeout(500);
        }
      }
    }

    // Final pause to show completed draft
    await page.waitForTimeout(3000);

    // Save video with named output
    const video = page.video();
    if (video) {
      await video.saveAs(path.join(VIDEO_OUTPUT_DIR, 'shuffle_draft.webm'));
    }

    console.log(`Shuffle Draft Demo complete! Made ${picksMade} picks.`);
  });
});
