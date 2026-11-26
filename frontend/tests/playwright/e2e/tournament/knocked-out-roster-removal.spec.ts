/**
 * Removing a tournament player keeps knocked-out rosters intact (#842).
 *
 * Uses the dedicated `knocked_out_roster` tournament:
 * - KO Out: knocked out (placement 3), members ko_roster_out_1..5
 * - KO Live: still playing, members ko_roster_live_1..5
 */

import type { Locator, Page } from '@playwright/test';
import {
  expect,
  resetTournamentByKey,
  test,
  type TournamentData,
} from '../../fixtures';

const KEY = 'knocked_out_roster';
const OUT_PLAYER = 'ko_roster_out_3';
const LIVE_PLAYER = 'ko_roster_live_3';

let tournament: TournamentData;

function teamCard(page: Page, name: string): Locator {
  const team = tournament.teams.find((t) => t.name === name);
  if (!team) throw new Error(`Team ${name} missing from the ${KEY} reset`);
  return page.getByTestId(`completed-team-card-${team.pk}`);
}

/** A card member row, matched on its avatar's alt text (names can truncate). */
function memberRow(card: Locator, username: string): Locator {
  return card.locator('[data-testid^="team-card-member-"]').filter({
    has: card.page().locator(`img[alt="${username}"]`),
  });
}

async function openTournament(page: Page): Promise<void> {
  await page.goto(`/tournament/${tournament.pk}`);
  await page
    .getByTestId('tournamentDetailPage')
    .waitFor({ state: 'visible', timeout: 15_000 });
}

async function removePlayer(page: Page, username: string): Promise<void> {
  await openTournament(page);
  await page.getByTestId('playersTab').click();
  const button = page.getByTestId(`removePlayerBtn-${username}`);
  await button.scrollIntoViewIfNeeded();
  const patched = page.waitForResponse(
    (r) =>
      r.request().method() === 'PATCH' &&
      new URL(r.url()).pathname === `/api/tournaments/${tournament.pk}/`,
  );
  await button.click();
  expect((await patched).status()).toBe(200);
}

async function openTeamsTab(page: Page): Promise<void> {
  await openTournament(page);
  await page.getByTestId('teamsTab').click();
  await page.getByTestId('teamsTabContent').waitFor({ state: 'visible' });
}

test.describe('Knocked-out roster on player removal (#842)', () => {
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

  test('@cicd removing a player leaves the knocked-out team roster intact', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();

    await openTeamsTab(page);
    await expect(memberRow(teamCard(page, 'KO Out'), OUT_PLAYER)).toBeVisible();
    await expect(
      memberRow(teamCard(page, 'KO Live'), LIVE_PLAYER),
    ).toBeVisible();

    await removePlayer(page, OUT_PLAYER);
    await removePlayer(page, LIVE_PLAYER);

    await openTournament(page);
    await page.getByTestId('playersTab').click();
    await expect(page.getByTestId('playersTabContent')).toBeVisible();
    await expect(page.getByTestId(`removePlayerBtn-${OUT_PLAYER}`)).toHaveCount(
      0,
    );
    await expect(
      page.getByTestId(`removePlayerBtn-${LIVE_PLAYER}`),
    ).toHaveCount(0);

    await page.getByTestId('teamsTab').click();
    await page.getByTestId('teamsTabContent').waitFor({ state: 'visible' });
    const outCard = teamCard(page, 'KO Out');
    await expect(memberRow(outCard, OUT_PLAYER)).toBeVisible();
    await expect(
      outCard.locator('[data-testid^="team-card-member-"]'),
    ).toHaveCount(5);
    const liveCard = teamCard(page, 'KO Live');
    await expect(memberRow(liveCard, 'ko_roster_live_1')).toBeVisible();
    await expect(memberRow(liveCard, LIVE_PLAYER)).toHaveCount(0);
  });
});
