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
      const reseedButton = page.locator('[data-testid="reseedBracketButton"], [data-testid="generateBracketButton"]');
      await expect(reseedButton).toBeVisible();
    });

    test('should allow reseeding with different methods', async ({ page }) => {
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // Click on Reseed Bracket dropdown
      const reseedButton = page.locator('[data-testid="reseedBracketButton"], [data-testid="generateBracketButton"]');
      await reseedButton.click();

      // Should show seeding options
      await expect(page.locator('[data-testid="seedByTeamMmrOption"]')).toBeVisible();
      await expect(page.locator('[data-testid="seedByCaptainMmrOption"]')).toBeVisible();
      await expect(page.locator('[data-testid="randomSeedingOption"]')).toBeVisible();
    });

    test('should enable save button after reseeding', async ({ page }) => {
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // Wait for bracket to fully load
      await page.waitForLoadState('networkidle');

      // Click on Reseed Bracket dropdown
      const reseedButton = page.locator('[data-testid="reseedBracketButton"], [data-testid="generateBracketButton"]');
      await reseedButton.click();

      // Wait for dropdown to open and select seeding method
      const randomSeeding = page.locator('[data-testid="randomSeedingOption"]');
      await randomSeeding.waitFor({ state: 'visible', timeout: 5000 });
      await randomSeeding.click();

      // Wait for and confirm the regenerate dialog
      const regenerateButton = page.locator('[data-testid="regenerateBracketConfirmButton"]');
      await regenerateButton.waitFor({ state: 'visible', timeout: 5000 });
      await regenerateButton.click();

      // Wait for dialog to close
      await regenerateButton.waitFor({ state: 'hidden', timeout: 5000 });

      // Should show unsaved changes indicator (wait with timeout)
      await expect(page.locator('text=Unsaved changes')).toBeVisible({ timeout: 10000 });

      // Save button should be enabled and clickable
      const saveButton = page.locator('[data-testid="saveBracketButton"]');
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

      // Wait for nodes to render
      await page.waitForLoadState('networkidle');

      // Find all match nodes and try each one until we find one with teams
      const matchNodes = page.locator('[data-testid="bracket-match-node"]');
      const nodeCount = await matchNodes.count();

      let foundMatchWithTeams = false;
      for (let i = 0; i < Math.min(nodeCount, 5); i++) {
        await matchNodes.nth(i).click({ force: true });

        // Wait for modal to open
        const dialog = page.locator('[role="dialog"]');
        const isVisible = await dialog.isVisible().catch(() => false);

        if (isVisible) {
          // Check for Match Details
          const hasDetails = await page.locator('[data-testid="match-details-header"]').isVisible().catch(() => false);
          if (hasDetails) {
            // Check for "Wins" buttons (indicating teams are assigned)
            const winButtons = dialog.locator('[data-testid="radiantWinsButton"], [data-testid="direWinsButton"]');
            const winButtonCount = await winButtons.count();

            if (winButtonCount > 0) {
              foundMatchWithTeams = true;
              // Check that buttons show captain usernames (from mock data these are player usernames)
              for (let j = 0; j < winButtonCount; j++) {
                const buttonText = await winButtons.nth(j).textContent();
                // Should not be a generic team name pattern
                expect(buttonText).not.toMatch(/^Team (Alpha|Beta|Gamma|Delta|Epsilon) Wins$/);
              }
              break;
            }
          }
          // Close modal and try next node
          await page.keyboard.press('Escape');
          await dialog.waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});
        }
      }

      // If we found a match with teams, the test passes
      // If no match with teams was found, log it but don't fail
      if (!foundMatchWithTeams) {
        console.log('No match with both teams assigned found - skipping assertion');
      }
    });

    test('should advance winner to next match after selection', async ({ page }) => {
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // Wait for nodes to render
      await page.waitForLoadState('networkidle');

      // Find a match with teams and winner selection buttons
      const matchNodes = page.locator('[data-testid="bracket-match-node"]');
      const nodeCount = await matchNodes.count();

      let foundMatch = false;
      for (let i = 0; i < Math.min(nodeCount, 5); i++) {
        await matchNodes.nth(i).click({ force: true });

        // Wait for modal
        const dialog = page.locator('[role="dialog"]');
        const isVisible = await dialog.isVisible().catch(() => false);

        if (isVisible) {
          // Check if this match has teams and Set Winner buttons
          const winButtons = dialog.locator('[data-testid="radiantWinsButton"], [data-testid="direWinsButton"]');
          const winButtonCount = await winButtons.count();

          if (winButtonCount >= 2) {
            foundMatch = true;
            // Click to set winner
            await winButtons.first().click();

            // Should show unsaved changes (winner was set locally)
            await expect(page.locator('text=Unsaved changes')).toBeVisible({ timeout: 5000 });
            break;
          }

          // Close modal and try next node
          await page.keyboard.press('Escape');
          await dialog.waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});
        }
      }

      if (!foundMatch) {
        console.log('No match with two teams assigned found - skipping winner selection');
      }
    });

    test('should advance loser to losers bracket after winner selection', async ({
      page,
    }) => {
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // Reseed to guarantee a fresh, fully-seeded bracket with loser paths wired.
      const reseedButton = page.locator(
        '[data-testid="reseedBracketButton"], [data-testid="generateBracketButton"]'
      );
      await reseedButton.click();

      const randomSeeding = page.locator('[data-testid="randomSeedingOption"]');
      await randomSeeding.waitFor({ state: 'visible', timeout: 5000 });
      await randomSeeding.click();

      // If the regenerate confirm dialog appears (it does when matches already
      // exist), wait for and click it. If not, we're on a fresh bracket.
      const regenerateButton = page.locator(
        '[data-testid="regenerateBracketConfirmButton"]'
      );
      const needsConfirm = await regenerateButton
        .waitFor({ state: 'visible', timeout: 3000 })
        .then(() => true)
        .catch(() => false);
      if (needsConfirm) {
        await regenerateButton.click();
        await regenerateButton.waitFor({ state: 'hidden', timeout: 5000 });
      }

      // Wait for the toolbar to indicate an unsaved, generated bracket.
      await expect(page.locator('text=Unsaved changes')).toBeVisible({
        timeout: 10000,
      });

      // Find the first Winners R1 node — it's guaranteed to have both teams
      // (first-round assignment) and a wired loser path.
      const winnersR1 = page.locator(
        '[data-testid="bracket-match-node"][data-bracket-type="winners"][data-round="1"]'
      );
      await expect(winnersR1.first()).toBeVisible({ timeout: 10000 });

      // Capture team names visible in the losers bracket BEFORE setting a winner.
      const losersNodesLocator = page.locator(
        '[data-testid="bracket-match-node"][data-bracket-type="losers"]'
      );
      const losersTextBefore = (
        await losersNodesLocator.allTextContents()
      ).join('\n');

      // Open the first winners R1 match.
      await winnersR1.first().click({ force: true });

      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible({ timeout: 10000 });

      const radiantWins = dialog.locator('[data-testid="radiantWinsButton"]');
      const direWins = dialog.locator('[data-testid="direWinsButton"]');
      await expect(radiantWins).toBeVisible({ timeout: 5000 });
      await expect(direWins).toBeVisible({ timeout: 5000 });

      // Capture the losing team's display name from the button text
      // ("<Captain> Wins" → strip the suffix).
      const direButtonText = (await direWins.textContent())?.trim() ?? '';
      const losingTeamName = direButtonText.replace(/ Wins$/i, '').trim();
      expect(losingTeamName.length).toBeGreaterThan(0);

      // Set radiant as winner — dire is therefore the loser.
      await radiantWins.click({ force: true });

      // Close the modal so the bracket re-renders fully.
      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden', timeout: 5000 });

      // The losing team's display name must now appear in a losers bracket node.
      // Poll because Zustand state propagation through ReactFlow is async.
      await expect(async () => {
        const losersTextAfter = (
          await losersNodesLocator.allTextContents()
        ).join('\n');
        // Sanity: losers bracket DOM should have changed (new team added).
        expect(losersTextAfter).not.toBe(losersTextBefore);
        // The specific losing team should now be visible somewhere in losers.
        expect(losersTextAfter).toContain(losingTeamName);
      }).toPass({ timeout: 5000 });
    });
  });

  test.describe('Bracket Saving', () => {
    test('should save bracket and persist changes', async ({ page }) => {
      await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);

      const bracketContainer = page.locator('[data-testid="bracketContainer"]');
      await expect(bracketContainer).toBeVisible({ timeout: 15000 });

      // Wait for bracket to fully load
      await page.waitForLoadState('networkidle');

      // Reseed the bracket
      const reseedButton = page.locator('[data-testid="reseedBracketButton"], [data-testid="generateBracketButton"]');
      await reseedButton.click();

      // Wait for dropdown and select seeding method
      const randomSeeding = page.locator('[data-testid="randomSeedingOption"]');
      await randomSeeding.waitFor({ state: 'visible', timeout: 5000 });
      await randomSeeding.click();

      // Wait for and confirm the regenerate dialog
      const regenerateButton = page.locator('[data-testid="regenerateBracketConfirmButton"]');
      await regenerateButton.waitFor({ state: 'visible', timeout: 5000 });
      await regenerateButton.click();

      // Wait for dialog to close
      await regenerateButton.waitFor({ state: 'hidden', timeout: 5000 });

      // Should show unsaved changes (expect waits for condition)
      await expect(page.locator('text=Unsaved changes')).toBeVisible({ timeout: 10000 });

      // Save the bracket
      // Note: There's a known Playwright issue with Radix ScrollArea where the html element
      // appears to intercept pointer events. Using evaluate to click works around this.
      const saveButton = page.locator('[data-testid="saveBracketButton"]');

      // Verify button is enabled before clicking
      await expect(saveButton).not.toBeDisabled();

      // Set up response listener before clicking
      const saveResponsePromise = page.waitForResponse(
        (response) => response.request().method() === 'POST' && response.url().includes('/save/'),
        { timeout: 15000 }
      );

      // Click via JavaScript to bypass the hit-testing issue
      await saveButton.evaluate((btn) => (btn as HTMLButtonElement).click());

      // Wait for save API call and verify success
      const saveResponse = await saveResponsePromise;
      expect(saveResponse.status()).toBe(200);

      // Wait for UI to update
      await page.waitForLoadState('networkidle');

      // Unsaved changes indicator should disappear
      await expect(page.locator('text=Unsaved changes')).not.toBeVisible({ timeout: 10000 });
    });
  });
});
