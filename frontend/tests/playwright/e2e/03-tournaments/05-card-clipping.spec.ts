/**
 * Nothing on /tournaments may be clipped: not by the viewport, not by the
 * page's overflow-hidden scroll area, and not by its own card. The page
 * scrolls inside a Radix ScrollArea whose viewport hides horizontal
 * overflow, so anything wider than it is cut off rather than scrollable.
 *
 * Seed: backend/tests/data/tournament_discovery.py. User 1100 is a member of
 * the discovery home org: logged in, the default is the flat My organizations
 * view with a Signups open badge, and the tiered view needs ?organization=all.
 * League 30 is the discovery home league, used for the league Tournaments tab.
 */

import type { Locator, Page } from '@playwright/test';

import { expect, loginAsUser, test, visitAndWaitForHydration } from '../../fixtures';
import { CARD_SELECTOR } from '../../helpers/tournament';

const DISCOVERY_MEMBER_PK = 1100;
const DISCOVERY_HOME_LEAGUE_PK = 30;
const WIDTHS = [1280, 1366, 1680, 1920, 2560];
const CONTROLS = [
  'tournaments-search',
  'tournaments-filter-organization',
  'tournaments-filter-league',
  'tournaments-tab-upcoming',
  'tournaments-tab-archived',
];
/** Fixed-vocabulary card values: these must never end in an ellipsis. */
const UNTRUNCATED_VALUES = ['tournament-card-date', 'tournament-card-time', 'tournament-card-state'];

type Tab = 'upcoming' | 'archived';

interface Box {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

async function waitForCards(page: Page, tab: Tab): Promise<Locator> {
  const panel = page.getByTestId(`tournaments-panel-${tab}`);
  await expect(panel).toHaveAttribute('data-fetching', 'false', { timeout: 15000 });
  const cards = panel.locator(CARD_SELECTOR);
  await expect(cards.first()).toBeVisible({ timeout: 15000 });
  return cards;
}

async function scrollAreaOverflow(page: Page): Promise<{ scrollWidth: number; clientWidth: number }> {
  return page.evaluate(() => {
    const viewport = document.querySelector<HTMLElement>(
      '#outlet_root [data-slot="scroll-area-viewport"]',
    );
    if (!viewport) throw new Error('outlet scroll area viewport not found');
    return { scrollWidth: viewport.scrollWidth, clientWidth: viewport.clientWidth };
  });
}

async function box(locator: Locator): Promise<Box> {
  return locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
  });
}

async function expectNothingClipped(page: Page, tab: Tab, width: number): Promise<void> {
  const cards = await waitForCards(page, tab);
  const where = `${tab} @ ${width}px`;

  const idle = await scrollAreaOverflow(page);
  expect(idle.scrollWidth, `scroll area overflows (${where})`).toBeLessThanOrEqual(idle.clientWidth);

  for (const testId of CONTROLS) {
    const b = await box(page.getByTestId(testId));
    expect(b.left, `${testId} clipped left (${where})`).toBeGreaterThanOrEqual(0);
    expect(b.right, `${testId} clipped right (${where})`).toBeLessThanOrEqual(width);
  }

  const search = await box(page.getByTestId('tournaments-search'));
  const boxes = await cards.evaluateAll((els) =>
    els.map((el) => {
      const r = el.getBoundingClientRect();
      const view = el.querySelector('[data-testid^="tournament-view-"]')!.getBoundingClientRect();
      let grid = el.parentElement;
      while (grid && getComputedStyle(grid).display !== 'grid') grid = grid.parentElement;
      const track = grid ? parseFloat(getComputedStyle(grid).gridTemplateColumns) : NaN;
      return {
        track,
        card: { left: r.left, right: r.right, top: r.top, bottom: r.bottom },
        view: { left: view.left, right: view.right, top: view.top, bottom: view.bottom },
      };
    }),
  );

  // Cards fill their grid tracks, so the grid's left edge lines up with the
  // filter row instead of each card floating inside a wider column.
  const minLeft = Math.min(...boxes.map((b) => b.card.left));
  expect(Math.abs(minLeft - search.left), `first column misaligned with search (${where})`).toBeLessThanOrEqual(1);

  for (const { card, view, track } of boxes) {
    expect(Math.abs(card.right - card.left - track), `card narrower than its column (${where})`).toBeLessThanOrEqual(1);
    expect(card.left, `card clipped left (${where})`).toBeGreaterThanOrEqual(0);
    expect(card.right, `card clipped right (${where})`).toBeLessThanOrEqual(width);
    expect(view.left, `view button outside card (${where})`).toBeGreaterThanOrEqual(card.left);
    expect(view.right, `view button outside card (${where})`).toBeLessThanOrEqual(card.right);
    // The footer button keeps at least the card's side inset below it.
    expect(card.bottom - view.bottom, `view button crowds the card bottom (${where})`).toBeGreaterThanOrEqual(
      view.left - card.left,
    );
  }

  for (const testId of UNTRUNCATED_VALUES) {
    const clipped = await cards.getByTestId(testId).evaluateAll((els) =>
      els.filter((el) => el.scrollWidth > el.clientWidth).map((el) => el.textContent),
    );
    expect(clipped, `${testId} truncated (${where})`).toEqual([]);
  }

  // Hovering lifts and scales a card; the rightmost one must stay inside the
  // scroll area rather than be cut off by its hidden horizontal overflow.
  const firstRowTop = Math.min(...boxes.map((b) => b.card.top));
  const rightmost = boxes
    .map((b, i) => ({ ...b, i }))
    .filter((b) => Math.abs(b.card.top - firstRowTop) < 1)
    .sort((a, b) => b.card.right - a.card.right)[0];
  await cards.nth(rightmost.i).hover();
  await expect(async () => {
    const hovered = await scrollAreaOverflow(page);
    expect(hovered.scrollWidth, `hovered card overflows (${where})`).toBeLessThanOrEqual(
      hovered.clientWidth,
    );
  }).toPass({ timeout: 3000 });
  await page.mouse.move(0, 0);
}

