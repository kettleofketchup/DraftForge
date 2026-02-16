/**
 * Shuffle Draft Tie Resolution Overlay Tests
 *
 * Tests that the TieResolutionOverlay dialog appears for all connected
 * users when a shuffle draft tie occurs. Uses the shuffle_tie_resolution
 * tournament which has controlled MMR values:
 *
 * - Captain 1 (2000 MMR) picks first (no tie)
 * - Captains 2, 3, 4 (3000 MMR each) tie after first pick
 * - All available players have 2000 MMR
 *
 * After Captain 1 picks any player (2000 MMR):
 * - Team 1 = 4000, Teams 2/3/4 = 3000 → 3-way tie → tie_roll event → overlay
 */

import {
  test,
  expect,
  getTournamentByKey,
  type TournamentData,
} from '../../fixtures';

test.describe('Shuffle Draft - Tie Resolution Overlay', () => {
  let tournamentData: TournamentData;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const tournament = await getTournamentByKey(context, 'shuffle_tie_resolution');
    if (!tournament) {
      throw new Error(
        'Could not find shuffle_tie_resolution tournament. ' +
        'Run: just db::populate::fresh'
      );
    }
    tournamentData = tournament;
    console.log(`Tournament: ${tournamentData.name} (pk=${tournamentData.pk})`);
    await context.close();
  });

  test.beforeEach(async ({ context, loginAdmin }) => {
    await context.clearCookies();
    await loginAdmin();
  });

  test('should show TieResolutionOverlay after first pick triggers 3-way tie', async ({
    page,
  }) => {
    // Navigate to tournament
    await page.goto(`/tournament/${tournamentData.pk}`);
    await page.locator('[data-testid="tournamentDetailPage"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });

    // Go to Teams tab
    await page.locator('[data-testid="teamsTab"]').click();
    await page.locator('[data-testid="teamsTabContent"]').waitFor({
      state: 'visible',
    });

    // Open draft modal
    const draftButton = page.locator(
      '[data-testid="liveTeamDraftButton"], [data-testid="startTeamDraftButton"], [data-testid="viewTeamDraftButton"]'
    ).first();
    await draftButton.click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 10000 });

    // Find and click first available pick button
    const pickButtons = dialog.locator('[data-testid="pickPlayerButton"]');
    await pickButtons.first().waitFor({ state: 'visible', timeout: 10000 });
    const pickCount = await pickButtons.count();
    expect(pickCount).toBeGreaterThan(0);

    await pickButtons.first().click();

    // Confirm the pick if a confirmation dialog appears
    const alertDialog = page.locator('[role="alertdialog"]');
    if (await alertDialog.isVisible({ timeout: 3000 }).catch(() => false)) {
      await alertDialog.locator('[data-testid="confirmPickButton"]').click();
    }

    // Wait for the TieResolutionOverlay to appear
    // The WebSocket tie_roll event triggers this overlay
    const tieOverlay = page.locator('[data-testid="tie-resolution-overlay"]');
    await expect(tieOverlay).toBeVisible({ timeout: 15000 });

    // Verify overlay content
    // Title should say "Tie Breaker!"
    await expect(tieOverlay.locator('text=Tie Breaker!')).toBeVisible();

    // Should show 3 tied team names (Teams 2, 3, 4 at 3000 MMR)
    // The tied teams all have "3,000 MMR" displayed
    const mmrLabels = tieOverlay.locator('text=3,000 MMR');
    await expect(mmrLabels.first()).toBeVisible();

    // Should show roll round(s)
    await expect(tieOverlay.locator('text=Round 1:')).toBeVisible();

    // Should show winner announcement
    const winnerAnnouncement = tieOverlay.locator('[data-testid="tie-resolution-winner"]');
    await expect(winnerAnnouncement).toBeVisible();
    await expect(winnerAnnouncement).toContainText('picks next!');

    // Continue button should be visible
    const continueBtn = tieOverlay.locator('[data-testid="tie-resolution-continue"]');
    await expect(continueBtn).toBeVisible();
  });

  test('should dismiss TieResolutionOverlay when Continue is clicked', async ({
    page,
  }) => {
    // Navigate to tournament
    await page.goto(`/tournament/${tournamentData.pk}`);
    await page.locator('[data-testid="tournamentDetailPage"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });

    // Go to Teams tab and open draft
    await page.locator('[data-testid="teamsTab"]').click();
    await page.locator('[data-testid="teamsTabContent"]').waitFor({ state: 'visible' });

    const draftButton = page.locator(
      '[data-testid="liveTeamDraftButton"], [data-testid="startTeamDraftButton"], [data-testid="viewTeamDraftButton"]'
    ).first();
    await draftButton.click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 10000 });

    // Make a pick to trigger the tie
    const pickButtons = dialog.locator('[data-testid="pickPlayerButton"]');
    await pickButtons.first().waitFor({ state: 'visible', timeout: 10000 });
    await pickButtons.first().click();

    // Confirm pick
    const alertDialog = page.locator('[role="alertdialog"]');
    if (await alertDialog.isVisible({ timeout: 3000 }).catch(() => false)) {
      await alertDialog.locator('[data-testid="confirmPickButton"]').click();
    }

    // Wait for overlay
    const tieOverlay = page.locator('[data-testid="tie-resolution-overlay"]');
    await expect(tieOverlay).toBeVisible({ timeout: 15000 });

    // Click Continue
    await tieOverlay.locator('[data-testid="tie-resolution-continue"]').click();

    // Overlay should be dismissed
    await expect(tieOverlay).not.toBeVisible({ timeout: 5000 });

    // Draft dialog should still be open
    await expect(dialog).toBeVisible();
  });
});
