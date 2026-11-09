/**
 * Shuffle draft timeout re-selection
 *
 * Tournament: 'shuffle_timer_skip' (timer-enabled, 20 s grace, 60 s reserve).
 * Serial: beforeAll readies every captain over HTTP and starts the draft as admin.
 * Only the skipped captain connects; the re-selected captain never does, so nothing auto-pauses.
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
  activeRound,
  openDraftModal,
  DraftWebSocketHelper,
  type TimerTournament,
} from '../../fixtures';

const KEY = 'shuffle_timer_skip';

test.use({ trace: 'on' }); // ci(tmp): measure burst handling on green runs

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

test.describe.serial('Shuffle draft timeout skip', () => {
  let t: TimerTournament;
  let admin: BrowserContext;
  let skipped: { context: BrowserContext; page: Page };

  test.beforeAll(async ({ browser }) => {
    ({ t, admin } = await resetReadyAndStart(browser));
  });

  test.afterAll(async () => {
    await skipped?.context.close().catch(() => undefined);
    await admin?.close().catch(() => undefined);
  });

  test('@cicd timeout re-selects a different captain for the same round', async ({
    browser,
  }) => {
    const before = activeRound(await fetchTimerTournament(admin, KEY));
    expect(before.captain).not.toBeNull();

    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await loginAsUser(context, before.captain!);
    const page = await context.newPage();
    skipped = { context, page };
    const wsHelper = new DraftWebSocketHelper(page);
    await openDraftModal(page, t.pk);

    const active = page.getByTestId('draft-clock-active-captain');
    await expect(active).toBeVisible();
    const name = (await active.textContent()) ?? '';

    await expireDraftClock(admin, t.draft.pk, 90_000);

    await wsHelper.waitForToast(/ran out of time — .* is up$/, 5_000);
    await expect(active).not.toHaveText(name, { timeout: 5_000 });
    // Every captain is 0 MMR, so the re-selection is a tie roll among the remaining teams.
    await expect(page.getByTestId('tie-resolution-overlay')).toBeVisible();
    await page.getByTestId('tie-resolution-continue').click();
    await expect(page.getByTestId('tie-resolution-overlay')).toHaveCount(0);

    const after = activeRound(await fetchTimerTournament(admin, KEY));
    expect(after.pk).toBe(before.pk);
    expect(after.captain).not.toBe(before.captain);
    expect(after.skip_count).toBe(1);

    await expect(page.getByTestId('pickDisabledNotYourTurn').first()).toBeVisible();
  });

  test('@cicd history lists the timeout events newest first', async () => {
    const { page } = skipped;
    await page.getByTestId('draft-history-button').click();
    await expect(page.getByTestId('draft-event-history-title')).toBeVisible();
    await expect(page.getByTestId('draft-event-text').first()).toBeVisible();

    const texts = await page.getByTestId('draft-event-text').allTextContents();
    const idx = (re: RegExp): number => texts.findIndex((s) => re.test(s));
    const timedOutIsUp = idx(/ran out of time — .* is up$/);
    const pickingNext = idx(/is picking next/);
    const ranOut = idx(/ran out of time on pick #/);

    expect(timedOutIsUp).toBeGreaterThanOrEqual(0);
    expect(pickingNext).toBeGreaterThanOrEqual(0);
    expect(ranOut).toBeGreaterThanOrEqual(0);
    expect(timedOutIsUp).toBeLessThan(pickingNext);
    expect(pickingNext).toBeLessThan(ranOut);
  });
});
