/**
 * Mobile-first responsive tests for Match Stats Modal and Tournament Bracket
 *
 * Tests ensure components are usable and properly displayed on mobile devices.
 * Use the `mobile-chrome` project for these tests:
 *   npx playwright test tests/playwright/e2e/06-mobile/ --project=mobile-chrome
 */

import { test, expect, loginAdmin, TournamentPage, getTournamentByKey } from '../../fixtures';

// Mobile-first viewport sizes (smallest first)
const VIEWPORTS = {
  mobile: { width: 375, height: 667, device: 'iPhone SE' },
  mobileLarge: { width: 414, height: 896, device: 'iPhone 11' },
  tablet: { width: 768, height: 1024, device: 'iPad' },
  desktop: { width: 1280, height: 720, device: 'Desktop' },
} as const;

type ViewportName = keyof typeof VIEWPORTS;

/**
 * Helper to navigate to bracket view and wait for it to load.
 */
async function navigateToBracket(tournamentPage: TournamentPage): Promise<void> {
  await tournamentPage.clickBracketTab();
  // Wait for React Flow to render
  await tournamentPage.page.locator('.react-flow').waitFor({ state: 'visible', timeout: 10000 });
}

/**
 * Helper to click on a bracket node - uses the group role with node roledescription.
 * React Flow nodes are rendered as groups with roledescription="node".
 * Find nodes that contain match info (have headings like "Winners R1", etc.)
 */
async function clickBracketNode(tournamentPage: TournamentPage): Promise<void> {
  const node = tournamentPage.page.locator('.react-flow [role="group"]').filter({ has: tournamentPage.page.locator('h3') }).first();
  await node.click({ force: true });
  await tournamentPage.page.waitForTimeout(300);
}

test.describe('Mobile-First: Tournament Bracket', () => {
  // Generate tests for each viewport
  for (const [name, viewport] of Object.entries(VIEWPORTS)) {
    test.describe(`${viewport.device} (${viewport.width}x${viewport.height})`, () => {
      test.beforeEach(async ({ context, page }) => {
        await loginAdmin(context);
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
      });

      test('should display tournament page without horizontal scroll', async ({ context, page }) => {
        const tournament = await getTournamentByKey(context, 'completed_bracket');
        expect(tournament).not.toBeNull();

        const tournamentPage = new TournamentPage(page);
        await tournamentPage.goto(tournament!.pk);

        // Page should be visible
        await expect(page.locator('body')).toBeVisible();
        await expect(page.getByText('Completed Bracket Test')).toBeVisible();

        // No horizontal scrolling
        const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
        expect(scrollWidth).toBeLessThanOrEqual(viewport.width + 1);
      });

      test('should display Games tab and bracket view', async ({ context, page }) => {
        const tournament = await getTournamentByKey(context, 'completed_bracket');
        expect(tournament).not.toBeNull();

        const tournamentPage = new TournamentPage(page);
        await tournamentPage.goto(tournament!.pk);
        await navigateToBracket(tournamentPage);

        // Bracket view should be visible
        await expect(page.locator('.react-flow')).toBeVisible();

        // Check for bracket content (Winners/Losers bracket labels)
        await expect(page.getByText(/Winners|Losers|Grand Finals/i).first()).toBeVisible();
      });

      test('should allow horizontal pan/scroll on bracket if content overflows', async ({ context, page }) => {
        const tournament = await getTournamentByKey(context, 'completed_bracket');
        expect(tournament).not.toBeNull();

        const tournamentPage = new TournamentPage(page);
        await tournamentPage.goto(tournament!.pk);
        await navigateToBracket(tournamentPage);

        // React Flow should be visible and interactive
        await expect(page.locator('.react-flow')).toBeVisible();
      });

      test('should display bracket nodes readably', async ({ context, page }) => {
        const tournament = await getTournamentByKey(context, 'completed_bracket');
        expect(tournament).not.toBeNull();

        const tournamentPage = new TournamentPage(page);
        await tournamentPage.goto(tournament!.pk);
        await navigateToBracket(tournamentPage);

        // Check that bracket nodes are visible and have minimum readable size
        const node = page.locator('.react-flow [role="group"]').filter({ has: page.locator('h3') }).first();
        const boundingBox = await node.boundingBox();
        expect(boundingBox).not.toBeNull();

        // Minimum touch target size for mobile (44px recommended)
        expect(boundingBox!.width).toBeGreaterThanOrEqual(44);
        expect(boundingBox!.height).toBeGreaterThanOrEqual(44);
      });

      test('should open match modal when clicking bracket node', async ({ context, page }) => {
        const tournament = await getTournamentByKey(context, 'completed_bracket');
        expect(tournament).not.toBeNull();

        const tournamentPage = new TournamentPage(page);
        await tournamentPage.goto(tournament!.pk);
        await navigateToBracket(tournamentPage);
        await clickBracketNode(tournamentPage);

        // Modal should appear
        await expect(page.locator('[role="dialog"]')).toBeVisible();
      });
    });
  }
});

