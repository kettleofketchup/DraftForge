/**
 * Tournament discovery: Upcoming | Archived tabs, the "My organizations"
 * default, "Your organizations" tiers, filters, search, load more and list
 * refresh after create/delete.
 *
 * Seed: backend/tests/data/tournament_discovery.py (orgs 30-32, leagues 30-32,
 * user 1100 = discovery_member of org 30, tournaments 900-906; 906 belongs to
 * org 32 and its source event has signups open).
 */

import type { BrowserContext, Locator, Page, Request } from '@playwright/test';

import { API_URL } from '../../fixtures/base-url';
import { getCsrfToken } from '../../fixtures/events';
import {
  expect,
  loginAdmin,
  loginAsUser,
  postWithCsrf,
  test,
} from '../../fixtures';
import {
  CARD_SELECTOR,
  findTournamentCard,
  showAllOrganizations,
} from '../../helpers/tournament';

const DISCOVERY_MEMBER_PK = 1100;
const HOME_ORG = 30;
const HOME_LEAGUE = 30;
const AWAY_ORG = 31;
const LIST_PATH = '/api/tournaments-list/';
const FAR_FUTURE_DATE = '2099-12-31T18:00:00Z';

const HOME_LIVE = 'Discovery Home Live';
const HOME_SOON = 'Discovery Home Soon';
const HOME_LATER = 'Discovery Home Later';
const HOME_FINISHED = 'Discovery Home Finished';
const HOME_STALE = 'Discovery Home Stale';
const AWAY_CUP = 'Discovery Away Cup';
const OPEN_CUP = 'Discovery Open Signups Cup';
const HOME_ORG_NAME = 'Discovery Home Organization';

type Tournament = Record<string, unknown>;

function recordListRequests(page: Page): string[] {
  const urls: string[] = [];
  page.on('request', (req: Request) => {
    if (new URL(req.url()).pathname.startsWith(LIST_PATH)) urls.push(req.url());
  });
  return urls;
}

function attachErrorCapture(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    if (/Failed to load resource: the server responded with a status of 4\d\d/.test(m.text())) {
      return;
    }
    errors.push(`console: ${m.text()}`);
  });
  return errors;
}

function bucketOf(url: string): string | null {
  return new URL(url).searchParams.get('bucket');
}

function panel(page: Page, tab: 'upcoming' | 'archived'): Locator {
  return page.getByTestId(`tournaments-panel-${tab}`);
}

function cardNamed(scope: Page | Locator, name: string): Locator {
  return scope.locator(CARD_SELECTOR).filter({ hasText: name });
}

async function waitForSettled(page: Page, tab: 'upcoming' | 'archived'): Promise<void> {
  const p = panel(page, tab);
  await expect(p).toBeVisible({ timeout: 15000 });
  await expect(p).toHaveAttribute('data-fetching', 'false', { timeout: 15000 });
}

async function waitForFilterRow(page: Page): Promise<void> {
  await expect(page.getByTestId('tournaments-filter-organization')).toBeVisible({
    timeout: 15000,
  });
}

async function cardNamesIn(scope: Locator): Promise<string[]> {
  return scope.locator(CARD_SELECTOR).allInnerTexts();
}

function indexOfName(texts: string[], name: string): number {
  return texts.findIndex((t) => t.includes(name));
}

async function deleteTournamentByPk(context: BrowserContext, pk: number): Promise<void> {
  const csrf = await getCsrfToken(context);
  await context.request.delete(`${API_URL}/tournaments/${pk}/`, {
    headers: { 'X-CSRFToken': csrf },
    failOnStatusCode: false,
  });
}

async function findPksByName(context: BrowserContext, name: string): Promise<number[]> {
  const pks: number[] = [];
  for (const bucket of ['upcoming', 'archived']) {
    const res = await context.request.get(
      `${API_URL}/tournaments-list/?bucket=${bucket}&search=${encodeURIComponent(name)}`,
      { failOnStatusCode: false },
    );
    if (!res.ok()) continue;
    const rows = (await res.json()) as Tournament[];
    for (const row of rows) {
      if (row.name === name && typeof row.pk === 'number') pks.push(row.pk);
    }
  }
  return pks;
}

