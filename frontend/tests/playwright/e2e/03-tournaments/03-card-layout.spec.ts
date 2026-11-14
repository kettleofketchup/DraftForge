/**
 * Tournament Card Layout Tests
 *
 * Cards in the same grid row must share one height, and their footer
 * buttons must line up, even when one card renders fewer rows (#301).
 * Both grids that render TournamentCard are covered: the /tournaments page
 * (cards inside TournamentCardWrapper) and the league Tournaments tab (cards
 * as direct grid items).
 */

import type { Locator, Page } from '@playwright/test';

import {
  expect,
  getFirstLeague,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { CARD_SELECTOR } from '../../helpers/tournament';

type Tournament = Record<string, unknown>;

/**
 * Serve exactly one grid row of real tournaments. The second card loses its
 * full-width Style row (tournament_type), so it is one row shorter than its
 * neighbours. The API never sends a null tournament_type, but it is the one
 * conditional row that changes card height: Date and State share their grid
 * rows with the always-rendered Time and Players cells. Seed data alone gives
 * every card the same rows, which would not detect a regression.
 */
async function serveOneRow(
  page: Page,
  rowSize: number,
  edit: (t: Tournament) => Tournament = (t) => t,
): Promise<void> {
  await page.route('**/api/tournaments-list/**', async (route) => {
    const response = await route.fetch();
    const tournaments = (await response.json()) as Tournament[];
    // Fulfil even when seed data is short; the count assertion in the test
    // then fails with a clear message instead of a stuck skeleton.
    const row = tournaments.slice(0, rowSize).map(edit);
    if (row.length > 1) {
      row[1] = { ...row[1], tournament_type: null };
    }
    await route.fulfill({ response, json: row });
  });
}

/**
 * /tournaments asks for the filtered upcoming bucket, which may hold fewer
 * than 4 rows, so fetch the unparameterised list instead and rewrite 4 rows
 * into one upcoming org: row 0 LIVE, row 1 without its Style row (#301) and
 * with a logo, row 2 without a logo, row 3 without a league.
 */
async function serveDiscoveryRows(page: Page): Promise<void> {
  await page.route('**/api/tournaments-list/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.has('page')) {
      await route.continue();
      return;
    }
    const response = await route.fetch({ url: `${url.origin}/api/tournaments-list/` });
    const tournaments = (await response.json()) as Tournament[];
    const source = tournaments.find((t) => t.league && typeof t.league === 'object');
    const baseLeague: Tournament = {
      ...((source?.league as Tournament | undefined) ?? { pk: 1, name: 'Card Layout League' }),
      organization_id: 1,
      organization_name: 'Card Layout Org',
      organization_logo: null,
    };
    const row: Tournament[] = tournaments.slice(0, 4).map((t, i) => ({
      ...t,
      state: 'future',
      date_played: `2099-06-0${i + 1}T18:00:00Z`,
      // A long zone name wraps the Time tile and shifts the row; keep rows uniform.
      timezone: 'UTC',
      league: baseLeague,
    }));
    if (row.length > 0) row[0] = { ...row[0], state: 'in_progress' };
    if (row.length > 1) {
      row[1] = {
        ...row[1],
        tournament_type: null,
        league: { ...baseLeague, organization_logo: '/logo192.png' },
      };
    }
    if (row.length > 3) row[3] = { ...row[3], league: null };
    await route.fulfill({ response, json: row });
  });
}

async function expectSameY(locators: Locator): Promise<void> {
  await expect(async () => {
    const boxes = await Promise.all(
      (await locators.all()).map((l) => l.boundingBox()),
    );
    for (const box of boxes) {
      expect(box).not.toBeNull();
      expect(Math.abs(box!.y - boxes[0]!.y)).toBeLessThanOrEqual(1);
    }
  }).toPass({ timeout: 10000 });
}

async function expectRowAligned(cards: Locator): Promise<void> {
  // Cards fade and slide in, so poll until the boxes stop moving.
  await expect(async () => {
    const boxes = await Promise.all(
      (await cards.all()).map(async (card) => {
        const cardBox = await card.boundingBox();
        const viewBox = await card
          .locator('[data-testid^="tournament-view-"]')
          .boundingBox();
        expect(cardBox).not.toBeNull();
        expect(viewBox).not.toBeNull();
        return { card: cardBox!, view: viewBox! };
      }),
    );

    // Stretched cards start at the top of their grid cell, so all tops line up.
    for (const box of boxes) {
      expect(Math.abs(box.card.y - boxes[0].card.y)).toBeLessThanOrEqual(1);
    }
    for (const box of boxes) {
      expect(
        Math.abs(box.card.height - boxes[0].card.height),
      ).toBeLessThanOrEqual(1);
      expect(
        Math.abs(
          box.view.y +
            box.view.height -
            (boxes[0].view.y + boxes[0].view.height),
        ),
      ).toBeLessThanOrEqual(1);
    }
  }).toPass({ timeout: 10000 });
}

test.describe('Tournaments - card layout', () => {
  // Room for the 15s card wait plus the 10s alignment poll on a slow stack.
  test.describe.configure({ timeout: 60_000 });

  test('@cicd /tournaments cards in a row share one height and align their footers', async ({
    page,
  }) => {
    // 1440px wide puts the /tournaments grid at its xl breakpoint (4 columns).
    const rowSize = 4;
    await page.setViewportSize({ width: 1440, height: 1200 });
    await serveDiscoveryRows(page);

    await visitAndWaitForHydration(page, '/tournaments');

    const cards = page.locator(CARD_SELECTOR);
    await expect(cards).toHaveCount(rowSize, { timeout: 15000 });
    await expectRowAligned(cards);

    // A LIVE header must not push the inner rows down.
    await expect(cards.nth(0).getByTestId('tournament-live-badge')).toBeVisible();
    await expect(page.getByTestId('tournament-live-badge')).toHaveCount(1);
    await expectSameY(cards.getByTestId('tournament-card-date'));

    // Logo, Building2 box and "No organization" all use a 24px media box.
    const media = cards.getByTestId('tournament-card-org-media');
    await expect(media).toHaveCount(rowSize);
    for (const box of await media.all()) {
      const bb = await box.boundingBox();
      expect(bb).not.toBeNull();
      expect(Math.abs(bb!.height - 24)).toBeLessThanOrEqual(0.5);
    }
  });

  test('@cicd league tab cards in a row share one height and align their footers', async ({
    page,
  }) => {
    const league = await getFirstLeague(page.context());
    expect(league, 'need at least one seeded league').not.toBeNull();
    const leaguePk = league!.pk;

    // 1200px wide puts the league tab grid at its lg breakpoint (3 columns).
    const rowSize = 3;
    await page.setViewportSize({ width: 1200, height: 1200 });
    // The league page filters the tournament list client-side by league.
    await serveOneRow(page, rowSize, (t) => ({
      ...t,
      league: leaguePk,
      league_pk: leaguePk,
    }));

    await visitAndWaitForHydration(page, `/leagues/${leaguePk}/tournaments`);

    const cards = page.locator(CARD_SELECTOR);
    await expect(cards).toHaveCount(rowSize, { timeout: 15000 });
    await expectRowAligned(cards);
  });
});
