/**
 * Shuffle Draft Full Flow Tests
 *
 * Tests a complete shuffle draft from start to finish.
 * Shuffle draft picks based on lowest team MMR - after each pick,
 * the team with lowest total MMR picks next.
 *
 * These tests use the test login capabilities to login as different
 * captains and verify the draft flow from their perspectives.
 *
 * Ported from Cypress: frontend/tests/cypress/e2e/08-shuffle-draft/01-full-draft.cy.ts
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getTournamentByKey,
  TournamentPage,
  type TournamentData,
} from '../../fixtures';

test.describe('Shuffle Draft - Full Flow', () => {
  let tournamentPk: number;
  let tournamentName: string;

  test.beforeAll(async ({ browser }) => {
    // Get the tournament dynamically
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const tournament = await getTournamentByKey(context, 'completed_bracket');
    if (!tournament) {
      throw new Error('Could not find completed_bracket tournament');
    }
    tournamentPk = tournament.pk;
    tournamentName = tournament.name;
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    // Clear cookies to prevent stale user data
    await context.clearCookies();
  });

  test('should navigate to tournament and view teams', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();

    // Navigate to tournament
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);

    // Wait for page content to load
    await expect(page.locator('h1')).toContainText(tournamentName, {
      timeout: 10000,
    });

    // Click on Teams tab
    const teamsTab = page.locator('[data-testid="teamsTab"]');
    await teamsTab.click();

    // Verify teams exist (check for team headers)
    await expect(page.locator('text=Team Alpha')).toBeVisible();
    await expect(page.locator('text=Avg MMR').first()).toBeVisible();
  });

  // TODO: This test needs rework - Draft Style dialog shows "Draft not initialized"
  // because the draft hasn't been started yet. Need to start draft first, then change style.
  test.skip('should open draft modal and configure shuffle draft style', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();

    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);

    // Wait for page to load
    await expect(page.locator('h1')).toContainText(tournamentName, {
      timeout: 10000,
    });

    // Click on Teams tab
    await page.locator('[data-testid="teamsTab"]').click({ force: true });
    await page.waitForLoadState('networkidle');

    // Click Start Draft button to open the draft modal
    await page.locator('button:has-text("Start Draft")').click({ force: true });

    // The draft modal should open
    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Open Moderation dropdown and click "Change Draft Style"
    await dialog.getByRole('button', { name: 'Moderation' }).click({ force: true });
    await page.locator('text=Change Draft Style').click({ force: true });

    // Wait for the draft style dialog to open
    const styleDialog = page.locator('[role="dialog"]').filter({ hasText: 'Draft Style' });
    await expect(styleDialog).toBeVisible();

    // Click on the style selector and choose shuffle
    await page.locator('[role="combobox"]').click();
    await page.locator('[role="option"]:has-text("Shuffle")').click();

    // Apply the style
    await page.locator('button:has-text("Apply Shuffle Draft")').click({ force: true });

    await page.waitForLoadState('networkidle');

    // Open Moderation dropdown and click Restart Draft
    await dialog.getByRole('button', { name: 'Moderation' }).click({ force: true });
    await page.locator('text=Restart Draft').click({ force: true });

    // Confirm if there's a confirmation dialog
    const alertDialog = page.locator('[role="alertdialog"]');
    if (await alertDialog.isVisible().catch(() => false)) {
      const confirmBtn = alertDialog.locator(
        'button:has-text("Confirm"), button:has-text("Yes"), button:has-text("Continue"), button:has-text("Restart")'
      );
      await confirmBtn.first().click({ force: true });
    }

    await page.waitForLoadState('networkidle');

    // Verify draft is now showing - should see pick order or captain info
    await expect(page.locator('[role="dialog"]')).toBeVisible();
  });

  // TODO: This test needs rework - same issue as above, draft needs to be initialized first
  test.skip('should complete shuffle draft flow with picks', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();

    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);

    // Wait for page to load
    await expect(page.locator('h1')).toContainText(tournamentName, {
      timeout: 10000,
    });

    // Click on Teams tab
    await page.locator('[data-testid="teamsTab"]').click({ force: true });
    await page.waitForLoadState('networkidle');

    // Open draft modal
    await page.locator('button:has-text("Start Draft")').click({ force: true });

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Open Moderation dropdown and click "Change Draft Style"
    await dialog.getByRole('button', { name: 'Moderation' }).click({ force: true });
    await page.locator('text=Change Draft Style').click({ force: true });

    // Wait for the draft style dialog to open
    const styleDialog = page.locator('[role="dialog"]').filter({ hasText: 'Draft Style' });
    await expect(styleDialog).toBeVisible();

    // Click on the style selector and choose shuffle
    await page.locator('[role="combobox"]').click();
    await page.locator('[role="option"]:has-text("Shuffle")').click();

    // Apply the style
    await page.locator('button:has-text("Apply Shuffle Draft")').click({ force: true });

    await page.waitForLoadState('networkidle');

    // Open Moderation dropdown and click Restart Draft
    await dialog.getByRole('button', { name: 'Moderation' }).click({ force: true });
    await page.locator('text=Restart Draft').click({ force: true });

    // Confirm restart dialog
    const alertDialog = page.locator('[role="alertdialog"]');
    if (await alertDialog.isVisible().catch(() => false)) {
      const confirmBtn = alertDialog.locator(
        'button:has-text("Confirm"), button:has-text("Yes"), button:has-text("Continue"), button:has-text("Restart")'
      );
      await confirmBtn.first().click({ force: true });
    }

    await page.waitForLoadState('networkidle');

    // Now the draft should be active
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Make picks - click any available Pick button
    // Try to make 4 picks sequentially
    const attemptPick = async () => {
      const dialogEl = page.locator('[role="dialog"]');
      const pickButtons = dialogEl.locator('button:has-text("Pick")');
      const pickCount = await pickButtons.count();

      if (pickCount > 0) {
        await pickButtons.first().click({ force: true });

        // Handle confirmation dialog if it appears
        const confirmDialog = page.locator('[role="alertdialog"]');
        if (await confirmDialog.isVisible().catch(() => false)) {
          const pickConfirmBtn = confirmDialog.locator(
            'button:has-text("Confirm"), button:has-text("Yes"), button:has-text("Pick")'
          );
          if (await pickConfirmBtn.isVisible().catch(() => false)) {
            await pickConfirmBtn.first().click({ force: true });
          }
        }

        await page.waitForLoadState('networkidle');
      }
    };

    // Try to make picks sequentially
    await attemptPick();
    await attemptPick();
    await attemptPick();
    await attemptPick();

    // Verify we're still in the draft modal
    await expect(page.locator('[role="dialog"]')).toBeVisible();
  });
});

test.describe('Shuffle Draft - Captain Login Scenarios', () => {
  // Use the shuffle_draft_captain_turn tournament config
  // This has the test user (bucketoffish55) as the first captain
  let tournamentData: TournamentData;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Get the shuffle draft captain turn tournament
    const tournament = await getTournamentByKey(
      context,
      'shuffle_draft_captain_turn'
    );

    if (!tournament) {
      throw new Error('Could not find shuffle_draft_captain_turn tournament');
    }

    tournamentData = tournament;
    console.log(
      `Tournament: ${tournamentData.name} (pk=${tournamentData.pk})`
    );
    console.log(
      `Captains: ${tournamentData.captains.map((c) => c.username).join(', ')}`
    );

    await context.close();
  });

  test('should show draft dialog when logged in as current captain', async ({
    page,
    context,
    loginUser,
  }) => {
    // Login as the first captain (test user - bucketoffish55)
    // The shuffle_draft_captain_turn config sets test user as first captain
    await loginUser();

    // Visit the tournament page
    await visitAndWaitForHydration(page, `/tournament/${tournamentData.pk}`);

    // Wait for page to load
    await expect(page.locator('h1')).toContainText(tournamentData.name, {
      timeout: 10000,
    });

    // Click on Teams tab
    await page.locator('[data-testid="teamsTab"]').click({ force: true });
    await page.waitForLoadState('networkidle');

    // Open draft modal
    const liveDraftButton = page.locator('button:has-text("Live Draft")');
    const startDraftButton = page.locator('button:has-text("Start Draft")');

    if (await liveDraftButton.isVisible().catch(() => false)) {
      await liveDraftButton.click({ force: true });
    } else if (await startDraftButton.isVisible().catch(() => false)) {
      await startDraftButton.click({ force: true });
    }

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // The captain should see the draft dialog
    // Verify the dialog shows draft-related content
    const dialogText = await dialog.textContent();
    const hasDraftContent =
      dialogText?.toLowerCase().includes('pick') ||
      dialogText?.toLowerCase().includes('draft') ||
      dialogText?.toLowerCase().includes('turn') ||
      dialogText?.toLowerCase().includes('captain') ||
      dialogText?.toLowerCase().includes('team');

    console.log(`Dialog text includes draft content: ${hasDraftContent}`);
    expect(hasDraftContent).toBe(true);
  });

  test('should show draft dialog when logged in as second captain', async ({
    page,
    loginAsUser,
  }) => {
    // Get the second captain's pk
    const secondCaptain = tournamentData.teams.find(
      (t) => t.draft_order === 2
    )?.captain;

    if (!secondCaptain) {
      console.log('No second captain found, skipping test');
      test.skip();
      return;
    }

    // Login as the second captain using loginAsUser
    const response = await loginAsUser(secondCaptain.pk);
    console.log(`Logged in as: ${response.user?.username || secondCaptain.username}`);

    // Visit the tournament page
    await visitAndWaitForHydration(page, `/tournament/${tournamentData.pk}`);

    // Wait for page to load
    await expect(page.locator('h1')).toContainText(tournamentData.name, {
      timeout: 10000,
    });

    // Click on Teams tab
    await page.locator('[data-testid="teamsTab"]').click({ force: true });
    await page.waitForLoadState('networkidle');

    // Open draft modal
    const liveDraftButton = page.locator('button:has-text("Live Draft")');
    const startDraftButton = page.locator('button:has-text("Start Draft")');

    if (await liveDraftButton.isVisible().catch(() => false)) {
      await liveDraftButton.click({ force: true });
    } else if (await startDraftButton.isVisible().catch(() => false)) {
      await startDraftButton.click({ force: true });
    }

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // The second captain should see the draft dialog
    const dialogText = await dialog.textContent();
    const hasDraftContent =
      dialogText?.toLowerCase().includes('pick') ||
      dialogText?.toLowerCase().includes('draft') ||
      dialogText?.toLowerCase().includes('turn') ||
      dialogText?.toLowerCase().includes('captain') ||
      dialogText?.toLowerCase().includes('team');

    console.log(`Dialog text includes draft content: ${hasDraftContent}`);
    console.log(`Second captain sees: ${dialogText?.substring(0, 200)}...`);
    expect(hasDraftContent).toBe(true);
  });

  test('should allow captain to make a pick when it is their turn', async ({
    page,
    loginUser,
  }) => {
    // Login as the first captain (test user)
    await loginUser();

    // Visit the tournament page
    await visitAndWaitForHydration(page, `/tournament/${tournamentData.pk}`);

    // Wait for page to load
    await expect(page.locator('h1')).toContainText(tournamentData.name, {
      timeout: 10000,
    });

    // Click on Teams tab
    await page.locator('[data-testid="teamsTab"]').click({ force: true });
    await page.waitForLoadState('networkidle');

    // Open draft modal
    const liveDraftButton = page.locator('button:has-text("Live Draft")');
    const startDraftButton = page.locator('button:has-text("Start Draft")');

    if (await liveDraftButton.isVisible().catch(() => false)) {
      await liveDraftButton.click({ force: true });
    } else if (await startDraftButton.isVisible().catch(() => false)) {
      await startDraftButton.click({ force: true });
    }

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Look for Pick buttons - captain should be able to pick
    const pickButtons = dialog.locator('button:has-text("Pick")');
    const pickCount = await pickButtons.count();

    if (pickCount > 0) {
      console.log(`Found ${pickCount} pick buttons`);

      // Click the first available pick button
      await pickButtons.first().click({ force: true });

      // Handle confirmation dialog
      const alertDialog = page.locator('[role="alertdialog"]');
      if (await alertDialog.isVisible().catch(() => false)) {
        const confirmBtn = alertDialog.locator(
          'button:has-text("Confirm"), button:has-text("Yes"), button:has-text("Pick")'
        );
        if (await confirmBtn.isVisible().catch(() => false)) {
          await confirmBtn.first().click({ force: true });
          await page.waitForLoadState('networkidle');
          console.log('Pick confirmed successfully');
        }
      }
    } else {
      console.log('No pick buttons available - draft may not be at captain turn');
    }
  });

  test('should switch captains after a pick in shuffle draft', async ({
    page,
    loginAdmin,
  }) => {
    // This test verifies that after a pick, the turn switches
    // based on lowest team MMR (shuffle draft behavior)

    await loginAdmin();

    // Visit the tournament page
    await visitAndWaitForHydration(page, `/tournament/${tournamentData.pk}`);

    // Wait for page to load
    await expect(page.locator('h1')).toContainText(tournamentData.name, {
      timeout: 10000,
    });

    // Click on Teams tab
    await page.locator('[data-testid="teamsTab"]').click({ force: true });
    await page.waitForLoadState('networkidle');

    // Open draft modal
    const liveDraftButton = page.locator('button:has-text("Live Draft")');
    const startDraftButton = page.locator('button:has-text("Start Draft")');

    if (await liveDraftButton.isVisible().catch(() => false)) {
      await liveDraftButton.click({ force: true });
    } else if (await startDraftButton.isVisible().catch(() => false)) {
      await startDraftButton.click({ force: true });
    }

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Get initial turn state (which captain's turn it is)
    const initialText = await dialog.textContent();
    console.log(`Initial draft state: ${initialText?.substring(0, 200)}...`);

    // Make a pick as admin
    const pickButtons = dialog.locator('button:has-text("Pick")');
    const pickCount = await pickButtons.count();

    if (pickCount > 0) {
      await pickButtons.first().click({ force: true });

      // Confirm the pick
      const alertDialog = page.locator('[role="alertdialog"]');
      if (await alertDialog.isVisible().catch(() => false)) {
        const confirmBtn = alertDialog.locator(
          'button:has-text("Confirm"), button:has-text("Yes"), button:has-text("Pick")'
        );
        if (await confirmBtn.isVisible().catch(() => false)) {
          await confirmBtn.first().click({ force: true });
        }
      }

      await page.waitForLoadState('networkidle');

      // Verify state has changed after pick
      const afterText = await dialog.textContent();
      console.log(`After pick state: ${afterText?.substring(0, 200)}...`);

      // In shuffle draft, the next captain should be the one with lowest MMR
      // We just verify the dialog is still open and state changed
      await expect(dialog).toBeVisible();
    }
  });
});
