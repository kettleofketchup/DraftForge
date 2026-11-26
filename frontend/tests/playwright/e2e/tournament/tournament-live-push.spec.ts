/**
 * Tournament writes reach other open browsers through the tournament
 * WebSocket (issue #964), not through polling.
 *
 * Admin A sets a winner and renames a team over the API; viewers B1 (bracket)
 * and B2 (teams) are anonymous contexts with the page open. The rename is
 * checked on the teams view; on the bracket view the spec checks that the
 * push refetched the bracket, since the bracket payload's team names are
 * cached server-side (issue #962). Each viewer's
 * clock is paused right after one of its polls, and the assertions only let
 * fake time run for well under a poll interval, so no poll can fire: an
 * update that lands came from the socket.
 */

import type { Browser, BrowserContext, Page } from '@playwright/test';
import { expect, loginAdmin, postWithCsrf, test } from '../../fixtures';
import { API_URL, BASE_URL } from '../../fixtures/base-url';
import { getCsrfToken } from '../../fixtures/events';

/**
 * Fake time a viewer may run per assertion. With the 1s pause margin this
 * stays well under the 5s bracket and 10s tournament polls.
 */
const PUSH_BUDGET_MS = 1_500;

type Viewer = {
  context: BrowserContext;
  page: Page;
  frames: string[];
  /** Paths of the viewer's GET requests. */
  gets: string[];
  /** frames.length and gets.length when the viewer's clock was last paused. */
  since: { frames: number; gets: number };
};

let tournamentPk = 0;
let teamPks: number[] = [];
let gamePk = 0;

async function expectOk(
  resp: import('@playwright/test').APIResponse,
): Promise<void> {
  expect(resp.ok(), `${resp.status()} ${await resp.text()}`).toBe(true);
}

async function createTournament(context: BrowserContext): Promise<void> {
  const name = `E2E Live Push ${Date.now()}`;
  const tournamentResp = await postWithCsrf(
    context,
    `${API_URL}/tournament/register`,
    {
      name,
      date_played: new Date().toISOString().slice(0, 10),
      tournament_type: 'single_elimination',
    },
  );
  await expectOk(tournamentResp);
  tournamentPk = (await tournamentResp.json()).pk;

  teamPks = [];
  for (const teamName of ['Push Radiant', 'Push Dire']) {
    const teamResp = await postWithCsrf(context, `${API_URL}/team/register`, {
      name: `${teamName} ${tournamentPk}`,
      tournament_id: tournamentPk,
    });
    await expectOk(teamResp);
    teamPks.push((await teamResp.json()).pk);
  }

  const saveResp = await postWithCsrf(
    context,
    `${API_URL}/bracket/tournaments/${tournamentPk}/save/`,
    {
      matches: [
        {
          id: 'w-1-0',
          round: 1,
          position: 0,
          bracketType: 'winners',
          eliminationType: 'single',
          radiantTeam: { pk: teamPks[0] },
          direTeam: { pk: teamPks[1] },
          status: 'pending',
        },
      ],
    },
  );
  await expectOk(saveResp);
  gamePk = (await saveResp.json()).matches[0].pk;
}

