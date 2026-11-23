/**
 * Staff sign-up history (#497): the History tab, its member/action filters,
 * the per-row history Sheet, staff-only access and phone layout.
 *
 * Uses the isolated "Signup History Org" data (backend
 * tests.data.signup_history), rebuilt in beforeAll so reruns and retries
 * start from the seeded ledger. Tests run in file order; the last one mutates
 * the fixture (staff moves a member to the waitlist).
 */

import type { BrowserContext, Locator, Page } from '@playwright/test';
import { expect, test, visitAndWaitForHydration } from '../../fixtures';
import { loginAsUser } from '../../fixtures/auth';
import { API_URL } from '../../fixtures/base-url';
import {
  resetSignupHistoryData,
  type SignupHistoryData,
} from '../../fixtures/signup-history';

test.describe.configure({ mode: 'default' });

interface Subject {
  user_id: number | null;
  username: string | null;
  nickname: string | null;
  discordNickname: string | null;
  guildNickname: string | null;
}

interface HistoryEntry {
  id: number;
  action: string;
  subject: Subject;
}

interface Signup {
  id: number;
  user: number;
  status: string;
}

const PHONE = { width: 390, height: 844 };
const ROW_ID = /^signup-history-row-\d+$/;
const HISTORY_RESPONSE = /\/api\/events\/\d+\/signup-history\//;

let data: SignupHistoryData;
let names: Map<number, string>;

const nameOf = (s: Subject): string =>
  s.guildNickname ?? s.discordNickname ?? s.nickname ?? s.username ?? '?';

const escapeRe = (s: string): string =>
  s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function name(pk: number): string {
  const n = names.get(pk);
  if (!n) throw new Error(`no history subject for user ${pk}`);
  return n;
}

async function historyPage(
  context: BrowserContext,
  query = '',
): Promise<HistoryEntry[]> {
  const resp = await context.request.get(
    `${API_URL}/events/${data.event_pk}/signup-history/${query}`,
  );
  expect(resp.status()).toBe(200);
  return (await resp.json()).results as HistoryEntry[];
}

async function signups(context: BrowserContext): Promise<Signup[]> {
  const resp = await context.request.get(
    `${API_URL}/events/signups/?event=${data.event_pk}`,
  );
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  return (Array.isArray(body) ? body : body.results) as Signup[];
}

async function signupOf(context: BrowserContext, userPk: number) {
  const found = (await signups(context)).find((s) => s.user === userPk);
  if (!found) throw new Error(`no signup for user ${userPk}`);
  return found;
}

function rows(scope: Locator): Locator {
  return scope.getByTestId(ROW_ID);
}

function rowsWithAction(page: Page, scope: Locator, label: string): Locator {
  return rows(scope).filter({ has: page.getByText(label, { exact: true }) });
}

async function openTab(page: Page, tab: string) {
  const trigger = page.getByTestId(`event-tab-${tab}`);
  if (await trigger.isVisible()) {
    await trigger.click();
  } else {
    await page.getByTestId('page-nav-trigger').click();
    await page.getByTestId(`page-nav-${tab}`).click();
  }
}

async function openHistoryTab(page: Page): Promise<Locator> {
  const loaded = page.waitForResponse(
    (r) => HISTORY_RESPONSE.test(r.url()) && r.status() === 200,
  );
  await openTab(page, 'history');
  await loaded;
  const table = page.getByTestId('signup-history-table');
  await expect(table).toHaveAttribute('aria-busy', 'false', {
    timeout: 15000,
  });
  return table;
}

async function chooseFilter(
  page: Page,
  table: Locator,
  filter: 'member' | 'action',
  option: string,
  param: RegExp,
) {
  const filtered = page.waitForResponse(
    (r) => HISTORY_RESPONSE.test(r.url()) && param.test(r.url()) && r.ok(),
  );
  await page.getByTestId(`signup-history-${filter}-filter`).click();
  await page.getByRole('option', { name: option, exact: true }).click();
  await filtered;
  await expect(table).toHaveAttribute('aria-busy', 'false');
}

async function expectNoPageScroll(page: Page, where: string) {
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow, `horizontal page scroll on ${where}`).toBeLessThanOrEqual(0);
}

async function expectCellsFit(scope: Locator, where: string) {
  const all = rows(scope);
  const count = await all.count();
  expect(count, `rows in ${where}`).toBeGreaterThan(0);
  for (let i = 0; i < count; i++) {
    const clipped = await all.nth(i).evaluate((row) =>
      Array.from(row.querySelectorAll('td'))
        .filter((td) => td.scrollWidth > td.clientWidth)
        .map((td) => `${td.scrollWidth}>${td.clientWidth}`),
    );
    expect(clipped, `clipped cells in ${where} row ${i}`).toEqual([]);
  }
}

