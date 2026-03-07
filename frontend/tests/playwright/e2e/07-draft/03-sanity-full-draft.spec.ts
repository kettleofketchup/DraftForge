/**
 * Team Draft Sanity Test - Full Draft Lifecycle
 *
 * Tests the complete team draft flow from start to finish:
 * 1. Tournament with no draft initialized
 * 2. Staff opens draft modal, sees "Start Draft" UI
 * 3. Selects draft style and starts the draft
 * 4. Picks all players through all draft rounds
 * 5. Verifies draft completes
 *
 * Uses the 'draft_not_started' test tournament config
 * (4 teams, 20 users, draft_state="not_started").
 */

import {
  test,
  expect,
  getTournamentByKey,
  resetTournamentByKey,
  TournamentPage,
  visitAndWaitForHydration,
  type TournamentData,
} from '../../fixtures';

test.describe('Team Draft - Full Lifecycle Sanity', () => {
  let tournamentData: TournamentData;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Reset fixture — the full draft test mutates it (starts + completes the draft)
    const reset = await resetTournamentByKey(context, 'draft_not_started');
    const tournament = reset ?? await getTournamentByKey(context, 'draft_not_started');
    if (!tournament) {
      throw new Error('Could not find draft_not_started tournament');
    }
    tournamentData = tournament;
    console.log(`Tournament: ${tournamentData.name} (pk=${tournamentData.pk})`);
    console.log(`Teams: ${tournamentData.teams.length}`);
    console.log(`Users: ${tournamentData.users.length}`);
    console.log(`Captains: ${tournamentData.captains.join(', ')}`);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test('non-staff sees waiting message when draft not started', async ({
    page,
    loginUser,
  }) => {
    await loginUser();
    await visitAndWaitForHydration(page, `/tournament/${tournamentData.pk}/teams`);

    // Click start draft button to open the draft modal
    const tournamentPage = new TournamentPage(page);
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Non-staff should see "Draft Not Started" message
    await expect(dialog.getByText('Draft Not Started')).toBeVisible();
    await expect(dialog.getByText('Waiting for tournament staff')).toBeVisible();

    // Should NOT see the Start Draft button
    await expect(dialog.locator('[data-testid="start-draft-button"]')).not.toBeVisible();
  });

  test('staff can start and complete a full snake draft', async ({
    page,
    loginAdmin,
  }) => {
    // Increase timeout for full draft run (16 picks with WS-driven UI updates)
    test.setTimeout(120_000);

    await loginAdmin();
    await visitAndWaitForHydration(page, `/tournament/${tournamentData.pk}/teams`);

    // Open draft modal
    const tournamentPage = new TournamentPage(page);
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // --- Step 1: Verify "Start Draft" UI ---
    await expect(dialog.getByText('Start Team Draft')).toBeVisible();
    await expect(dialog.locator('[data-testid="start-draft-button"]')).toBeVisible();

    // --- Step 2: Select snake draft style and start ---
    // The style selector defaults to "snake" so just click Start Draft
    await dialog.locator('[data-testid="start-draft-button"]').click();

    // Wait for draft to initialize - pick buttons should appear
    await expect(dialog.locator('[data-testid="pickPlayerButton"]').first()).toBeVisible({
      timeout: 30_000,
    });

    // --- Step 3: Pick all players ---
    // 4 teams with 5 members each = 20 users total
    // 4 captains are pre-assigned, so 16 picks needed
    const totalPicks = tournamentData.users.length - tournamentData.captains.length;
    console.log(`Total picks needed: ${totalPicks}`);

    let picksMade = 0;

    for (let i = 0; i < totalPicks; i++) {
      // Wait for a pick button to become visible
      const pickButton = dialog.locator('[data-testid="pickPlayerButton"]').first();
      try {
        await pickButton.waitFor({ state: 'visible', timeout: 10_000 });
      } catch {
        console.log(`No pick button visible after ${picksMade} picks - draft may be complete`);
        break;
      }

      // Count players before pick to detect when UI updates
      const playerCountBefore = await dialog.locator('[data-testid="pickPlayerButton"]').count();

      // Click the first available pick button
      await pickButton.click();

      // Handle confirmation dialog
      const alertDialog = page.locator('[role="alertdialog"]');
      await alertDialog.waitFor({ state: 'visible', timeout: 5_000 }).catch(() => {});

      if (await alertDialog.isVisible()) {
        const confirmBtn = alertDialog.locator('[data-testid="confirmPickButton"]');
        await confirmBtn.click();
      }

      // Wait for the pick to be processed: player count should decrease
      // (avoids networkidle which never fires with active WebSocket)
      await expect.poll(
        () => dialog.locator('[data-testid="pickPlayerButton"]').count(),
        { timeout: 10_000 },
      ).toBeLessThan(playerCountBefore);

      picksMade++;
      if (picksMade % 4 === 0) {
        console.log(`Picks made: ${picksMade}/${totalPicks}`);
      }
    }

    console.log(`Total picks made: ${picksMade}`);
    expect(picksMade).toBeGreaterThan(0);

    // --- Step 4: Verify draft completed ---
    // After all picks, no more pick buttons should be available
    const remainingPicks = await dialog.locator('[data-testid="pickPlayerButton"]').count();
    expect(remainingPicks).toBe(0);

    console.log('Draft completed successfully!');
  });
});
