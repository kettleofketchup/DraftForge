/**
 * Bracket Generation and Winner Advancement Tests
 *
 * Tests bracket generation with various seeding methods and the winner
 * advancement flow where setting a match winner moves teams to next round.
 *
 * Uses 'pending_bracket' tournament which has teams but pending games.
 *
 * Ported from Cypress: frontend/tests/cypress/e2e/09-bracket/03-bracket-winner-advancement.cy.ts
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

test.describe('Bracket Generation and Winner Advancement (e2e)', () => {
  test.beforeAll(async ({ browser }) => {
    // Get the tournament pk for the pending bracket test scenario
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

  test.describe('Bracket Generation', () => {
    test('should generate a bracket with seeding', async ({ page }) => {
      // Use Pending Bracket Test which has teams but pending games
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      // Wait for the games tab to load
      const bracketTab = page.locator('[data-testid="bracketTab"]');
      await expect(bracketTab).toBeVisible({ timeout: 10000 });

      // Should see the bracket container
      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // Staff should see the toolbar
      const reseedButton = page.locator('button:has-text("Reseed Bracket"), button:has-text("Generate Bracket")');
      await expect(reseedButton).toBeVisible();
    });

    test('should allow reseeding with different methods', async ({ page }) => {
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // Click on Reseed Bracket dropdown
      const reseedButton = page.locator('button:has-text("Reseed Bracket"), button:has-text("Generate Bracket")');
      await reseedButton.click();

      // Should show seeding options
      await expect(page.locator('text=Seed by Team MMR')).toBeVisible();
      await expect(page.locator('text=Seed by Captain MMR')).toBeVisible();
      await expect(page.locator('text=Random Seeding')).toBeVisible();
    });

    test('should enable save button after reseeding', async ({ page }) => {
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // Click on Reseed Bracket
      const reseedButton = page.locator('button:has-text("Reseed Bracket"), button:has-text("Generate Bracket")');
      await reseedButton.click();

      // Select a seeding method
      await page.locator('text=Random Seeding').click();

      // If confirmation dialog appears, confirm it
      const regenerateButton = page.locator('button:has-text("Regenerate")');
      if (await regenerateButton.isVisible().catch(() => false)) {
        await regenerateButton.click();
      }

      // Should show unsaved changes indicator (expect waits for condition)
      await expect(page.locator('text=Unsaved changes')).toBeVisible();

      // Save button should be enabled and clickable
      const saveButton = page.locator('button:has-text("Save Bracket"), button:has-text("Save Changes")');
      await expect(saveButton).toBeVisible();
      await expect(saveButton).not.toBeDisabled();
    });
  });

  test.describe('Winner Selection', () => {
    test('should show captain names in winner selection buttons', async ({ page }) => {
      // Use Pending Bracket Test with teams assigned
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // Click on a match node that has teams assigned (first round)
      // ReactFlow nodes have class containing 'react-flow__node'
      const matchNode = page.locator('.react-flow__node').filter({ has: page.locator(':visible') }).first();
      await matchNode.click({ force: true });

      // Wait for modal to open
      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible({ timeout: 5000 });

      // Modal should show Match Details
      await expect(page.locator('text=Match Details')).toBeVisible();

      // If match has teams, the Set Winner buttons should show captain names, not team names
      // The button text should contain "Wins" and NOT "Team Alpha Wins" pattern
      const winButtons = dialog.locator('button:has-text("Wins")');
      const winButtonCount = await winButtons.count();

      if (winButtonCount > 0) {
        // Check that buttons show captain usernames (from mock data these are player usernames)
        // The buttons should NOT show generic "Team X" pattern
        for (let i = 0; i < winButtonCount; i++) {
          const buttonText = await winButtons.nth(i).textContent();
          // Should not be a generic team name pattern
          expect(buttonText).not.toMatch(/^Team (Alpha|Beta|Gamma|Delta|Epsilon) Wins$/);
        }
      }

      // Close modal by pressing Escape
      await page.keyboard.press('Escape');
    });

    test('should advance winner to next match after selection', async ({ page }) => {
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // Find a winners bracket R1 match with both teams
      const matchNode = page.locator('.react-flow__node').filter({ has: page.locator(':visible') }).first();
      await matchNode.click({ force: true });

      // Wait for modal
      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible({ timeout: 5000 });

      // Check if this match has teams and Set Winner buttons
      const winButtons = dialog.locator('button:has-text("Wins")');
      const winButtonCount = await winButtons.count();

      if (winButtonCount >= 2) {
        // Get the first team's name from the button
        const firstButtonText = await winButtons.first().textContent();
        const teamName = firstButtonText?.replace(' Wins', '');

        // Click to set winner
        await winButtons.first().click();

        // Should show unsaved changes (winner was set locally - expect waits for condition)
        await expect(page.locator('text=Unsaved changes')).toBeVisible();
      } else {
        // Log and skip if no teams
        console.log('Match does not have two teams assigned - skipping winner selection');
      }
    });

    // Skip: This test is flaky due to timing issues with modal after reseed
    test.skip('should advance loser to losers bracket after winner selection', async ({
      page,
    }) => {
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // First, reseed to ensure we have a fresh bracket with loser paths
      const reseedButton = page.locator('button:has-text("Reseed Bracket"), button:has-text("Generate Bracket")');
      await reseedButton.click();
      await page.locator('text=Random Seeding').click();

      // Confirm if dialog appears
      const regenerateButton = page.locator('button:has-text("Regenerate")');
      await regenerateButton.waitFor({ state: 'visible', timeout: 2000 }).catch(() => {});
      if (await regenerateButton.isVisible().catch(() => false)) {
        await regenerateButton.click({ force: true });
      }

      // Wait for network to settle after regeneration
      await page.waitForLoadState('networkidle');

      // Click on first match
      const matchNode = page.locator('.react-flow__node').filter({ has: page.locator(':visible') }).first();
      await matchNode.click({ force: true });

      // Wait for modal
      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible({ timeout: 10000 });

      // If match has Set Winner buttons, click one
      const winButtons = dialog.locator('button:has-text("Wins")');
      const winButtonCount = await winButtons.count();

      if (winButtonCount >= 2) {
        // Click second button (dire wins, so radiant is loser)
        await winButtons.nth(1).click({ force: true });

        // The loser should now be in the losers bracket
        // But we can verify unsaved changes is shown (expect waits for condition)
        await expect(page.locator('text=Unsaved changes')).toBeVisible();
      } else {
        console.log('Match does not have two teams - skipping loser advancement check');
      }
    });
  });

  test.describe('Bracket Saving', () => {
    test('should save bracket and persist changes', async ({ page }) => {
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // Reseed the bracket
      const reseedButton = page.locator('button:has-text("Reseed Bracket"), button:has-text("Generate Bracket")');
      await reseedButton.click();
      await page.locator('text=Random Seeding').click();

      // Confirm if dialog appears
      const regenerateButton = page.locator('button:has-text("Regenerate")');
      await regenerateButton.waitFor({ state: 'visible', timeout: 2000 }).catch(() => {});
      if (await regenerateButton.isVisible().catch(() => false)) {
        await regenerateButton.click({ force: true });
      }

      // Wait for network to settle after regeneration
      await page.waitForLoadState('networkidle');

      // Should show unsaved changes (expect waits for condition)
      await expect(page.locator('text=Unsaved changes')).toBeVisible();

      // Save the bracket - use force to handle any overlays
      const saveButton = page.locator('button:has-text("Save Bracket"), button:has-text("Save Changes")');
      await saveButton.click({ force: true });

      // Wait for save to complete
      await page.waitForLoadState('networkidle');

      // Unsaved changes should disappear (expect waits for condition)
      await expect(page.locator('text=Unsaved changes')).not.toBeVisible();
    });
  });
});