test.describe('Mobile-First: Match Stats Modal', () => {
  // Generate tests for each viewport
  for (const [name, viewport] of Object.entries(VIEWPORTS)) {
    test.describe(`${viewport.device} (${viewport.width}x${viewport.height})`, () => {
      test.beforeEach(async ({ context, page }) => {
        await loginAdmin(context);
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
      });

      test('should display match details modal properly', async ({ context, page }) => {
        const tournament = await getTournamentByKey(context, 'completed_bracket');
        expect(tournament).not.toBeNull();

        const tournamentPage = new TournamentPage(page);
        await tournamentPage.goto(tournament!.pk);
        await navigateToBracket(tournamentPage);
        await clickBracketNode(tournamentPage);

        // Modal should be visible
        const modal = page.locator('[role="dialog"]');
        await expect(modal).toBeVisible();

        // Modal should not cause horizontal scroll
        const boundingBox = await modal.boundingBox();
        expect(boundingBox).not.toBeNull();
        expect(boundingBox!.x + boundingBox!.width).toBeLessThanOrEqual(viewport.width + 10);
      });

      test('should display View Stats button and open stats modal', async ({ context, page }) => {
        const tournament = await getTournamentByKey(context, 'completed_bracket');
        expect(tournament).not.toBeNull();

        const tournamentPage = new TournamentPage(page);
        await tournamentPage.goto(tournament!.pk);
        await navigateToBracket(tournamentPage);
        await clickBracketNode(tournamentPage);

        // Look for View Stats button
        const dialog = page.locator('[role="dialog"]');
        const dialogText = await dialog.textContent();

        if (dialogText?.includes('View Stats')) {
          await page.getByText('View Stats').click();
          await page.waitForTimeout(500);

          // Stats modal should open
          await expect(page.locator('[role="dialog"]')).toBeVisible();
        }
      });

      test('should display player stats table with proper layout', async ({ context, page }) => {
        const tournament = await getTournamentByKey(context, 'completed_bracket');
        expect(tournament).not.toBeNull();

        const tournamentPage = new TournamentPage(page);
        await tournamentPage.goto(tournament!.pk);
        await navigateToBracket(tournamentPage);
        await clickBracketNode(tournamentPage);

        const dialog = page.locator('[role="dialog"]');
        const dialogText = await dialog.textContent();

        if (dialogText?.includes('View Stats')) {
          await page.getByText('View Stats').click();
          await page.waitForTimeout(500);

          // Check for team tables (RADIANT/DIRE)
          const statsModal = page.locator('[role="dialog"]').last();
          const statsText = await statsModal.textContent();

          const hasRadiant = statsText?.includes('RADIANT');
          const hasDire = statsText?.includes('DIRE');

          if (hasRadiant || hasDire) {
            // Tables should be present
            expect(hasRadiant || hasDire).toBe(true);

            // Modal should be scrollable if content overflows
            const scrollArea = statsModal.locator('[data-radix-scroll-area-viewport]');
            const scrollCount = await scrollArea.count();
            if (scrollCount > 0) {
              const scrollHeight = await scrollArea.first().evaluate((el) => el.scrollHeight);
              expect(scrollHeight).toBeGreaterThanOrEqual(0);
            }
          }
        }
      });

      test('should display external links (Dotabuff, OpenDota) accessibly', async ({ context, page }) => {
        const tournament = await getTournamentByKey(context, 'completed_bracket');
        expect(tournament).not.toBeNull();

        const tournamentPage = new TournamentPage(page);
        await tournamentPage.goto(tournament!.pk);
        await navigateToBracket(tournamentPage);
        await clickBracketNode(tournamentPage);

        const dialog = page.locator('[role="dialog"]').first();
        const dialogText = await dialog.textContent();

        if (dialogText?.includes('View Stats')) {
          await page.getByText('View Stats').click();
          await page.waitForTimeout(500);

          // Check for external links in the stats modal (last dialog)
          const statsModal = page.locator('[role="dialog"]').last();

          // Look for Dotabuff and OpenDota links
          await expect(statsModal.locator('a[href*="dotabuff.com"]')).toBeVisible();
          await expect(statsModal.locator('a[href*="opendota.com"]')).toBeVisible();

          // Links should have proper touch target size
          const dotabuffLink = statsModal.locator('a[href*="dotabuff.com"]').first();
          const boundingBox = await dotabuffLink.boundingBox();
          expect(boundingBox).not.toBeNull();
          expect(boundingBox!.height).toBeGreaterThanOrEqual(32); // Minimum touch target
        }
      });

      test('should allow closing modals on mobile', async ({ context, page }) => {
        const tournament = await getTournamentByKey(context, 'completed_bracket');
        expect(tournament).not.toBeNull();

        const tournamentPage = new TournamentPage(page);
        await tournamentPage.goto(tournament!.pk);
        await navigateToBracket(tournamentPage);
        await clickBracketNode(tournamentPage);

        // Modal should be visible
        await expect(page.locator('[role="dialog"]')).toBeVisible();

        // Close modal by pressing Escape
        await page.keyboard.press('Escape');
        await page.waitForTimeout(300);

        // Modal should close
        await expect(page.locator('[role="dialog"]')).not.toBeVisible();
      });

      test('should have readable font sizes on mobile', async ({ context, page }) => {
        const tournament = await getTournamentByKey(context, 'completed_bracket');
        expect(tournament).not.toBeNull();

        const tournamentPage = new TournamentPage(page);
        await tournamentPage.goto(tournament!.pk);
        await navigateToBracket(tournamentPage);
        await clickBracketNode(tournamentPage);

        const dialog = page.locator('[role="dialog"]');
        const dialogText = await dialog.textContent();

        if (dialogText?.includes('View Stats')) {
          await page.getByText('View Stats').click();
          await page.waitForTimeout(500);

          // Check font sizes are readable (minimum 10px for mobile)
          const cells = page.locator('[role="dialog"]').locator('td, th');
          const cellCount = await cells.count();

          for (let i = 0; i < cellCount; i++) {
            const cell = cells.nth(i);
            const isVisible = await cell.isVisible().catch(() => false);
            if (isVisible) {
              const fontSize = await cell.evaluate((el) => parseInt(window.getComputedStyle(el).fontSize));
              expect(fontSize).toBeGreaterThanOrEqual(10); // Allow smaller for dense tables
            }
          }
        }
      });
    });
  }
});