test.describe('Staff sign-up history (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    data = await resetSignupHistoryData(context);
    await loginAsUser(context, data.staff_pk);
    names = new Map();
    for (const entry of await historyPage(context, '?page_size=100')) {
      if (entry.subject.user_id != null) {
        names.set(entry.subject.user_id, nameOf(entry.subject));
      }
    }
    await context.close();
  });

  test.describe('as staff', () => {
    test.beforeEach(async ({ context }) => {
      await loginAsUser(context, data.staff_pk);
    });

    test('History tab lists entries with means badges and the staff reason', async ({
      page,
    }) => {
      await visitAndWaitForHydration(page, `/events/${data.event_pk}`);
      const table = await openHistoryTab(page);

      for (const label of [
        'Promoted from waitlist',
        'Withdrew',
        'Signed up again',
        'Added by staff',
      ]) {
        await expect(
          rowsWithAction(page, table, label),
          `${label} row`,
        ).toHaveCount(1);
      }

      const withdrew = rowsWithAction(page, table, 'Withdrew');
      await expect(withdrew).toContainText(name(data.withdrawer_pk));
      await expect(withdrew.getByTestId('signup-history-means')).toHaveText(
        'Web',
      );

      const staffAdd = rowsWithAction(page, table, 'Added by staff');
      await expect(staffAdd).toContainText(name(data.staff_added_pk));
      await expect(staffAdd.getByTestId('signup-history-means')).toHaveText(
        'Staff',
      );
      await expect(staffAdd.getByTestId('signup-history-reason')).toContainText(
        'captain confirmed availability',
      );

      const means = table.getByTestId('signup-history-means');
      for (const label of ['Discord button', 'Discord reaction', 'System']) {
        await expect(
          means.filter({ hasText: new RegExp(`^${label}$`) }).first(),
          `${label} badge`,
        ).toBeVisible();
      }

      const promoted = rowsWithAction(page, table, 'Promoted from waitlist');
      await expect(promoted).toContainText(name(data.promoted_pk));
      await expect(promoted.getByTestId('signup-history-cause')).toHaveText(
        `after ${name(data.withdrawer_pk)} withdrew`,
      );
    });

    test('member and action filters narrow the rows', async ({ page }) => {
      await visitAndWaitForHydration(page, `/events/${data.event_pk}`);
      const table = await openHistoryTab(page);

      await chooseFilter(
        page,
        table,
        'member',
        name(data.withdrawer_pk),
        new RegExp(`[?&]user=${data.withdrawer_pk}(&|$)`),
      );
      await expect(rows(table)).toHaveCount(3);
      for (const label of ['Signed up', 'Withdrew', 'Signed up again']) {
        await expect(rowsWithAction(page, table, label)).toHaveCount(1);
      }
      const memberRows = rows(table);
      for (let i = 0; i < 3; i++) {
        await expect(memberRows.nth(i)).toContainText(name(data.withdrawer_pk));
      }

      await page.getByTestId('signup-history-clear-filters').click();
      await expect(table).toHaveAttribute('aria-busy', 'false');

      await chooseFilter(
        page,
        table,
        'action',
        'Promoted from waitlist',
        /[?&]action=promoted(&|$)/,
      );
      await expect(rows(table)).toHaveCount(1);
      await expect(
        rowsWithAction(page, table, 'Promoted from waitlist'),
      ).toContainText(name(data.promoted_pk));
    });

    test('row history button opens a Sheet filtered to that member', async ({
      context,
      page,
    }) => {
      const signup = await signupOf(context, data.promoted_pk);
      await visitAndWaitForHydration(page, `/events/${data.event_pk}`);
      await openTab(page, 'signups');
      await expect(
        page.getByTestId(`event-signup-row-${signup.id}`),
      ).toBeVisible({ timeout: 10000 });

      const filtered = page.waitForResponse(
        (r) =>
          HISTORY_RESPONSE.test(r.url()) &&
          r.url().includes(`user=${data.promoted_pk}`) &&
          r.ok(),
      );
      await page
        .getByTestId(`signup-history-btn-user-${data.promoted_pk}`)
        .click();
      await filtered;

      const sheet = page.getByTestId('signup-history-sheet');
      await expect(sheet).toBeVisible();
      await expect(sheet).toContainText('Sign-up history');
      await expect(
        sheet.getByTestId('signup-history-member-filter'),
      ).toHaveCount(0);
      const sheetRows = rows(sheet);
      await expect(sheetRows.first()).toBeVisible();
      const count = await sheetRows.count();
      for (let i = 0; i < count; i++) {
        await expect(sheetRows.nth(i)).toContainText(name(data.promoted_pk));
      }

      // The withdrawal that caused it belongs to another member, so it is
      // not loaded here (spec §7.3).
      const promoted = rowsWithAction(page, sheet, 'Promoted from waitlist');
      await expect(promoted).toHaveCount(1);
      await expect(promoted.getByTestId('signup-history-cause')).toHaveText(
        'automatic',
      );

      const changeCell = promoted.locator('td', {
        has: page.getByTestId('signup-history-diff'),
      });
      const box = await changeCell.boundingBox();
      expect(box?.width ?? 0).toBeGreaterThan(200);
    });

    test('staff can read the history API', async ({ page }) => {
      const resp = await page.request.get(
        `${API_URL}/events/${data.event_pk}/signup-history/`,
      );
      expect(resp.status()).toBe(200);
    });
  });

  test('members get no History UI and a 403 from the API', async ({
    context,
    page,
  }) => {
    await loginAsUser(context, data.withdrawer_pk);
    const historyRequests: string[] = [];
    page.on('request', (r) => {
      if (HISTORY_RESPONSE.test(r.url())) historyRequests.push(r.url());
    });

    await visitAndWaitForHydration(page, `/events/${data.event_pk}`);
    await expect(page.getByTestId('event-tab-details')).toBeVisible();
    await expect(page.getByTestId('event-tab-history')).toHaveCount(0);
    await openTab(page, 'signups');
    await expect(
      page.locator('[data-testid^="signup-history-btn-"]'),
    ).toHaveCount(0);

    await visitAndWaitForHydration(page, `/events/${data.event_pk}/history`);
    await expect(page.getByTestId('event-tab-details')).toHaveAttribute(
      'data-state',
      'active',
    );
    await expect(page.getByTestId('signup-history-section')).toHaveCount(0);
    expect(historyRequests).toEqual([]);

    const resp = await page.request.get(
      `${API_URL}/events/${data.event_pk}/signup-history/`,
    );
    expect(resp.status()).toBe(403);
  });

  test('phone width: history, filters, signup rows and Sheet fit 390px', async ({
    context,
    page,
  }) => {
    await loginAsUser(context, data.staff_pk);
    const all = await signups(context);
    const rsvp = all.find(
      (s) => data.member_pks.includes(s.user) && s.status === 'rsvp',
    );
    const waitlisted = await signupOf(context, data.staff_added_pk);
    if (!rsvp) throw new Error('no RSVP fixture signup; run populate');
    expect(waitlisted.status).toBe('waitlisted');

    await page.setViewportSize(PHONE);
    await visitAndWaitForHydration(page, `/events/${data.event_pk}`);

    await page.getByTestId('page-nav-trigger').click();
    await expect(page.getByTestId('page-nav-history')).toBeVisible();
    await page.keyboard.press('Escape');

    const table = await openHistoryTab(page);
    await expectNoPageScroll(page, 'History tab');
    await expectCellsFit(table, 'History tab');
    const reason = table.getByTestId('signup-history-reason');
    await reason.scrollIntoViewIfNeeded();
    const box = await reason.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(PHONE.width);

    const longName = name(data.long_nick_pk);
    await chooseFilter(
      page,
      table,
      'member',
      longName,
      new RegExp(`[?&]user=${data.long_nick_pk}(&|$)`),
    );
    await expect(
      page.getByTestId('signup-history-member-filter'),
    ).toContainText(new RegExp(escapeRe(longName.slice(0, 12))));
    await expectNoPageScroll(page, 'long-nickname filter');
    await expectCellsFit(table, 'long-nickname filter');

    for (const [tab, signup] of [
      ['waitlist', waitlisted],
      ['signups', rsvp],
    ] as const) {
      await openTab(page, tab);
      const row = page.getByTestId(`event-signup-row-${signup.id}`);
      await expect(row).toBeVisible({ timeout: 10000 });
      await expectNoPageScroll(page, `${tab} tab`);
      await expect(row).toBeInViewport();
      await expect(
        page.getByTestId(`signup-history-btn-user-${signup.user}`),
      ).toBeInViewport({ ratio: 1 });
    }

    await page.getByTestId(`signup-history-btn-user-${rsvp.user}`).click();
    const sheet = page.getByTestId('signup-history-sheet');
    await expect(sheet).toBeVisible();
    await expect(rows(sheet).first()).toBeVisible({ timeout: 10000 });
    await expectNoPageScroll(page, 'history Sheet');
    await expectCellsFit(sheet, 'history Sheet');
    const last = rows(sheet).last();
    await last.scrollIntoViewIfNeeded();
    await expect(last).toBeInViewport();
  });

  // Mutates the fixture, so it runs last.
  test('a staff action adds a History row', async ({ context, page }) => {
    await loginAsUser(context, data.staff_pk);
    const candidates = await signups(context);
    const target = [data.discord_button_pk, data.promoted_pk]
      .map((pk) => candidates.find((s) => s.user === pk))
      .find((s) => s?.status === 'rsvp');
    if (!target) {
      throw new Error(
        'no RSVP fixture signup left to waitlist after the beforeAll reset',
      );
    }
    const before = (await historyPage(context, '?action=demoted')).length;

    await visitAndWaitForHydration(page, `/events/${data.event_pk}`);
    await openTab(page, 'signups');
    await expect(page.getByTestId(`event-signup-row-${target.id}`)).toBeVisible(
      { timeout: 10000 },
    );
    const demoted = page.waitForResponse(
      (r) => r.url().includes(`/signups/${target.id}/demote/`) && r.ok(),
    );
    await page.getByTestId(`waitlist-signup-${target.id}`).click();
    await demoted;

    const table = await openHistoryTab(page);
    const moved = rowsWithAction(page, table, 'Moved to waitlist');
    await expect(moved).toHaveCount(before + 1);
    await expect(moved.first()).toContainText(name(target.user));
    await expect(moved.first().getByTestId('signup-history-means')).toHaveText(
      'Staff',
    );
  });
});