async function cleanupByName(context: BrowserContext, name: string): Promise<void> {
  for (const pk of await findPksByName(context, name)) {
    await deleteTournamentByPk(context, pk);
  }
}

test.describe('Tournament discovery (@cicd)', () => {
  test.describe('request isolation', () => {
    test('@cicd default tab never requests the archive (logged out)', async ({ page }) => {
      const urls = recordListRequests(page);
      await page.goto('/tournaments');
      await waitForSettled(page, 'upcoming');
      await expect(cardNamed(page, HOME_SOON).first()).toBeVisible({ timeout: 15000 });

      expect(urls.length).toBeGreaterThan(0);
      expect(urls.filter((u) => bucketOf(u) === null)).toEqual([]);
      expect(urls.filter((u) => bucketOf(u) === 'archived')).toEqual([]);
    });

    test('@cicd default tab never requests the archive (logged in)', async ({
      page,
      context,
    }) => {
      await loginAsUser(context, DISCOVERY_MEMBER_PK);
      const urls = recordListRequests(page);
      await page.goto('/tournaments');
      await expect(cardNamed(page, HOME_SOON).first()).toBeVisible({ timeout: 15000 });
      await waitForSettled(page, 'upcoming');

      expect(urls.length).toBeGreaterThan(0);
      expect(urls.filter((u) => bucketOf(u) === null)).toEqual([]);
      expect(urls.filter((u) => bucketOf(u) === 'archived')).toEqual([]);
      // The default waits for the user, so it never fetches the unscoped list first.
      for (const url of urls) {
        const params = new URL(url).searchParams;
        expect(params.get('organizations')).toBe('mine');
        expect(params.get('open_signups')).toBe('1');
      }
    });

    test('@cicd archived tab never requests the upcoming list (logged out)', async ({
      page,
    }) => {
      const urls = recordListRequests(page);
      await page.goto('/tournaments?tab=archived');
      await waitForSettled(page, 'archived');
      await expect(page.locator(CARD_SELECTOR).first()).toBeVisible({ timeout: 15000 });

      expect(urls.length).toBeGreaterThan(0);
      expect(urls.filter((u) => bucketOf(u) === null)).toEqual([]);
      expect(urls.filter((u) => bucketOf(u) === 'upcoming')).toEqual([]);
    });

    test('@cicd archived tab never requests the upcoming list (logged in)', async ({
      page,
      context,
    }) => {
      await loginAsUser(context, DISCOVERY_MEMBER_PK);
      const urls = recordListRequests(page);
      await page.goto('/tournaments?tab=archived');
      await waitForSettled(page, 'archived');
      await expect(page.locator(CARD_SELECTOR).first()).toBeVisible({ timeout: 15000 });

      expect(urls.length).toBeGreaterThan(0);
      expect(urls.filter((u) => bucketOf(u) === null)).toEqual([]);
      expect(urls.filter((u) => bucketOf(u) === 'upcoming')).toEqual([]);
    });
  });

  test.describe('hydration', () => {
    for (const path of ['/tournaments', `/tournaments?organization=${HOME_ORG}&league=${HOME_LEAGUE}`]) {
      test(`@cicd hard load of ${path} has no hydration mismatch`, async ({ page }) => {
        const errors = attachErrorCapture(page);
        await page.goto(path);
        await waitForFilterRow(page);
        await waitForSettled(page, 'upcoming');

        expect(errors.filter((e) => /hydration|did not match/i.test(e))).toEqual([]);
      });
    }
  });

  test.describe('logged in as an organization member', () => {
    test.beforeEach(async ({ context }) => {
      await loginAsUser(context, DISCOVERY_MEMBER_PK);
    });

    test('@cicd renders tiers without a flat-list flash, own org first, live first', async ({
      page,
      context,
    }) => {
      await context.addInitScript((cardSelector: string) => {
        const w = window as Window & { __flatCardSeen?: boolean };
        w.__flatCardSeen = false;
        const check = (node: Node) => {
          if (!(node instanceof Element)) return;
          const cards = node.matches(cardSelector)
            ? [node]
            : Array.from(node.querySelectorAll(cardSelector));
          if (cards.some((card) => card.closest('[data-tier]') === null)) {
            w.__flatCardSeen = true;
          }
        };
        new MutationObserver((mutations) => {
          for (const m of mutations) m.addedNodes.forEach(check);
        }).observe(document, { childList: true, subtree: true });
      }, CARD_SELECTOR);

      await page.goto('/tournaments?organization=all');
      await expect(page.getByTestId('tournaments-tier-yours')).toBeVisible({ timeout: 15000 });
      await waitForSettled(page, 'upcoming');

      const flatSeen = await page.evaluate(
        () => (window as Window & { __flatCardSeen?: boolean }).__flatCardSeen,
      );
      expect(flatSeen).toBe(false);

      const tiers = page.locator('[data-tier]');
      await expect(tiers.nth(0)).toHaveAttribute('data-tier', 'yours');
      await expect(tiers.nth(1)).toHaveAttribute('data-tier', 'others');

      const yours = page.locator('[data-tier="yours"]');
      const others = page.locator('[data-tier="others"]');

      const firstYours = yours.locator(CARD_SELECTOR).first();
      await expect(firstYours).toContainText(HOME_LIVE);
      await expect(firstYours.getByTestId('tournament-live-badge')).toBeVisible();
      await expect(firstYours.getByTestId('tournament-card-state')).toHaveText('Live');

      const names = await cardNamesIn(yours);
      const live = indexOfName(names, HOME_LIVE);
      const soon = indexOfName(names, HOME_SOON);
      const later = indexOfName(names, HOME_LATER);
      expect(live).toBeGreaterThanOrEqual(0);
      expect(soon).toBeGreaterThan(live);
      expect(later).toBeGreaterThan(soon);

      await expect(cardNamed(others, AWAY_CUP)).toHaveCount(1);
      await expect(cardNamed(yours, AWAY_CUP)).toHaveCount(0);
      await expect(cardNamed(page, HOME_FINISHED)).toHaveCount(0);
      await expect(cardNamed(page, HOME_STALE)).toHaveCount(0);
    });

    test('@cicd organization filter renders a flat list and survives a tab switch', async ({
      page,
    }) => {
      await page.goto(`/tournaments?organization=${HOME_ORG}`);
      await waitForSettled(page, 'upcoming');
      const upcoming = panel(page, 'upcoming');
      await expect(cardNamed(upcoming, HOME_SOON)).toHaveCount(1, { timeout: 15000 });
      await expect(page.locator('[data-tier]')).toHaveCount(0);
      await expect(page.getByTestId('tournaments-tier-yours')).toHaveCount(0);
      await expect(cardNamed(upcoming, AWAY_CUP)).toHaveCount(0);

      await page.getByTestId('tournaments-tab-archived').click();
      await expect(page).toHaveURL(new RegExp(`organization=${HOME_ORG}`));
      await waitForSettled(page, 'archived');
      const archived = panel(page, 'archived');
      await expect(cardNamed(archived, HOME_FINISHED)).toHaveCount(1, { timeout: 15000 });
      await expect(page.getByTestId('tournaments-filter-organization')).toContainText(
        'Discovery Home',
      );

      await page.getByTestId('tournaments-tab-upcoming').click();
      await expect(page).toHaveURL(new RegExp(`organization=${HOME_ORG}`));
      await waitForSettled(page, 'upcoming');
      await expect(page.locator('[data-tier]')).toHaveCount(0);
      await expect(cardNamed(panel(page, 'upcoming'), AWAY_CUP)).toHaveCount(0);
    });

    test('@cicd a search with no match shows only the empty state', async ({ page }) => {
      await page.goto('/tournaments?organization=all');
      await expect(page.getByTestId('tournaments-tier-yours')).toBeVisible({ timeout: 15000 });

      await page.getByTestId('tournaments-search').fill('zzq no such tournament xyz');
      await expect(page.getByTestId('tournaments-empty-upcoming')).toBeVisible({ timeout: 15000 });
      await waitForSettled(page, 'upcoming');
      await expect(page.getByTestId('tournaments-tier-yours')).toHaveCount(0);
      await expect(page.getByTestId('tournaments-tier-others')).toHaveCount(0);
    });
  });

  test.describe('My organizations (logged in as an organization member)', () => {
    test.beforeEach(async ({ context }) => {
      await loginAsUser(context, DISCOVERY_MEMBER_PK);
    });

    test('@cicd is the default: one list of own orgs plus open signups, badged', async ({
      page,
    }) => {
      await page.goto('/tournaments');
      await waitForFilterRow(page);
      await waitForSettled(page, 'upcoming');
      const upcoming = panel(page, 'upcoming');

      await expect(page.getByTestId('tournaments-filter-organization')).toContainText(
        'My organizations',
      );
      expect(new URL(page.url()).searchParams.has('organization')).toBe(false);
      await expect(page.locator('[data-tier]')).toHaveCount(0);
      await expect(page.getByTestId('tournaments-filter-clear')).toHaveCount(0);

      for (const name of [HOME_LIVE, HOME_SOON, HOME_LATER, OPEN_CUP]) {
        await expect(cardNamed(upcoming, name)).toHaveCount(1, { timeout: 15000 });
      }
      await expect(cardNamed(upcoming, AWAY_CUP)).toHaveCount(0);

      // Other specs add open-signup tournaments in parallel, so only the seeded
      // cards are asserted, never the panel's badge count.
      const badge = 'tournament-signups-open-badge';
      await expect(cardNamed(upcoming, OPEN_CUP).getByTestId(badge)).toHaveText('Signups open');
      for (const name of [HOME_LIVE, HOME_SOON, HOME_LATER]) {
        await expect(cardNamed(upcoming, name).getByTestId(badge)).toHaveCount(0);
      }
    });

    test('@cicd the dropdown lists My, All, then your and other organizations', async ({
      page,
    }) => {
      await page.goto('/tournaments');
      await waitForFilterRow(page);
      await page.getByTestId('tournaments-filter-organization').click();
      const listbox = page.getByRole('listbox');
      await expect(listbox).toBeVisible();

      const options = await listbox.getByRole('option').allInnerTexts();
      expect(options.slice(0, 2)).toEqual(['My organizations', 'All organizations']);

      const groups = listbox.getByRole('group');
      await expect(groups).toHaveCount(2);
      await expect(groups.nth(0)).toContainText('Your organizations');
      await expect(groups.nth(0).getByRole('option')).toHaveCount(1);
      await expect(groups.nth(0).getByRole('option')).toContainText(HOME_ORG_NAME);
      await expect(groups.nth(1)).toContainText('Other organizations');
      await expect(
        groups.nth(1).getByRole('option', { name: 'Discovery Away Org', exact: true }),
      ).toHaveCount(1);
      await expect(
        groups.nth(1).getByRole('option', { name: 'Discovery Open Org', exact: true }),
      ).toHaveCount(1);
      await page.keyboard.press('Escape');
    });

    test('@cicd switching to All organizations restores the tiers and the URL', async ({
      page,
    }) => {
      await page.goto('/tournaments');
      await waitForSettled(page, 'upcoming');
      await showAllOrganizations(page);

      await expect(page).toHaveURL(/organization=all/);
      await expect(page.getByTestId('tournaments-tier-yours')).toBeVisible({ timeout: 15000 });
      await waitForSettled(page, 'upcoming');
      const others = page.locator('[data-tier="others"]');
      await expect(cardNamed(others, AWAY_CUP)).toHaveCount(1);
      await expect(cardNamed(others, OPEN_CUP)).toHaveCount(1);
      await expect(page.getByTestId('tournament-signups-open-badge')).toHaveCount(0);

      await page.getByTestId('tournaments-filter-clear').click();
      await expect(page).not.toHaveURL(/organization=/);
      await expect(page.getByTestId('tournaments-filter-organization')).toContainText(
        'My organizations',
      );
      await waitForSettled(page, 'upcoming');
      await expect(page.locator('[data-tier]')).toHaveCount(0);
    });

    test('@cicd ?organization=all and ?organization=<id> deep links keep working', async ({
      page,
    }) => {
      await page.goto(`/tournaments?organization=${AWAY_ORG}`);
      await waitForSettled(page, 'upcoming');
      const upcoming = panel(page, 'upcoming');
      await expect(cardNamed(upcoming, AWAY_CUP)).toHaveCount(1, { timeout: 15000 });
      await expect(cardNamed(upcoming, HOME_SOON)).toHaveCount(0);
      await expect(page.locator('[data-tier]')).toHaveCount(0);

      await page.goto('/tournaments?organization=mine');
      await waitForSettled(page, 'upcoming');
      await expect(page.getByTestId('tournaments-filter-organization')).toContainText(
        'My organizations',
      );
      await expect(cardNamed(panel(page, 'upcoming'), OPEN_CUP)).toHaveCount(1, {
        timeout: 15000,
      });
    });

    test('@cicd archived shows only member organizations', async ({ page }) => {
      const urls = recordListRequests(page);
      await page.goto('/tournaments?tab=archived');
      await waitForSettled(page, 'archived');
      const archived = panel(page, 'archived');
      await expect(cardNamed(archived, HOME_FINISHED)).toHaveCount(1, { timeout: 15000 });

      const cards = archived.locator(CARD_SELECTOR);
      const total = await cards.count();
      await expect(cards.filter({ hasText: HOME_ORG_NAME })).toHaveCount(total);

      const archivedUrls = urls.filter((u) => bucketOf(u) === 'archived');
      expect(archivedUrls.length).toBeGreaterThan(0);
      for (const url of archivedUrls) {
        const params = new URL(url).searchParams;
        expect(params.get('organizations')).toBe('mine');
        expect(params.has('open_signups')).toBe(false);
      }
    });
  });

  test('@cicd logged out has no My organizations option', async ({ page }) => {
    await page.goto('/tournaments');
    await waitForFilterRow(page);
    await waitForSettled(page, 'upcoming');
    const trigger = page.getByTestId('tournaments-filter-organization');
    await expect(trigger).toContainText('All organizations');
    await trigger.click();
    const listbox = page.getByRole('listbox');
    await expect(listbox.getByRole('option', { name: 'All organizations' })).toBeVisible();
    await expect(listbox.getByRole('option', { name: 'My organizations' })).toHaveCount(0);
    await expect(listbox.getByRole('group')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('tournament-signups-open-badge')).toHaveCount(0);
  });

  test('@cicd archived tab lists past and stale tournaments of an organization', async ({
    page,
  }) => {
    await page.goto(`/tournaments?tab=archived&organization=${HOME_ORG}`);
    await waitForSettled(page, 'archived');
    const archived = panel(page, 'archived');

    await expect(cardNamed(archived, HOME_FINISHED)).toHaveCount(1, { timeout: 15000 });
    const stale = cardNamed(archived, HOME_STALE);
    await expect(stale).toHaveCount(1);
    await expect(stale.getByTestId('tournament-card-state')).toHaveText('Past (not closed)');
    await expect(cardNamed(archived, HOME_LIVE)).toHaveCount(0);
  });

  test('@cicd logged out shows no tier headings', async ({ page }) => {
    await page.goto('/tournaments');
    await waitForSettled(page, 'upcoming');
    await expect(panel(page, 'upcoming').locator(CARD_SELECTOR).first()).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByTestId('tournaments-tier-yours')).toHaveCount(0);
    await expect(page.getByTestId('tournaments-tier-others')).toHaveCount(0);
  });

  test('@cicd search narrows the upcoming list', async ({ page }) => {
    await page.goto('/tournaments');
    await waitForFilterRow(page);

    const card = await findTournamentCard(page, 'Discovery Away');
    await expect(card).toContainText(AWAY_CUP);

    const upcoming = panel(page, 'upcoming');
    await expect(upcoming.locator(CARD_SELECTOR)).toHaveCount(1);
    await expect(cardNamed(upcoming, HOME_SOON)).toHaveCount(0);
  });

  test('@cicd an invalid organization param renders the unfiltered list', async ({ page }) => {
    const urls = recordListRequests(page);
    await page.goto('/tournaments?organization=abc');
    await waitForSettled(page, 'upcoming');

    const upcoming = panel(page, 'upcoming');
    await expect(cardNamed(upcoming, HOME_SOON)).toHaveCount(1, { timeout: 15000 });
    await expect(cardNamed(upcoming, AWAY_CUP)).toHaveCount(1);
    await expect(page.getByTestId('tournaments-error-upcoming')).toHaveCount(0);
    expect(urls.filter((u) => new URL(u).searchParams.has('organization'))).toEqual([]);
  });

  test('@cicd an unknown tab param renders the Upcoming tab', async ({ page }) => {
    await page.goto('/tournaments?tab=bogus');
    await expect(page.getByTestId('tournaments-tab-upcoming')).toHaveAttribute(
      'aria-selected',
      'true',
      { timeout: 15000 },
    );
    await waitForSettled(page, 'upcoming');
    await expect(cardNamed(panel(page, 'upcoming'), HOME_SOON)).toHaveCount(1, {
      timeout: 15000,
    });
  });

  test('@cicd search and filters have accessible names', async ({ page }) => {
    await page.goto('/tournaments');
    await waitForFilterRow(page);

    await expect(page.getByRole('textbox', { name: 'Search tournaments' })).toBeVisible();
    await expect(page.getByRole('combobox', { name: /organization/i })).toBeVisible();
    await expect(page.getByRole('combobox', { name: /league/i })).toBeVisible();
  });

  test('@cicd load more requests the next page on its own origin and grows the grid', async ({
    page,
  }) => {
    const pageRequests: URL[] = [];
    await page.route('**/api/tournaments-list/**', async (route) => {
      const url = new URL(route.request().url());
      const pageNo = url.searchParams.get('page');
      if (pageNo === null) {
        await route.continue();
        return;
      }
      pageRequests.push(url);
      const response = await route.fetch({
        url: `${url.origin}${LIST_PATH}?bucket=archived&page=1&page_size=3`,
      });
      const body = (await response.json()) as { count: number; results: Tournament[] };
      const first = body.results;
      if (pageNo === '1') {
        await route.fulfill({
          response,
          json: {
            count: first.length * 2,
            next: 'http://other-host/api/tournaments-list/?bucket=archived&page=2',
            previous: null,
            results: first,
          },
        });
        return;
      }
      await route.fulfill({
        response,
        json: {
          count: first.length * 2,
          next: null,
          previous: 'http://other-host/api/tournaments-list/?bucket=archived&page=1',
          results: first.map((t, i) => ({
            ...t,
            pk: 990000 + i,
            name: `Load More Row ${i}`,
          })),
        },
      });
    });

    await page.goto('/tournaments?tab=archived');
    await waitForSettled(page, 'archived');
    const archived = panel(page, 'archived');
    const cards = archived.locator(CARD_SELECTOR);
    await expect(cards.first()).toBeVisible({ timeout: 15000 });
    const before = await cards.count();
    expect(before).toBeGreaterThan(0);

    const loadMore = page.getByTestId('tournaments-load-more');
    await expect(loadMore).toBeVisible();
    await loadMore.click();

    await expect(cards).toHaveCount(before * 2, { timeout: 15000 });
    await expect(cardNamed(archived, 'Load More Row 0')).toHaveCount(1);
    await expect(loadMore).toHaveCount(0);

    const second = pageRequests.find((u) => u.searchParams.get('page') === '2');
    expect(second, 'no page=2 request was sent').toBeDefined();
    expect(second!.origin).toBe(new URL(page.url()).origin);
    expect(second!.pathname).toBe(LIST_PATH);
    expect(second!.searchParams.get('bucket')).toBe('archived');
    expect(pageRequests.every((u) => u.hostname !== 'other-host')).toBe(true);
  });

  test.describe('as a site admin', () => {
    test.beforeEach(async ({ context }) => {
      await loginAdmin(context);
    });

    test('@cicd a tournament created through the API can be found and deleted from its card', async ({
      page,
      context,
    }) => {
      const name = `Discovery Delete ${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
      let pk: number | undefined;
      try {
        const res = await postWithCsrf(context, `${API_URL}/tournaments/`, {
          name,
          date_played: FAR_FUTURE_DATE,
          state: 'future',
          tournament_type: 'single_elimination',
          // perform_create reads `league`; the serializer writes `league_id_write`.
          league: HOME_LEAGUE,
          league_id_write: HOME_LEAGUE,
        });
        expect(res.ok(), await res.text()).toBe(true);
        pk = ((await res.json()) as { pk: number }).pk;

        await page.goto('/tournaments');
        await waitForFilterRow(page);
        await page.evaluate(() => {
          (window as Window & { __noReload?: boolean }).__noReload = true;
        });

        const card = await findTournamentCard(page, name);
        await expect(card).toHaveAttribute('data-testid', `tournament-card-${pk}`);

        await card.getByTestId(`tournament-delete-${pk}`).click();
        await page.getByRole('button', { name: 'Confirm Delete' }).click();

        await expect(cardNamed(page, name)).toHaveCount(0, { timeout: 15000 });
        await expect(page.getByTestId('tournaments-empty-upcoming')).toBeVisible();
        const noReload = await page.evaluate(
          () => (window as Window & { __noReload?: boolean }).__noReload,
        );
        expect(noReload).toBe(true);
      } finally {
        if (pk !== undefined) await deleteTournamentByPk(context, pk);
        await cleanupByName(context, name);
      }
    });

    test('@cicd creating through the modal never reloads the unbucketed list', async ({
      page,
      context,
    }) => {
      const name = `Discovery Modal ${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
      try {
        await page.goto('/tournaments');
        await waitForFilterRow(page);
        await waitForSettled(page, 'upcoming');
        const urls = recordListRequests(page);

        await page.getByTestId('tournament-create-button').click();
        const nameInput = page.getByTestId('tournament-name-input');
        await expect(nameInput).toBeVisible({ timeout: 10000 });
        await nameInput.fill(name);

        await page.getByTestId('tournament-type-select').click();
        await page.getByTestId('tournament-type-single').click();

        await page.getByTestId('tournament-date-picker').click();
        const calendar = page.locator('[data-slot="calendar"]');
        await expect(calendar).toBeVisible({ timeout: 5000 });
        await calendar.getByTestId('calendar-day-20').first().click();
        await expect(calendar).toBeHidden({ timeout: 5000 });

        await page.getByTestId('tournament-submit-button').click();
        await expect(nameInput).toBeHidden({ timeout: 15000 });

        await findTournamentCard(page, name);

        expect(urls.length).toBeGreaterThan(0);
        expect(urls.filter((u) => bucketOf(u) === null)).toEqual([]);
      } finally {
        await cleanupByName(context, name);
      }
    });
  });

  test('@cicd no horizontal overflow at 375 px with long filter values', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(`/tournaments?organization=${HOME_ORG}&league=${HOME_LEAGUE}`);
    await waitForFilterRow(page);
    await waitForSettled(page, 'upcoming');
    await expect(page.getByTestId('tournaments-filter-league')).toContainText('Discovery Home');
    await expect(cardNamed(panel(page, 'upcoming'), HOME_SOON)).toHaveCount(1, {
      timeout: 15000,
    });

    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  });
});
