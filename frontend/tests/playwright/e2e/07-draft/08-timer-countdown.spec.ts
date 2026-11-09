/**
 * Team draft timer countdown and undo reactivation
 *
 * Tournament: 'draft_timer_countdown' (timer-enabled, 20 s grace, 60 s reserve, 4 teams).
 * Serial: beforeAll readies every captain over HTTP and starts the draft as admin, so
 * the clock is already running and no captain has connected. Each test that leaves the
 * clock running must end by picking or pausing.
 */

import type { BrowserContext, Browser } from '@playwright/test';
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
  staffPick,
  activeRound,
  captainsOf,
  openCaptainPage,
  openDraftModal,
  draftStateOf,
  type TimerTournament,
} from '../../fixtures';

const KEY = 'draft_timer_countdown';

function parseClock(text: string | null): number {
  const match = /^(\d+):(\d{2})$/.exec((text ?? '').trim());
  if (!match) throw new Error(`unparseable clock: ${text}`);
  return Number(match[1]) * 60 + Number(match[2]);
}

function teamsInOrder(t: TimerTournament): TimerTournament['teams'] {
  return [...t.teams].sort((a, b) => a.draft_order - b.draft_order);
}

async function resetReadyAndStart(browser: Browser): Promise<TimerTournament> {
  const admin = await browser.newContext({ ignoreHTTPSErrors: true });
  try {
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
    return t;
  } finally {
    await admin.close();
  }
}

test.describe.serial('Team draft timer countdown', () => {
  let t: TimerTournament;
  let a: { context: BrowserContext; page: import('@playwright/test').Page };

  test.beforeAll(async ({ browser }) => {
    t = await resetReadyAndStart(browser);
  });

  test.afterAll(async () => {
    await a?.context.close().catch(() => undefined);
  });

  test('@cicd grace counts down and reserve stays full before grace ends', async ({ browser }) => {
    a = await openCaptainPage(browser, captainsOf(t)[0], t.pk);
    const grace = a.page.getByTestId('draft-clock-grace');
    await expect(grace).toBeVisible();

    const first = parseClock(await grace.textContent());
    await a.page.waitForTimeout(1_500);
    await expect
      .poll(async () => parseClock(await grace.textContent()))
      .toBeLessThan(first);

    const teamA = teamsInOrder(t)[0];
    await expect(a.page.getByTestId(`draft-clock-reserve-${teamA.pk}`)).toHaveText('1:00');
    await expect(a.page.getByTestId('draft-clock-your-turn')).toBeVisible();
    await expect(a.page.getByTestId('turn-indicator')).toContainText('YOUR turn');
  });

  test('@cicd spectator sees the same clock', async ({ page, loginAdmin: login }) => {
    await login();
    await openDraftModal(page, t.pk);

    const spectator = page.getByTestId('draft-clock-grace');
    const captain = a.page.getByTestId('draft-clock-grace');
    await expect(spectator).toBeVisible();
    const s = parseClock(await spectator.textContent());
    const c = parseClock(await captain.textContent());
    expect(Math.abs(s - c)).toBeLessThanOrEqual(1);

    await expect(page.getByTestId('draft-paused-overlay')).toHaveCount(0);
    await expect(a.page.getByTestId('draft-paused-overlay')).toHaveCount(0);
  });

  test('@cicd a pick restarts the clock for the next captain', async () => {
    const active = a.page.getByTestId('draft-clock-active-captain');
    const before = (await active.textContent()) ?? '';

    await a.page.getByTestId('pickPlayerButton').first().click();
    await a.page.getByTestId('confirmPickButton').click();

    await expect(active).not.toHaveText(before);
    await expect(a.page.getByTestId('draft-clock-grace')).toHaveText(/^0:(1\d|20)$/);
    await a.context.close();
  });

  test('@cicd reserve burns for the active team only after grace', async ({
    page,
    context,
    loginAdmin: login,
  }) => {
    await login();
    await openDraftModal(page, t.pk);
    await expect(page.getByTestId('draft-clock-grace')).toBeVisible();

    const [teamA, teamB] = teamsInOrder(t);
    await expireDraftClock(context, t.draft.pk, 18_000);

    await expect(page.getByTestId('draft-clock-grace')).toHaveText('0:00', { timeout: 6_000 });
    await expect(page.getByTestId(`draft-clock-reserve-${teamB.pk}`)).not.toHaveText('1:00', {
      timeout: 6_000,
    });
    await expect(page.getByTestId(`draft-clock-reserve-${teamA.pk}`)).toHaveText('1:00');

    const cur = await fetchTimerTournament(context, KEY);
    await staffPick(context, activeRound(cur).pk, cur.draft.users_remaining[0]);
  });

  test('@cicd staff undo of the final pick returns the draft to drafting with a running clock', async ({
    page,
    context,
    browser,
    loginAdmin: login,
  }) => {
    test.setTimeout(120_000);
    t = await resetReadyAndStart(browser);
    await login();

    for (let i = 0; i < 16; i++) {
      const cur = await fetchTimerTournament(context, KEY);
      expect(cur.draft.state).toBe('drafting');
      await staffPick(context, activeRound(cur).pk, cur.draft.users_remaining[0]);
    }

    await openDraftModal(page, t.pk);
    await expect(page.getByTestId('completed-team-draft-view')).toBeVisible();

    await page.getByTestId('undoPickButton').filter({ visible: true }).click();
    await page.getByTestId('confirmUndoPickButton').click();

    await expect(page.getByTestId('draft-clock-bar')).toBeVisible();
    await expect(page.getByTestId('draft-clock-grace')).not.toHaveText('0:00');
    await expect(page.getByTestId('draft-paused-overlay')).toHaveCount(0);
    await expect.poll(() => draftStateOf(context, KEY)).toBe('drafting');
  });
});
