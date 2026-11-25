/**
 * MMR update requests (#750): a member requests an org or league MMR change
 * with a screenshot, staff approve or reject it, staff set an official value
 * from the edit modal, and a private org's MMR stays hidden from outsiders.
 *
 * Uses the isolated "MMR Requests" org/league (backend tests.data.mmr_requests).
 * Each test resets the member it drives.
 */

import type { Browser, BrowserContext, Page } from '@playwright/test';
import {
  expect,
  loginAsUser,
  openEditModal,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import {
  getMmrRequestsData,
  MMR_SCREENSHOT_PATH,
  resetMmrRequests,
  type MmrRequestsData,
} from '../../fixtures/mmr-requests';

let data: MmrRequestsData;

interface Session {
  context: BrowserContext;
  page: Page;
}

async function sessionAs(browser: Browser, userPk: number): Promise<Session> {
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  await loginAsUser(context, userPk);
  return { context, page: await context.newPage() };
}

async function openMmrTab(page: Page, userPk: number): Promise<void> {
  await visitAndWaitForHydration(page, `/user/${userPk}?tab=leagues`);
  await expect(page.getByTestId('mmr-tab')).toBeVisible({ timeout: 15000 });
}

async function submitRequest(
  page: Page,
  requestBtnTestId: string,
  value: number,
  note: string,
): Promise<number> {
  await page.getByTestId(requestBtnTestId).click();
  const dialog = page.getByTestId('mmr-request-dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByTestId('mmr-request-value').fill(String(value));
  await dialog
    .getByTestId('mmr-screenshot-input')
    .setInputFiles(MMR_SCREENSHOT_PATH);
  await expect(dialog.getByTestId('mmr-screenshot-preview')).toBeVisible();
  await dialog.getByTestId('mmr-request-note').fill(note);

  const created = page.waitForResponse(
    (resp) =>
      resp.request().method() === 'POST' &&
      /\/api\/mmr-requests\/$/.test(resp.url()),
  );
  await dialog.getByTestId('mmr-request-submit').click();
  const resp = await created;
  expect(resp.status()).toBe(201);
  const id = ((await resp.json()) as { id: number }).id;
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId(`mmr-pending-${id}`)).toContainText(
    String(value),
  );
  return id;
}

async function openOrgQueue(page: Page, orgPk: number): Promise<void> {
  await visitAndWaitForHydration(page, `/organizations/${orgPk}`);
  const tab = page.getByTestId('org-tab-mmr-requests');
  await expect(tab).toBeVisible({ timeout: 15000 });
  await tab.click();
  await expect(page.getByTestId('mmr-requests-tab')).toBeVisible();
}

async function approveCard(page: Page, id: number): Promise<void> {
  const card = page.getByTestId(`mmr-card-${id}`);
  await expect(card).toBeVisible({ timeout: 15000 });
  await card.getByTestId(`mmr-approve-btn-${id}`).click();
  const dialog = page.getByTestId('mmr-approve-dialog');
  await expect(dialog).toBeVisible();
  const approved = page.waitForResponse(
    (resp) =>
      resp.request().method() === 'POST' &&
      resp.url().includes(`/api/mmr-requests/${id}/approve/`),
  );
  await dialog.getByTestId('mmr-approve-confirm').click();
  expect((await approved).status()).toBe(200);
  await expect(page.getByTestId(`mmr-card-${id}`)).toBeHidden();
}

test.describe('MMR update requests (@cicd)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    data = await getMmrRequestsData(context);
    await context.close();
  });

  test.afterAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await resetMmrRequests(context, data.users.member_approve.pk);
    await context.close();
  });

  test('member requests, staff approves, profile shows official', async ({
    browser,
    context,
  }) => {
    const member = data.users.member_approve;
    const orgPk = data.org.pk;
    const dota = data.game_types.dota2;
    await resetMmrRequests(context, member.pk);

    const m = await sessionAs(browser, member.pk);
    const s = await sessionAs(browser, data.users.org_staff.pk);
    try {
      await openMmrTab(m.page, member.pk);
      const row = m.page.getByTestId(`mmr-row-org-${orgPk}-${dota}`);
      await expect(row).toContainText(String(data.base_mmr));
      await expect(row.getByTestId('mmr-badge-unverified')).toBeVisible();

      const id = await submitRequest(
        m.page,
        `mmr-request-btn-org-${orgPk}-${dota}`,
        4800,
        'Climbed this season',
      );
      await expect(row.getByTestId('mmr-badge-pending')).toBeVisible();

      await openOrgQueue(s.page, orgPk);
      await expect(s.page.getByTestId('org-tab-mmr-requests-count')).toHaveText(
        /^[1-9]\d*$/,
      );
      const card = s.page.getByTestId(`mmr-card-${id}`);
      await expect(card).toBeVisible({ timeout: 15000 });
      await expect(card.getByTestId(`mmr-card-mmrs-${id}`)).toContainText(
        '4800',
      );
      await expect(card.getByTestId(`mmr-card-note-${id}`)).toContainText(
        'Climbed this season',
      );
      const thumb = card
        .getByTestId(`mmr-card-screenshot-${id}`)
        .locator('img');
      await thumb.scrollIntoViewIfNeeded();
      await expect
        .poll(() => thumb.evaluate((el: HTMLImageElement) => el.naturalWidth), {
          timeout: 10000,
        })
        .toBeGreaterThan(0);

      await approveCard(s.page, id);

      await openMmrTab(m.page, member.pk);
      const after = m.page.getByTestId(`mmr-row-org-${orgPk}-${dota}`);
      await expect(after).toContainText('4800');
      await expect(after.getByTestId('mmr-badge-official')).toBeVisible();
      await expect(after.getByTestId('mmr-badge-pending')).toHaveCount(0);
    } finally {
      await m.context.close();
      await s.context.close();
    }
  });

  test('staff rejects with a reason', async ({ browser, context }) => {
    const member = data.users.member_reject;
    const orgPk = data.org.pk;
    const dota = data.game_types.dota2;
    await resetMmrRequests(context, member.pk);

    const m = await sessionAs(browser, member.pk);
    const s = await sessionAs(browser, data.users.org_staff.pk);
    try {
      await openMmrTab(m.page, member.pk);
      const id = await submitRequest(
        m.page,
        `mmr-request-btn-org-${orgPk}-${dota}`,
        4600,
        'Please update',
      );

      await openOrgQueue(s.page, orgPk);
      const card = s.page.getByTestId(`mmr-card-${id}`);
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.getByTestId(`mmr-reject-btn-${id}`).click();
      await s.page.getByTestId('mmr-reject-reason').fill('Blurry screenshot');
      const rejected = s.page.waitForResponse(
        (resp) =>
          resp.request().method() === 'POST' &&
          resp.url().includes(`/api/mmr-requests/${id}/reject/`),
      );
      await s.page.getByTestId('mmr-reject-confirm').click();
      expect((await rejected).status()).toBe(200);
      await expect(card).toBeHidden();

      await openMmrTab(m.page, member.pk);
      const row = m.page.getByTestId(`mmr-row-org-${orgPk}-${dota}`);
      await expect(row).toContainText(String(data.base_mmr));
      await expect(row.getByTestId('mmr-badge-unverified')).toBeVisible();
      await expect(m.page.getByTestId(`mmr-last-decision-${id}`)).toContainText(
        'Blurry screenshot',
      );
    } finally {
      await m.context.close();
      await s.context.close();
    }
  });

  test('staff sets official from the edit modal', async ({
    browser,
    context,
  }) => {
    const member = data.users.member_staffset;
    const orgPk = data.org.pk;
    const dota = data.game_types.dota2;
    await resetMmrRequests(context, member.pk);

    const s = await sessionAs(browser, data.users.org_staff.pk);
    const m = await sessionAs(browser, member.pk);
    try {
      await visitAndWaitForHydration(s.page, `/organizations/${orgPk}`);
      await s.page.getByTestId('org-tab-users').click();
      const userCard = s.page.getByTestId(`usercard-${member.username}`);
      await expect(userCard).toBeVisible({ timeout: 15000 });
      await openEditModal(s.page, userCard);
      await s.page.getByTestId('set-official-mmr-btn').click();

      const dialog = s.page.getByTestId('set-official-mmr-dialog');
      await expect(dialog).toBeVisible();
      await dialog.getByTestId(`set-official-mmr-target-org-${dota}`).click();
      await dialog.getByTestId('set-official-mmr-value').fill('5100');
      const setResp = s.page.waitForResponse(
        (resp) =>
          resp.request().method() === 'POST' &&
          resp
            .url()
            .includes(`/api/organizations/${orgPk}/mmr-requests/staff-set/`),
      );
      await dialog.getByTestId('set-official-mmr-submit').click();
      expect((await setResp).status()).toBe(201);
      await expect(dialog).toBeHidden();

      await openMmrTab(m.page, member.pk);
      const row = m.page.getByTestId(`mmr-row-org-${orgPk}-${dota}`);
      await expect(row).toContainText('5100');
      await expect(row.getByTestId('mmr-badge-official')).toBeVisible();
    } finally {
      await s.context.close();
      await m.context.close();
    }
  });

  test('league staff approves a league request', async ({
    browser,
    context,
  }) => {
    const member = data.users.member_reject;
    const leaguePk = data.league.pk;
    await resetMmrRequests(context, member.pk);

    const m = await sessionAs(browser, member.pk);
    const s = await sessionAs(browser, data.users.league_staff.pk);
    try {
      await openMmrTab(m.page, member.pk);
      const row = m.page.getByTestId(`mmr-row-league-${leaguePk}`);
      await expect(row).toContainText(String(data.base_mmr));
      const id = await submitRequest(
        m.page,
        `mmr-request-btn-league-${leaguePk}`,
        4500,
        'League placement',
      );

      await visitAndWaitForHydration(s.page, `/leagues/${leaguePk}`);
      const tab = s.page.getByTestId('league-tab-mmr-requests');
      await expect(tab).toBeVisible({ timeout: 15000 });
      await tab.click();
      await approveCard(s.page, id);

      await openMmrTab(m.page, member.pk);
      const after = m.page.getByTestId(`mmr-row-league-${leaguePk}`);
      await expect(after).toContainText('4500');
      await expect(after.getByTestId('mmr-badge-official')).toBeVisible();
    } finally {
      await m.context.close();
      await s.context.close();
    }
  });

  test('outsider does not see private org MMR', async ({
    browser,
    context,
  }) => {
    const member = data.users.member_approve;
    const orgPk = data.org.pk;
    const leaguePk = data.league.pk;
    const dota = data.game_types.dota2;
    const orgRows = `[data-testid^="mmr-row-org-${orgPk}-"]`;
    await resetMmrRequests(context, member.pk);

    const fellow = await sessionAs(browser, data.users.member_reject.pk);
    const o = await sessionAs(browser, data.users.outsider.pk);
    try {
      await openMmrTab(fellow.page, member.pk);
      await expect(
        fellow.page.getByTestId(`mmr-row-org-${orgPk}-${dota}`),
      ).toContainText(String(data.base_mmr));
      await expect(
        fellow.page.getByTestId(`mmr-request-btn-org-${orgPk}-${dota}`),
      ).toHaveCount(0);

      await resetMmrRequests(context, member.pk, { membersPrivate: true });

      await openMmrTab(fellow.page, member.pk);
      await expect(
        fellow.page.getByTestId(`mmr-row-league-${leaguePk}`),
      ).toContainText(String(data.base_mmr));
      await expect(fellow.page.locator(orgRows)).toHaveCount(0);

      await visitAndWaitForHydration(o.page, `/user/${member.pk}?tab=leagues`);
      await expect(o.page.getByText('No public org memberships')).toBeVisible({
        timeout: 15000,
      });
      await expect(o.page.locator(orgRows)).toHaveCount(0);
      await expect(
        o.page.getByTestId(`mmr-row-league-${leaguePk}`),
      ).toHaveCount(0);
    } finally {
      await fellow.context.close();
      await o.context.close();
    }
  });
});
