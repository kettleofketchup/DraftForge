/** Tournament detail mobile (#232): breadcrumb hidden, no h-overflow, page-nav drives tabs. */

import { test, expect, getTournamentByKey } from '../../fixtures';

test.describe('Tournament detail on mobile', () => {
  let tournamentPk: number;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const tournament = await getTournamentByKey(context, 'completed_bracket');
    tournamentPk = tournament ? tournament.pk : 1;
    await context.close();
  });

  test.beforeEach(async ({ loginAdmin, page }) => {
    await loginAdmin();
    await page.goto(`/tournament/${tournamentPk}/players`);
    await page
      .locator('[data-testid="tournamentDetailPage"]')
      .waitFor({ state: 'visible', timeout: 15_000 });
  });

  test('breadcrumb is hidden on mobile', async ({ page }) => {
    // EntityBreadcrumb renders the <nav aria-label="breadcrumb">; with
    // `hidden sm:block` it should not be visible at mobile widths.
    await expect(page.locator('nav[aria-label="breadcrumb"]')).toBeHidden();
  });

  test('no horizontal overflow on players tab', async ({ page }) => {
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflow, 'horizontal overflow on /tournament/:pk/players').toBe(false);
  });

  test('Import CSV button is fully visible (no clipping)', async ({ page }) => {
    const button = page.locator('[data-testid="tournament-csv-import-btn"]');
    await expect(button).toBeVisible();

    const box = await button.boundingBox();
    const viewport = page.viewportSize();
    expect(box, 'Import CSV bounding box').not.toBeNull();
    expect(viewport, 'viewport from device profile').not.toBeNull();
    if (box && viewport) {
      expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
      expect(box.x).toBeGreaterThanOrEqual(0);
    }
  });

  test('desktop TabsList is hidden, page-nav dropdown is visible', async ({ page }) => {
    // Desktop tabs (in TournamentTabs) are `hidden md:block`.
    await expect(page.locator('[data-testid="tournamentTabsList"]')).toBeHidden();
    // Page-nav dropdown (centered in the navbar at mobile widths) drives tabs.
    await expect(page.locator('[data-testid="page-nav-trigger"]')).toBeVisible();
  });

  test('?modal=captains deep-link opens the Choose Captains dialog', async ({ page }) => {
    // ?modal=captains is bookmarkable — opens the dialog without clicking the in-page trigger.
    await page.goto(`/tournament/${tournamentPk}/teams?modal=captains`);
    const dialog = page.locator('[role="dialog"]', { hasText: 'Choose Captains' });
    await expect(dialog).toBeVisible({ timeout: 15_000 });
  });
});
