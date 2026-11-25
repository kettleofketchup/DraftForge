/**
 * The tournament Players tab reads the org from the organization query, so an
 * org change made elsewhere shows up on refocus instead of after a reload.
 */

import {
  expect,
  getTournamentByKey,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';

const NOT_CONFIGURED = 'No Discord server configured for this organization';

let tournamentPk: number;

test.describe('AddUserModal org refresh', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const tournament = await getTournamentByKey(context, 'completed_bracket');
    if (!tournament) throw new Error('No completed_bracket tournament found');
    tournamentPk = tournament.pk;
    await context.close();
  });

  test('@cicd tournament add-player modal sees a Discord server linked elsewhere', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();

    let linked = false;
    await page.route('**/api/organizations/*/', async (route) => {
      if (route.request().method() !== 'GET') return route.continue();
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({
        response,
        json: { ...body, discord_server_id: linked ? '1' : null },
      });
    });

    await page.clock.install();
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);
    await expect(
      page.locator('[data-testid="tournamentDetailPage"]'),
    ).toBeVisible({
      timeout: 15000,
    });

    const addBtn = page.locator('[data-testid="tournamentAddPlayerBtn"]');
    const modal = page.locator('[data-testid="add-user-modal"]');

    await addBtn.click();
    await expect(modal.getByText(NOT_CONFIGURED)).toBeVisible({
      timeout: 10000,
    });
    await page.keyboard.press('Escape');
    await expect(modal).not.toBeVisible();

    linked = true;
    await page.clock.fastForward('00:31');
    const refetched = page.waitForResponse(
      (r) =>
        /\/api\/organizations\/\d+\/$/.test(new URL(r.url()).pathname) &&
        r.request().method() === 'GET',
    );
    await page.evaluate(() =>
      window.dispatchEvent(new Event('visibilitychange')),
    );
    await refetched;

    await addBtn.click();
    await expect(modal).toBeVisible({ timeout: 5000 });
    await expect(modal.getByText(NOT_CONFIGURED)).not.toBeVisible({
      timeout: 10000,
    });
  });
});
