/**
 * The Match Details dialog fits the screen with the lobby panel in it.
 *
 * The lobby panel makes the dialog long. At a phone size (390x844) and a
 * small laptop (1366x768), the title and the close button stay inside the
 * viewport, and Link Steam Match (the last control) is reached by scrolling
 * the dialog body. Needs lobbies on (docker/.env.test), not the simulator.
 */

import {
  expect,
  loginAdmin,
  openBracket,
  openMatchModal,
  resetDotaLobbyData,
  test,
  type DotaLobbyTestData,
} from '../../fixtures';
import type { Locator, Page } from '@playwright/test';

const VIEWPORTS = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'laptop', width: 1366, height: 768 },
];

async function expectInViewport(page: Page, locator: Locator, what: string): Promise<void> {
  const viewport = page.viewportSize()!;
  const box = await locator.boundingBox();
  expect(box, `${what} is rendered`).not.toBeNull();
  expect(box!.x, `${what} left edge`).toBeGreaterThanOrEqual(0);
  expect(box!.y, `${what} top edge`).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width, `${what} right edge`).toBeLessThanOrEqual(viewport.width + 0.5);
  expect(box!.y + box!.height, `${what} bottom edge`).toBeLessThanOrEqual(viewport.height + 0.5);
}

test.describe('Dota lobby: Match Details dialog fits the viewport (e2e)', () => {
  let data: DotaLobbyTestData;

  test.beforeEach(async ({ context }) => {
    data = await resetDotaLobbyData(context);
    await loginAdmin(context);
  });

  for (const viewport of VIEWPORTS) {
    test(`@cicd title, close and Link Steam Match fit at ${viewport.width}x${viewport.height}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      const tournament = data.series_event.tournament;
      await openBracket(page, tournament.pk);
      const dialog = await openMatchModal(page, tournament.games[0].pk);
      await expect(dialog.locator('[data-testid="lobby-panel"]')).toBeVisible({ timeout: 15_000 });
      await expect(dialog.locator('[data-testid="lobby-staff-controls"]')).toBeVisible();

      const title = dialog.locator('[data-testid="match-details-header"]');
      const close = dialog.locator('[data-testid="dialog-close-button"]');
      await expectInViewport(page, dialog, 'dialog');
      await expectInViewport(page, title, 'title');
      await expectInViewport(page, close, 'close button');

      // The body scrolls, not the page: the last control comes into view.
      const link = dialog.locator('[data-testid="link-steam-match-btn"]');
      await expect(link).toBeAttached();
      await link.scrollIntoViewIfNeeded();
      await expect(link).toBeVisible();
      await expectInViewport(page, link, 'Link Steam Match');
      const body = await dialog.locator('[data-testid="matchStatsModal-body"]').boundingBox();
      const linkBox = await link.boundingBox();
      expect(linkBox!.y).toBeGreaterThanOrEqual(body!.y - 0.5);
      expect(linkBox!.y + linkBox!.height).toBeLessThanOrEqual(body!.y + body!.height + 0.5);

      // Scrolling the body leaves the header where it was.
      await expectInViewport(page, title, 'title after scrolling');
      await expectInViewport(page, close, 'close button after scrolling');
    });
  }
});