async function checkWidths(page: Page, tab: Tab, path: string): Promise<void> {
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 1000 });
    await visitAndWaitForHydration(page, path);
    await expectNothingClipped(page, tab, width);
  }
}

/** The league Tournaments tab renders the same cards in its own grid. */
async function expectLeagueTabNothingClipped(page: Page, width: number): Promise<void> {
  const where = `league tab @ ${width}px`;
  const cards = page.locator(CARD_SELECTOR);
  await expect(cards.first()).toBeVisible({ timeout: 15000 });

  const idle = await scrollAreaOverflow(page);
  expect(idle.scrollWidth, `scroll area overflows (${where})`).toBeLessThanOrEqual(idle.clientWidth);

  const boxes = await cards.evaluateAll((els) =>
    els.map((el) => {
      const r = el.getBoundingClientRect();
      const view = el.querySelector('[data-testid^="tournament-view-"]')!.getBoundingClientRect();
      return {
        card: { left: r.left, right: r.right, top: r.top, bottom: r.bottom },
        view: { left: view.left, right: view.right, top: view.top, bottom: view.bottom },
      };
    }),
  );
  expect(boxes.length, `need at least two league cards (${where})`).toBeGreaterThan(1);

  for (const { card, view } of boxes) {
    expect(card.left, `card clipped left (${where})`).toBeGreaterThanOrEqual(0);
    expect(card.right, `card clipped right (${where})`).toBeLessThanOrEqual(width);
    expect(view.left, `view button outside card (${where})`).toBeGreaterThanOrEqual(card.left);
    expect(view.right, `view button outside card (${where})`).toBeLessThanOrEqual(card.right);
    expect(view.bottom, `view button outside card (${where})`).toBeLessThanOrEqual(card.bottom);
  }

  // Cards in a row keep the grid's gap-4 between them, the same as /tournaments.
  const rows = new Map<number, Box[]>();
  for (const { card } of boxes) {
    const key = Math.round(card.top);
    rows.set(key, [...(rows.get(key) ?? []), card]);
  }
  for (const row of rows.values()) {
    const sorted = [...row].sort((a, b) => a.left - b.left);
    for (let i = 1; i < sorted.length; i++) {
      const gap = sorted[i].left - sorted[i - 1].right;
      expect(gap, `cards closer than the grid gap (${where})`).toBeGreaterThanOrEqual(15);
    }
  }

  const firstRowTop = Math.min(...boxes.map((b) => b.card.top));
  const rightmost = boxes
    .map((b, i) => ({ ...b, i }))
    .filter((b) => Math.abs(b.card.top - firstRowTop) < 1)
    .sort((a, b) => b.card.right - a.card.right)[0];
  await cards.nth(rightmost.i).hover();
  await expect(async () => {
    const hovered = await scrollAreaOverflow(page);
    expect(hovered.scrollWidth, `hovered card overflows (${where})`).toBeLessThanOrEqual(
      hovered.clientWidth,
    );
  }).toPass({ timeout: 3000 });
  await page.mouse.move(0, 0);
}

test.describe('Tournaments - nothing is clipped', () => {
  test.describe.configure({ timeout: 120_000 });

  test('@cicd logged out: upcoming grid, controls and cards fit at desktop widths', async ({
    page,
  }) => {
    await checkWidths(page, 'upcoming', '/tournaments');
  });

  test('@cicd logged out: archived grid fits at desktop widths', async ({ page }) => {
    await checkWidths(page, 'archived', '/tournaments?tab=archived');
  });

  test('@cicd organization member: tiered upcoming view fits at desktop widths', async ({
    page,
    context,
  }) => {
    await loginAsUser(context, DISCOVERY_MEMBER_PK);
    await checkWidths(page, 'upcoming', '/tournaments?organization=all');
  });

  test('@cicd organization member: My organizations with a signups badge fits at desktop widths', async ({
    page,
    context,
  }) => {
    await loginAsUser(context, DISCOVERY_MEMBER_PK);
    await checkWidths(page, 'upcoming', '/tournaments');
  });

  test('@cicd league Tournaments tab: cards fit and keep their gap at desktop widths', async ({
    page,
  }) => {
    for (const width of [1024, ...WIDTHS]) {
      await page.setViewportSize({ width, height: 1000 });
      await visitAndWaitForHydration(page, `/leagues/${DISCOVERY_HOME_LEAGUE_PK}/tournaments`);
      await expectLeagueTabNothingClipped(page, width);
    }
  });
});
