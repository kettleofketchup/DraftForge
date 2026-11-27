/**
 * Removing a team captain from the tournament's players (#841).
 *
 * Uses the dedicated `captain_removal` tournament (reset in beforeAll):
 * - CR Knocked Out: placement 3, lost a bracket game; captain ko_1, deputy ko_2
 * - CR Fresh: captain-only pre-draft team
 */

import type { Page } from '@playwright/test';
import {
  expect,
  resetTournamentByKey,
  test,
  type TournamentData,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

const KEY = 'captain_removal';
const PREFIX = 'cr_fixture_';
const PLAYED = 'CR Knocked Out';
const FRESH = 'CR Fresh';

let tournament: TournamentData;

function teamPk(name: string): number {
  const team = tournament.teams.find((t) => t.name === name);
  if (!team) throw new Error(`Team ${name} missing from the ${KEY} reset`);
  return team.pk;
}

async function openTab(page: Page, tab: 'players' | 'teams'): Promise<void> {
  await page.goto(`/tournament/${tournament.pk}`);
  await page
    .getByTestId('tournamentDetailPage')
    .waitFor({ state: 'visible', timeout: 15_000 });
  await page.getByTestId(`${tab}Tab`).click();
  await page.getByTestId(`${tab}TabContent`).waitFor({ state: 'visible' });
}

async function removePlayer(page: Page, username: string): Promise<void> {
  const button = page.getByTestId(`removePlayerBtn-${username}`);
  await button.scrollIntoViewIfNeeded();
  const patch = page.waitForResponse(
    (r) =>
      r.request().method() === 'DELETE' &&
      new URL(r.url()).pathname.startsWith(
        `/api/tournaments/${tournament.pk}/members/`,
      ),
  );
  await button.click();
  expect((await patch).status()).toBe(200);
  await expect(page.getByTestId(`usercard-${username}`)).toHaveCount(0);
}

test.describe('Removing a captain from the players list', () => {
  test.describe.configure({ mode: 'serial', timeout: 60_000 });

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      const reset = await resetTournamentByKey(ctx, KEY);
      if (!reset) throw new Error(`Could not reset ${KEY}`);
      tournament = reset;
    } finally {
      await ctx.close();
    }
  });

  test('@cicd keeps a knocked-out team and its historical captain', async ({
    page,
    context,
    loginAdmin,
  }) => {
    await loginAdmin();
    await openTab(page, 'players');
    await removePlayer(page, `${PREFIX}ko_1`);
    await removePlayer(page, `${PREFIX}fresh`);

    await openTab(page, 'teams');
    const played = page.getByTestId(`completed-team-card-${teamPk(PLAYED)}`);
    await expect(played).toBeVisible();
    await expect(
      page.getByTestId(`completed-team-card-${teamPk(FRESH)}`),
    ).toHaveCount(0);

    await played.getByTestId('team-card-name').click();
    const modal = page.getByTestId('team-modal');
    await expect(modal.getByTestId('team-modal-captain')).toContainText(
      `${PREFIX}ko_1`,
    );

    const team = await context.request.get(
      `${API_URL}/teams/${teamPk(PLAYED)}/`,
    );
    expect(team.status()).toBe(200);
    const body = await team.json();
    expect(body.placement).toBe(3);
    expect(body.captain?.username).toBe(`${PREFIX}ko_1`);

    const tournamentResp = await context.request.get(
      `${API_URL}/tournaments/${tournament.pk}/`,
    );
    const detail = await tournamentResp.json();
    expect(
      detail.games.some(
        (g: { radiant_team: unknown }) =>
          (typeof g.radiant_team === 'object'
            ? (g.radiant_team as { pk?: number } | null)?.pk
            : g.radiant_team) === teamPk(PLAYED),
      ),
    ).toBe(true);
  });
});