async function openViewer(browser: Browser, path: string): Promise<Viewer> {
  const context = await browser.newContext({
    baseURL: BASE_URL,
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();
  const frames: string[] = [];
  const gets: string[] = [];
  page.on('request', (req) => {
    if (req.method() === 'GET') gets.push(new URL(req.url()).pathname);
  });
  page.on('websocket', (ws) => {
    if (!ws.url().includes(`/api/tournament/${tournamentPk}/`)) return;
    ws.on('framereceived', (frame) => frames.push(String(frame.payload)));
  });
  // Before any page script, so the app's poll timers use the fake clock.
  await page.clock.install();
  await page.goto(path, { waitUntil: 'commit' });
  await expect
    .poll(() => frames.some((f) => f.includes('initial_events')), {
      timeout: 90_000,
    })
    .toBe(true);
  return { context, page, frames, gets, since: { frames: 0, gets: 0 } };
}

/** Let the clock run until the viewer's next poll of `apiPath`, then pause it. */
async function pauseAfterPoll(viewer: Viewer, apiPath: string): Promise<void> {
  const { page } = viewer;
  await page.clock.resume();
  await page.waitForResponse(
    (r) =>
      r.request().method() === 'GET' && new URL(r.url()).pathname === apiPath,
    { timeout: 15_000 },
  );
  // pauseAt only moves forward; leave room for the round trip.
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 1_000);
  viewer.since = { frames: viewer.frames.length, gets: viewer.gets.length };
}

/** Wait for the pushed event, then run at most PUSH_BUDGET_MS of fake time. */
async function expectPushed(
  viewer: Viewer,
  eventType: string,
  check: () => Promise<boolean>,
): Promise<void> {
  await expect
    .poll(
      () =>
        viewer.frames
          .slice(viewer.since.frames)
          .some((f) => f.includes(`"type": "${eventType}"`)),
      { timeout: 10_000 },
    )
    .toBe(true);
  let elapsed = 0;
  await expect
    .poll(
      async () => {
        if (elapsed < PUSH_BUDGET_MS) {
          await viewer.page.clock.runFor(100);
          elapsed += 100;
        }
        return check();
      },
      { timeout: 15_000 },
    )
    .toBe(true);
}

test.describe('Tournament live push (@cicd)', () => {
  test.setTimeout(240_000);

  test.beforeEach(async ({ context }) => {
    await loginAdmin(context);
    await createTournament(context);
  });

  test.afterEach(async ({ context }) => {
    if (!tournamentPk) return;
    await context.request.delete(`${API_URL}/tournaments/${tournamentPk}/`, {
      headers: { 'X-CSRFToken': await getCsrfToken(context) },
    });
  });

  test('a winner and a team rename reach open viewers without polling', async ({
    browser,
    context,
  }) => {
    const bracketApi = `/api/bracket/tournaments/${tournamentPk}/`;
    const tournamentApi = `/api/tournaments/${tournamentPk}/`;
    const [bracketViewer, teamsViewer] = await Promise.all([
      openViewer(browser, `/tournament/${tournamentPk}/bracket`),
      openViewer(browser, `/tournament/${tournamentPk}/teams`),
    ]);

    try {
      const radiantSlot = bracketViewer.page
        .locator('[data-testid="bracket-match-node"]')
        .locator('[data-testid="bracket-team-slot-radiant"]');
      await expect(radiantSlot).toHaveAttribute('data-team-status', 'pending', {
        timeout: 15_000,
      });
      await expect(
        teamsViewer.page.locator('[data-testid="team-card-name"]'),
      ).toHaveCount(2, { timeout: 15_000 });

      await pauseAfterPoll(bracketViewer, bracketApi);
      await expectOk(
        await postWithCsrf(
          context,
          `${API_URL}/bracket/games/${gamePk}/advance-winner/`,
          { winner: 'radiant' },
        ),
      );
      await expectPushed(
        bracketViewer,
        'bracket_update',
        async () =>
          (await radiantSlot.getAttribute('data-team-status')) === 'winner',
      );

      const newName = `Pushed ${tournamentPk}`;
      await Promise.all([
        pauseAfterPoll(bracketViewer, bracketApi),
        pauseAfterPoll(teamsViewer, tournamentApi),
      ]);
      await expectOk(
        await postWithCsrf(context, `${API_URL}/teams/${teamPks[0]}/rename/`, {
          name: newName,
          reason: 'live push e2e',
        }),
      );
      await Promise.all([
        expectPushed(
          teamsViewer,
          'tournament_update',
          async () =>
            (await teamsViewer.page
              .locator('[data-testid="team-card-name"]', { hasText: newName })
              .count()) === 1,
        ),
        expectPushed(bracketViewer, 'tournament_update', async () =>
          bracketViewer.gets
            .slice(bracketViewer.since.gets)
            .includes(bracketApi),
        ),
      ]);
    } finally {
      await bracketViewer.context.close();
      await teamsViewer.context.close();
    }
  });
});
