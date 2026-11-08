/**
 * Tournament Card Layout Tests
 *
 * Cards in the same grid row must share one height, and their footer
 * buttons must line up, even when one card renders fewer rows (#301).
 */

import { test, expect, visitAndWaitForHydration } from '../../fixtures';

// 1440px wide puts the /tournaments grid at its xl breakpoint (4 columns).
const DESKTOP_VIEWPORT = { width: 1440, height: 1200 };
const ROW_SIZE = 4;

test.describe('Tournaments - card layout', () => {
  test('cards in a row share one height and align their footers', async ({ page }) => {
    await page.setViewportSize(DESKTOP_VIEWPORT);

    // Keep only the first row of real tournaments and drop optional fields
    // from the second one, so its card has one row fewer than its neighbours.
    // Seed data alone gives every card the same rows, which would not detect
    // a regression.
    await page.route('**/api/tournaments-list/**', async (route) => {
      const response = await route.fetch();
      const tournaments = (await response.json()) as Record<string, unknown>[];
      expect(tournaments.length).toBeGreaterThanOrEqual(ROW_SIZE);
      const row = tournaments.slice(0, ROW_SIZE);
      row[1] = { ...row[1], tournament_type: null, state: null, date_played: null };
      await route.fulfill({ response, json: row });
    });

    await visitAndWaitForHydration(page, '/tournaments');

    const cards = page.locator('[data-testid^="tournament-card-"]:not([data-testid="tournament-card-date"])');
    await expect(cards).toHaveCount(ROW_SIZE, { timeout: 30000 });

    // Cards fade and slide in, so poll until the boxes stop moving.
    await expect(async () => {
      const boxes = await Promise.all(
        (await cards.all()).map(async (card) => {
          const cardBox = await card.boundingBox();
          const viewBox = await card.locator('[data-testid^="tournament-view-"]').boundingBox();
          expect(cardBox).not.toBeNull();
          expect(viewBox).not.toBeNull();
          return { card: cardBox!, view: viewBox! };
        }),
      );

      // Stretched cards start at the top of their grid cell, so all four tops line up.
      for (const box of boxes) {
        expect(Math.abs(box.card.y - boxes[0].card.y)).toBeLessThanOrEqual(1);
      }
      for (const box of boxes) {
        expect(Math.abs(box.card.height - boxes[0].card.height)).toBeLessThanOrEqual(1);
        expect(
          Math.abs(box.view.y + box.view.height - (boxes[0].view.y + boxes[0].view.height)),
        ).toBeLessThanOrEqual(1);
      }
    }).toPass({ timeout: 10000 });
  });
});