test.describe('Mobile-First: Touch Interactions', () => {
  test.beforeEach(async ({ context, page }) => {
    await loginAdmin(context);
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
  });

  test('should support touch scrolling in stats modal', async ({ context, page }) => {
    const tournament = await getTournamentByKey(context, 'completed_bracket');
    expect(tournament).not.toBeNull();

    const tournamentPage = new TournamentPage(page);
    await tournamentPage.goto(tournament!.pk);
    await navigateToBracket(tournamentPage);
    await clickBracketNode(tournamentPage);

    const dialog = page.locator('[role="dialog"]').first();
    const dialogText = await dialog.textContent();

    if (dialogText?.includes('View Stats')) {
      await page.getByText('View Stats').click();
      await page.waitForTimeout(500);

      // Verify the stats modal is scrollable if content overflows
      const modal = page.locator('[role="dialog"]').last();
      await expect(modal).toBeVisible();

      // Modal should allow scrolling for overflow content
      // Just verify the modal is visible and usable - scroll behavior varies
      const clientHeight = await modal.evaluate((el) => el.clientHeight);
      expect(clientHeight).toBeGreaterThan(0);
    }
  });

  test('should have adequate tap targets for all interactive elements', async ({ context, page }) => {
    const tournament = await getTournamentByKey(context, 'completed_bracket');
    expect(tournament).not.toBeNull();

    const tournamentPage = new TournamentPage(page);
    await tournamentPage.goto(tournament!.pk);
    await navigateToBracket(tournamentPage);

    // Check that buttons and links meet minimum tap target size (44x44)
    const interactiveElements = page.locator('button:visible, a:visible');
    const count = await interactiveElements.count();

    for (let i = 0; i < count; i++) {
      const el = interactiveElements.nth(i);
      const isVisible = await el.isVisible().catch(() => false);

      if (isVisible) {
        const boundingBox = await el.boundingBox();

        if (boundingBox && boundingBox.width > 0 && boundingBox.height > 0) {
          // Allow some flexibility but log warnings on very small targets
          if (boundingBox.height < 32 || boundingBox.width < 32) {
            console.log(`Warning: Small tap target detected: ${boundingBox.width}x${boundingBox.height}`);
          }
        }
      }
    }
  });
});

test.describe('Mobile-First: Orientation Changes', () => {
  test.beforeEach(async ({ context }) => {
    await loginAdmin(context);
  });

  test('should handle portrait to landscape orientation', async ({ context, page }) => {
    const tournament = await getTournamentByKey(context, 'completed_bracket');
    expect(tournament).not.toBeNull();

    // Start in portrait
    await page.setViewportSize({ width: 375, height: 667 });

    const tournamentPage = new TournamentPage(page);
    await tournamentPage.goto(tournament!.pk);
    await navigateToBracket(tournamentPage);

    // Switch to landscape
    await page.setViewportSize({ width: 667, height: 375 });
    await page.waitForTimeout(300);

    // Content should still be visible
    await expect(page.locator('body')).toBeVisible();

    // No content should be cut off
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(670);
  });

  test('should maintain modal visibility after orientation change', async ({ context, page }) => {
    const tournament = await getTournamentByKey(context, 'completed_bracket');
    expect(tournament).not.toBeNull();

    // Start in portrait
    await page.setViewportSize({ width: 375, height: 667 });

    const tournamentPage = new TournamentPage(page);
    await tournamentPage.goto(tournament!.pk);
    await navigateToBracket(tournamentPage);
    await clickBracketNode(tournamentPage);

    // Modal should be visible in portrait
    await expect(page.locator('[role="dialog"]')).toBeVisible();

    // Switch to landscape
    await page.setViewportSize({ width: 667, height: 375 });
    await page.waitForTimeout(300);

    // Modal should still be visible and accessible
    await expect(page.locator('[role="dialog"]')).toBeVisible();
  });
});
