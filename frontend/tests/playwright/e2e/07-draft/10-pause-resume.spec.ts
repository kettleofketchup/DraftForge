/**
 * Team draft pause / resume and stale-heartbeat auto-pause
 *
 * Tournament: 'draft_timer_pause' (timer-enabled, 120 s grace, 30 s reserve, 4 teams).
 * Serial: beforeAll readies every captain over HTTP and starts the draft as admin; pick #1
 * is captain A's for tests 1-4. A's round only runs between pauses, well under the 150 s budget.
 * The 12 s hold in test 4 is the one fixed wait: "never pauses" needs elapsed time.
 */

import type { Browser, BrowserContext, Page } from '@playwright/test';
import {
  test,
  expect,
  loginAdmin,
  loginAsUser,
  resetTimerTournament,
  fetchTimerTournament,
  readyUp,
  startDraftAsStaff,
  resumeDraftAsStaff,
  staleDraftHeartbeat,
  suppressDraftHeartbeats,
  captainsOf,
  activeRound,
  openCaptainPage,
  openDraftModal,
  draftStateOf,
  type TimerTournament,
} from '../../fixtures';

const KEY = 'draft_timer_pause';

function parseClock(text: string | null): number {
  const match = /^(\d+):(\d{2})$/.exec((text ?? '').trim());
  if (!match) throw new Error(`unparseable clock: ${text}`);
  return Number(match[1]) * 60 + Number(match[2]);
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

test.describe.serial('Team draft pause and resume', () => {
  let t: TimerTournament;
  let admin: BrowserContext;
  let staffPage: Page;
  let captainA: number;
  let captainB: number;

  async function ensureDrafting(): Promise<void> {
    if ((await draftStateOf(admin, KEY)) === 'paused') {
      await resumeDraftAsStaff(admin, t.draft.pk);
    }
    await expect.poll(() => draftStateOf(admin, KEY), { timeout: 8_000 }).toBe('drafting');
  }

  test.beforeAll(async ({ browser }) => {
    ({ t, admin } = await resetReadyAndStart(browser));
    [captainA, captainB] = captainsOf(t);
    staffPage = await admin.newPage();
    await openDraftModal(staffPage, t.pk);
  });

  test.afterAll(async () => {
    await admin?.close().catch(() => undefined);
  });

  test('@cicd manual pause freezes the clock and resume counts down', async ({ browser }) => {
    // precondition: no captain page open
    const a = await openCaptainPage(browser, captainA, t.pk);
    try {
      const grace = a.page.getByTestId('draft-clock-grace');
      await expect(grace).toBeVisible();

      await a.page.getByTestId('draft-clock-pause-button').click();
      await expect(a.page.getByTestId('draft-paused-overlay')).toBeVisible();
      await expect(a.page.getByTestId('draft-paused-message')).toHaveText(
        'Paused by captain or staff'
      );

      const first = await grace.textContent();
      await a.page.waitForTimeout(1_500);
      expect(await grace.textContent()).toBe(first);

      await a.page.getByTestId('draft-resume-button').click();
      await expect(a.page.getByTestId('draft-resuming-countdown')).toBeVisible();
      await expect(a.page.getByTestId('draft-resuming-countdown')).toContainText('Resuming in 3');
      await expect(a.page.getByTestId('draft-paused-overlay')).toHaveCount(0, { timeout: 5_000 });

      const resumed = parseClock(await grace.textContent());
      await expect
        .poll(async () => parseClock(await grace.textContent()))
        .toBeLessThan(resumed);
    } finally {
      await a.context.close();
    }
  });

  test('@cicd stale heartbeat pauses only for the active captain and disables Resume until they are back', async ({
    browser,
  }) => {
    // precondition: captain pages closed; staff page open
    await staleDraftHeartbeat(admin, t.draft.pk, captainA, 'delete');

    await expect(staffPage.getByTestId('draft-paused-overlay')).toBeVisible({ timeout: 4_000 });
    await expect(staffPage.getByTestId('draft-paused-message')).toHaveText(
      / is disconnected — pick for them or wait$/
    );
    await expect(staffPage.getByTestId('draft-resume-button')).toBeDisabled();
    await expect(staffPage.getByTestId('draft-pick-for-captain-button')).toBeVisible();

    await staffPage.getByTestId('draft-history-button').click();
    await expect(
      staffPage
        .getByTestId('draft-event-row-draft_paused')
        .first()
        .getByTestId('draft-event-text')
    ).toHaveText(/Draft paused — .* disconnected/);
    await staffPage.keyboard.press('Escape');
    await expect(staffPage.getByTestId('draft-event-row-draft_paused')).toHaveCount(0);
    await expect(staffPage.getByTestId('close-draft-modal')).toBeVisible();
    await expect(staffPage.getByTestId('draft-paused-overlay')).toBeVisible();

    const a = await openCaptainPage(browser, captainA, t.pk);
    try {
      await expect(staffPage.getByTestId('draft-resume-button')).toBeEnabled({ timeout: 5_000 });
      await staffPage.getByTestId('draft-resume-button').click();
      await expect(staffPage.getByTestId('draft-paused-overlay')).toHaveCount(0, {
        timeout: 8_000,
      });
      await expect(a.page.getByTestId('draft-paused-overlay')).toHaveCount(0, { timeout: 8_000 });
    } finally {
      await a.context.close();
    }
  });

  test("@cicd Resume stays disabled while the captain's socket is open but heartbeats stop", async ({
    browser,
  }) => {
    // precondition: captain pages closed; may already be auto-paused for A, which is equally valid
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await loginAsUser(context, captainA);
      const page = await context.newPage();
      const hb = await suppressDraftHeartbeats(page);
      await openDraftModal(page, t.pk);

      await staleDraftHeartbeat(admin, t.draft.pk, captainA, 'delete');

      await expect(staffPage.getByTestId('draft-paused-overlay')).toBeVisible({ timeout: 4_000 });
      await expect(staffPage.getByTestId('draft-resume-button')).toBeDisabled();

      hb.resume();
      await expect(staffPage.getByTestId('draft-resume-button')).toBeEnabled({ timeout: 6_000 });
      await staffPage.getByTestId('draft-resume-button').click();
      await expect(staffPage.getByTestId('draft-paused-overlay')).toHaveCount(0, {
        timeout: 8_000,
      });
    } finally {
      await context.close();
    }
  });

  test('@cicd a non-active captain going stale does not pause', async ({ browser }) => {
    // precondition: captain A page open for the whole test; B has connected and left
    const a = await openCaptainPage(browser, captainA, t.pk);
    try {
      await ensureDrafting();

      const b = await openCaptainPage(browser, captainB, t.pk);
      try {
        await expect(b.page.getByTestId('draft-clock-bar')).toBeVisible();
      } finally {
        await b.context.close();
      }

      await staleDraftHeartbeat(admin, t.draft.pk, captainB, 'delete');

      for (let i = 0; i < 12; i++) {
        expect(await draftStateOf(admin, KEY)).toBe('drafting');
        await a.page.waitForTimeout(1_000);
      }
      await expect(a.page.getByTestId('draft-paused-overlay')).toHaveCount(0);
    } finally {
      await a.context.close();
    }
  });

  test('@cicd staff picks for a disconnected captain during the pause', async () => {
    // precondition: captain pages closed
    const before = activeRound(await fetchTimerTournament(admin, KEY));

    await staleDraftHeartbeat(admin, t.draft.pk, captainA, 'delete');
    await expect(staffPage.getByTestId('draft-paused-overlay')).toBeVisible({ timeout: 12_000 });

    await staffPage.getByTestId('draft-pick-for-captain-button').click();
    await expect(staffPage.getByTestId('draft-paused-overlay')).toHaveCount(0);
    await expect(staffPage.getByTestId('draft-paused-banner')).toBeVisible();

    await staffPage.getByTestId('pickPlayerButton').first().click();
    await staffPage.getByTestId('confirmPickButton').click();

    await expect
      .poll(async () => {
        const cur = await fetchTimerTournament(admin, KEY);
        const picked = cur.draft.draft_rounds.find((r) => r.pk === before.pk);
        const next = activeRound(cur);
        return {
          picked: picked?.choice != null,
          state: cur.draft.state,
          nextStartedAt: next.pk !== before.pk ? next.started_at ?? null : 'same-round',
        };
      })
      .toEqual({ picked: true, state: 'paused', nextStartedAt: null });
  });
});
