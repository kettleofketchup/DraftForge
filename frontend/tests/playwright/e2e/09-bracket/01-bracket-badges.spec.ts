/**
 * Bracket Badges Tests
 *
 * Tests the bracket badge display functionality for double elimination brackets.
 * Badges show loser paths (A, B, etc.) connecting winners bracket to losers bracket.
 *
 * Uses tournaments configured in the test database:
 * - 'completed_bracket': Tournament with all bracket games completed
 * - 'partial_bracket': Tournament with some games completed
 * - 'pending_bracket': Tournament with no games completed
 *
 * Ported from Cypress: frontend/tests/cypress/e2e/09-bracket/01-bracket-badges.cy.ts
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getTournamentByKey,
  TournamentPage,
} from '../../fixtures';

// Tournament PKs fetched in beforeAll
let completedBracketPk: number;
let partialBracketPk: number;
let pendingBracketPk: number;

// Skip: All tests require specific double elimination bracket structure with completed games
test.describe.skip('Bracket Badges (e2e)', () => {
  test.beforeAll(async ({ browser }) => {
    // Get tournament PKs by key (stable across populate changes)
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    const completedBracket = await getTournamentByKey(context, 'completed_bracket');
    const partialBracket = await getTournamentByKey(context, 'partial_bracket');
    const pendingBracket = await getTournamentByKey(context, 'pending_bracket');

    if (!completedBracket) {
      throw new Error('Could not find completed_bracket tournament');
    }
    if (!partialBracket) {
      throw new Error('Could not find partial_bracket tournament');
    }
    if (!pendingBracket) {
      throw new Error('Could not find pending_bracket tournament');
    }

    completedBracketPk = completedBracket.pk;
    partialBracketPk = partialBracket.pk;
    pendingBracketPk = pendingBracket.pk;

    await context.close();
  });

  test.beforeEach(async ({ loginStaff }) => {
    await loginStaff();
  });

  test('should display bracket with completed games', async ({ page }) => {
    // Completed Bracket Test has all 6 games completed
    await visitAndWaitForHydration(page, `/tournament/${completedBracketPk}/games`);

    // Wait for the games tab to load
    const bracketTab = page.locator('[data-testid="bracketTab"]');
    await expect(bracketTab).toBeVisible({ timeout: 10000 });

    // Default view should be bracket view
    await expect(page.locator('text=Bracket View')).toBeVisible();

    // Wait for bracket container to appear (bracket data loaded)
    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });
  });

  // Skip: Requires specific double elimination bracket structure with loser paths
  test.skip('should display bracket badges on winners bracket matches', async ({ page }) => {
    // Completed Bracket Test has completed bracket with badges
    await visitAndWaitForHydration(page, `/tournament/${completedBracketPk}/games`);

    // Wait for bracket to load
    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });

    // Winners bracket matches that have loser paths should have badges on the right
    // Badge A should appear on the first winners R1 match (position right)
    const badgeARight = page.locator('[data-testid="bracket-badge-A-right"]');
    await expect(badgeARight).toBeAttached({ timeout: 10000 });

    // Badge B should appear on the second winners R1 match
    const badgeBRight = page.locator('[data-testid="bracket-badge-B-right"]');
    await expect(badgeBRight).toBeAttached();
  });

  // Skip: Requires specific double elimination bracket structure with loser paths
  test.skip('should display corresponding badges on losers bracket slots', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${completedBracketPk}/games`);

    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });

    // Losers R1 match should have badges on the left indicating where teams came from
    // Badge A on top slot (radiant team)
    const badgeALeftTop = page.locator('[data-testid="bracket-badge-A-left-top"]');
    await expect(badgeALeftTop).toBeAttached({ timeout: 10000 });

    // Badge B on bottom slot (dire team)
    const badgeBLeftBottom = page.locator('[data-testid="bracket-badge-B-left-bottom"]');
    await expect(badgeBLeftBottom).toBeAttached();
  });

  // Skip: Requires specific double elimination bracket structure with loser paths
  test.skip('should show badge letters with distinct colors', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${completedBracketPk}/games`);

    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });

    // Verify badge A shows letter A (use first() since there may be multiple badges)
    const badgeLetterA = page.locator('[data-testid="bracket-badge-letter-A"]').first();
    await expect(badgeLetterA).toBeAttached();
    await expect(badgeLetterA).toContainText('A');

    // Verify badge B shows letter B (use first() since there may be multiple badges)
    const badgeLetterB = page.locator('[data-testid="bracket-badge-letter-B"]').first();
    await expect(badgeLetterB).toBeAttached();
    await expect(badgeLetterB).toContainText('B');
  });

  test('should show Winners Bracket label', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${completedBracketPk}/games`);

    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });

    // ReactFlow panel should show Winners Bracket label
    await expect(page.locator('text=Winners Bracket')).toBeVisible();
  });

  test('should show Losers Bracket divider', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${completedBracketPk}/games`);

    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });

    // Divider node should show Losers Bracket label
    await expect(page.locator('text=Losers Bracket')).toBeVisible();
  });

  test('should handle tournament with partial bracket', async ({ page }) => {
    // Partial Bracket Test has 2 games completed, 4 pending
    await visitAndWaitForHydration(page, `/tournament/${partialBracketPk}/games`);

    const bracketTab = page.locator('[data-testid="bracketTab"]');
    await expect(bracketTab).toBeVisible({ timeout: 10000 });

    // Should still show bracket container
    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });

    // Winners R1 badges should still be present (structure exists)
    const badgeARight = page.locator('[data-testid="bracket-badge-A-right"]');
    await expect(badgeARight).toBeAttached();
  });

  test('should handle tournament with no bracket games', async ({ page }) => {
    // Pending Bracket Test has 0 games completed
    await visitAndWaitForHydration(page, `/tournament/${pendingBracketPk}/games`);

    const bracketTab = page.locator('[data-testid="bracketTab"]');
    await expect(bracketTab).toBeVisible({ timeout: 10000 });

    // May show bracket container with pending games or empty state
    // The bracket structure should still exist
    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).toBeVisible({ timeout: 15000 });
  });

  test('can switch between bracket and list view', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${completedBracketPk}/games`);

    const bracketTab = page.locator('[data-testid="bracketTab"]');
    await expect(bracketTab).toBeVisible({ timeout: 10000 });

    // Click on List View tab
    await page.locator('text=List View').click();

    // Bracket container should not be visible in list view
    const bracketContainer = page.locator('[data-testid="bracketContainer"]');
    await expect(bracketContainer).not.toBeVisible();

    // Switch back to Bracket View
    await page.locator('text=Bracket View').click();

    // Bracket container should be visible again
    await expect(bracketContainer).toBeVisible({ timeout: 10000 });
  });
});
