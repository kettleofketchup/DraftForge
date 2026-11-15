/** brandBg surfaces (--brand-bg) render their gradient instead of resolving to none. */

import { test, expect, getTournamentByKey } from '../../fixtures';

test.describe('Brand surface background', () => {
  let tournamentPk: number;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const tournament = await getTournamentByKey(context, 'completed_bracket');
    tournamentPk = tournament ? tournament.pk : 1;
    await context.close();
  });

  test('@cicd admin actions dropdown paints the brand gradient', async ({ loginAdmin, page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loginAdmin();
    await page.goto(`/tournament/${tournamentPk}/players`);
    await page
      .locator('[data-testid="tournamentDetailPage"]')
      .waitFor({ state: 'visible', timeout: 15_000 });

    await page.locator('[data-testid="tournament-admin-actions-mobile"]').click();
    const menu = page.locator('[data-testid="tournament-admin-actions-mobile-menu"]');
    await expect(menu).toBeVisible();

    const backgroundImage = await menu.evaluate((el) => getComputedStyle(el).backgroundImage);
    await menu.screenshot({ path: test.info().outputPath('brand-dropdown.png') });
    expect(backgroundImage).toContain('linear-gradient');
  });
});
