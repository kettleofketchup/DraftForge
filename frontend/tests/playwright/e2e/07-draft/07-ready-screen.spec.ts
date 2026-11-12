/**
 * Team draft ready screen (timer lobby)
 *
 * Tournament: 'draft_timer_ready' (timer-enabled, pending, 4 teams, test user = captain A).
 * Serial: later tests build on the ready state set in earlier ones.
 */

import type { Browser } from '@playwright/test';
import {
  test,
  expect,
  loginAsUser,
  resetTimerTournament,
  readyUp,
  captainsOf,
  openDraftModal,
  openCaptainPage,
  draftStateOf,
  type TimerTournament,
} from '../../fixtures';

const KEY = 'draft_timer_ready';

async function readyCaptains(
  browser: Browser,
  t: TimerTournament,
  indices: number[]
): Promise<void> {
  const captains = captainsOf(t);
  for (const i of indices) {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await loginAsUser(ctx, captains[i]);
      await readyUp(ctx, t.draft.pk);
    } finally {
      await ctx.close();
    }
  }
}

function teamsInOrder(t: TimerTournament): TimerTournament['teams'] {
  return [...t.teams].sort((a, b) => a.draft_order - b.draft_order);
}

test.describe.serial('Team draft ready screen', () => {
  let t: TimerTournament;

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      t = await resetTimerTournament(ctx, KEY);
    } finally {
      await ctx.close();
    }
  });

  test('@cicd captain toggles ready and unready', async ({ page, loginUser }) => {
    await loginUser();
    await openDraftModal(page, t.pk);
    await expect(page.getByTestId('draft-lobby')).toBeVisible();

    const myTeam = teamsInOrder(t)[0];
    const check = page.getByTestId(`lobby-ready-check-${myTeam.pk}`);
    const toggle = page.getByTestId('lobby-ready-toggle');
    const sent: boolean[] = [];
    page.on('request', (req) => {
      if (req.method() === 'POST' && /\/api\/draft\/\d+\/ready\/$/.test(req.url())) {
        sent.push(req.postDataJSON().ready);
      }
    });

    await expect(check).toHaveAttribute('data-state', 'not-ready');
    await toggle.click();
    await expect(check).toHaveAttribute('data-state', 'ready');
    await expect(toggle).toHaveText('Not ready');
    await toggle.click();
    await expect(check).toHaveAttribute('data-state', 'not-ready');
    await expect(toggle).toHaveText('Ready up');
    // A stale tournament refetch landing between the clicks flips the toggle back, so the
    // second click re-sends ready=true.
    expect(sent).toEqual([true, false]);
  });

  test('@cicd captain sees no start control', async ({ page, loginUser }) => {
    await loginUser();
    await openDraftModal(page, t.pk);
    await expect(page.getByTestId('draft-lobby')).toBeVisible();
    await expect(page.getByTestId('lobby-ready-toggle')).toBeVisible();
    await expect(page.getByTestId('lobby-start-button')).toHaveCount(0);
  });

  test('@cicd staff sees Force start while a captain is not ready, and the confirm lists them', async ({
    page,
    browser,
    loginAdmin,
  }) => {
    await readyCaptains(browser, t, [0, 1, 2]);

    await loginAdmin();
    await openDraftModal(page, t.pk);
    await expect(page.getByTestId('draft-lobby')).toBeVisible();

    const notReadyTeam = teamsInOrder(t)[3];
    await expect(page.getByTestId(`lobby-ready-check-${notReadyTeam.pk}`)).toHaveAttribute(
      'data-state',
      'not-ready'
    );

    const start = page.getByTestId('lobby-start-button');
    await expect(start).toHaveText('Force start');
    await start.click();

    const list = page.getByTestId('lobby-force-start-not-ready');
    await expect(list).toBeVisible();
    const row = page.getByTestId(`lobby-team-row-${notReadyTeam.pk}`);
    const rowText = (await row.innerText()).toLowerCase();
    const listed = (await list.innerText()).trim();
    expect(listed.length).toBeGreaterThan(0);
    expect(rowText).toContain(listed.toLowerCase());

    await page.keyboard.press('Escape');
    await expect(page.getByTestId('lobby-force-start-dialog')).toHaveCount(0);
  });

  test('@cicd staff sees Start draft once everyone is ready', async ({
    page,
    browser,
    loginAdmin,
  }) => {
    await readyCaptains(browser, t, [3]);

    await loginAdmin();
    await openDraftModal(page, t.pk);
    await expect(page.getByTestId('lobby-start-button')).toHaveText('Start draft');
  });

  test('@cicd Start draft emits draft_started_by_staff and shows the clock', async ({
    page,
    context,
    browser,
    loginAdmin,
  }) => {
    // Pick #1 is captain A's; their page must stay connected or the draft auto-pauses.
    const a = await openCaptainPage(browser, captainsOf(t)[0], t.pk);
    try {
      await expect(a.page.getByTestId('draft-lobby')).toBeVisible();

      await loginAdmin();
      await openDraftModal(page, t.pk);
      await page.getByTestId('lobby-start-button').click();

      await expect(page.getByTestId('draft-lobby')).toBeHidden();
      await expect(page.getByTestId('draft-clock-bar')).toBeVisible();
      await expect(page.getByTestId('draft-clock-grace')).toHaveText(/0:(1[5-9]|20)/, {
        timeout: 5_000,
      });

      await expect.poll(() => draftStateOf(context, KEY)).toBe('drafting');
      await expect(page.getByTestId('draft-paused-overlay')).toHaveCount(0);
      await expect(a.page.getByTestId('draft-paused-overlay')).toHaveCount(0);

      await page.getByTestId('draft-history-button').click();
      await expect(page.getByTestId('draft-event-history-title')).toBeVisible();
      await expect(
        page.getByTestId('draft-event-row-draft_started_by_staff').first().getByTestId('draft-event-text')
      ).toContainText('Draft started by');
    } finally {
      await a.context.close();
    }
  });

  test('@cicd Force start emits draft_force_started', async ({ page, browser, loginAdmin }) => {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    let fresh: TimerTournament;
    try {
      fresh = await resetTimerTournament(ctx, KEY);
    } finally {
      await ctx.close();
    }
    await readyCaptains(browser, fresh, [0, 1]);

    await loginAdmin();
    await openDraftModal(page, fresh.pk);
    await expect(page.getByTestId('lobby-start-button')).toHaveText('Force start');
    await page.getByTestId('lobby-start-button').click();
    await page.getByTestId('lobby-force-start-confirm').click();

    await expect(page.getByTestId('draft-lobby')).toBeHidden();
    await page.getByTestId('draft-history-button').click();
    await expect(
      page.getByTestId('draft-event-row-draft_force_started').first().getByTestId('draft-event-text')
    ).toContainText(/force-started by .* \(2 not ready\)/);
  });
});
