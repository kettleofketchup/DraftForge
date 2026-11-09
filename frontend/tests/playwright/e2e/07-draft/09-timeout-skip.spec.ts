/**
 * Team draft timeout skip
 *
 * Tournament: 'draft_timer_skip' (timer-enabled, 20 s grace, 60 s reserve, 4 teams).
 * Serial: beforeAll readies every captain over HTTP and starts the draft as admin.
 * From test 1's skip onward the active round is captain B's and B never connected,
 * so captain A's closed pages cannot auto-pause it. Do not add steps that wait on the clock.
 */

import type { BrowserContext, Browser, Page } from '@playwright/test';
import {
  test,
  expect,
  loginAdmin,
  loginAsUser,
  resetTimerTournament,
  fetchTimerTournament,
  readyUp,
  startDraftAsStaff,
  expireDraftClock,
  captainsOf,
  openDraftModal,
  postWithCsrf,
  DraftWebSocketHelper,
  type TimerTournament,
} from '../../fixtures';
import { API_URL } from '../../fixtures/auth';

const KEY = 'draft_timer_skip';

function teamsInOrder(t: TimerTournament): TimerTournament['teams'] {
  return [...t.teams].sort((a, b) => a.draft_order - b.draft_order);
}

async function resetReadyAndStart(
  browser: Browser
): Promise<{ t: TimerTournament; admin: BrowserContext }> {
  const admin = await browser.newContext({ ignoreHTTPSErrors: true });
  await loginAdmin(admin);
  const t = await resetTimerTournament(admin, KEY);
  for (const captain of captainsOf(t)) {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await loginAsUser(ctx, captain);
      await readyUp(ctx, t.draft.pk);
    } finally {
      await ctx.close();
    }
  }
  await startDraftAsStaff(admin, t.draft.pk);
  return { t, admin };
}

test.describe.serial('Team draft timeout skip', () => {
  let t: TimerTournament;
  let admin: BrowserContext;
  let a: { context: BrowserContext; page: Page };

  test.beforeAll(async ({ browser }) => {
    ({ t, admin } = await resetReadyAndStart(browser));
  });

  test.afterAll(async () => {
    await a?.context.close().catch(() => undefined);
    await admin?.close().catch(() => undefined);
  });

  test('@cicd skipped captain lands on the new active round and sees the deferred copy', async ({
    browser,
  }) => {
    const [teamA, teamB] = teamsInOrder(t);

    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await loginAsUser(context, captainsOf(t)[0]);
    const page = await context.newPage();
    a = { context, page };
    const wsHelper = new DraftWebSocketHelper(page);
    await openDraftModal(page, t.pk);
    await expect(page.getByTestId('draft-clock-grace')).toBeVisible();

    const active = page.getByTestId('draft-clock-active-captain');
    const before = (await active.textContent()) ?? '';

    await expireDraftClock(admin, t.draft.pk, 90_000);

    await wsHelper.waitForToast(/ran out of time — .* is up, .* picks at #2/, 5_000);
    await expect(active).not.toHaveText(before, { timeout: 5_000 });
    await expect(
      page.locator('[data-testid^="upcoming-pick-"][data-pick-number="1"]')
    ).toHaveAttribute('data-team-pk', String(teamB.pk));
    await expect(
      page.locator('[data-testid^="upcoming-pick-"][data-pick-number="2"]')
    ).toHaveAttribute('data-team-pk', String(teamA.pk));
    await expect(page.getByTestId('pickDisabledNotYourTurn').first()).toBeVisible();
  });

  test('@cicd captain A navigating to their deferred round sees the deferred indicator, not YOUR turn', async () => {
    const { page } = a;
    await page.getByTestId('nextRoundButton').click();
    await expect(page.getByTestId('turn-indicator-deferred')).toContainText(
      /Pick #2 — deferred, .* picks after #1/
    );
    await expect(page.getByTestId('turn-indicator')).toHaveCount(0);

    await page.getByTestId('prevRoundButton').click();
    await expect(page.getByTestId('turn-indicator')).toContainText('Waiting for');
  });

  test('@cicd a pick against the deferred round is redirected (409 not_active_round)', async () => {
    const cur = await fetchTimerTournament(a.context, KEY);
    const deferred = cur.draft.draft_rounds.find((r) => r.pick_number === 2);
    expect(deferred).toBeDefined();

    const resp = await postWithCsrf(a.context, `${API_URL}/tournaments/pick_player`, {
      draft_round_pk: deferred!.pk,
      user_pk: cur.draft.users_remaining[0],
    });
    expect(resp.status()).toBe(409);
    const body = await resp.json();
    expect(body.code).toBe('not_active_round');
    expect(body.active_pick_number).toBe(1);
  });

  test('@cicd history shows the skip', async () => {
    const { page } = a;
    await page.getByTestId('draft-history-button').click();
    await expect(page.getByTestId('draft-event-history-title')).toBeVisible();
    await expect(page.getByTestId('draft-event-row-pick_timed_out').first()).toBeVisible();
    const skipped = page.getByTestId('draft-event-row-pick_skipped').first();
    await expect(skipped).toBeVisible();
    await expect(skipped.getByTestId('draft-event-text')).toHaveText(
      /ran out of time — .* is up, .* picks at #2$/
    );
  });
});
