/**
 * Shuffle draft tie roll popup
 *
 * Uses the shuffle_tie_resolution tournament (controlled MMR):
 * - Captain 1 (2000 MMR) picks first (no tie)
 * - Captains 2, 3, 4 (3000 MMR each); every available player is 2000 MMR
 *
 * After Captain 1 picks: Team 1 = 4000, Teams 2/3/4 = 3000 -> 3-way tie for pick #2.
 * Each test resets the tournament, so every test starts at pick #1.
 */

import type { Page } from '@playwright/test';
import type { TieResolution } from '~/components/teamdraft/types';
import {
  expect,
  loginAdmin,
  resetTournamentByKey,
  test,
  type TournamentData,
} from '../../fixtures';
import { captureTieRoll, type TieRollSnapshot } from '../../helpers/tie-roll';

const KEY = 'shuffle_tie_resolution';

async function openDraft(page: Page, tournamentPk: number): Promise<void> {
  await page.goto(`/tournament/${tournamentPk}`);
  await page
    .getByTestId('tournamentDetailPage')
    .waitFor({ state: 'visible', timeout: 15_000 });
  await page.getByTestId('teamsTab').click();
  await page.getByTestId('teamsTabContent').waitFor({ state: 'visible' });
  await page
    .locator(
      '[data-testid="liveTeamDraftButton"], [data-testid="startTeamDraftButton"], [data-testid="viewTeamDraftButton"]',
    )
    .first()
    .click();
  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 10_000 });
}

async function pickFirstPlayer(page: Page): Promise<void> {
  const pick = page.getByRole('dialog').getByTestId('pickPlayerButton').first();
  await pick.waitFor({ state: 'visible', timeout: 10_000 });
  await pick.click();
  const confirm = page.getByRole('alertdialog');
  if (await confirm.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await confirm.getByTestId('confirmPickButton').click();
  }
}

function expectTieRoll(
  snapshot: TieRollSnapshot | null,
  tie: TieResolution,
): void {
  expect(snapshot, 'viewer captured a completed tie roll').not.toBeNull();
  const observed = snapshot!;
  expect(observed.count).toBe(1);
  expect(observed.visible).toBe(true);
  expect(observed.pickNumber).toBe('2');
  expect(observed.heading).toContain('Tie for pick #2');
  expect(observed.continueCount).toBe(0);
  expect(observed.winnerId).toBe(String(tie.winner_id));
  expect(observed.result).toContain('picks next');
  expect(observed.rows.map((row) => row.teamId)).toEqual(
    tie.tied_teams.map((team) => String(team.id)),
  );
  const finalRound = tie.roll_rounds.at(-1)!;
  for (const row of observed.rows) {
    expect(row.winner).toBe(String(row.teamId === observed.winnerId));
    const roll = finalRound.find(
      (entry) => String(entry.team_id) === row.teamId,
    );
    expect(row.face).toBe(roll ? String(roll.roll) : null);
    if (!roll) expect(row.text).toContain('out');
  }
}

test.describe.serial('Shuffle draft - tie roll popup', () => {
  // Two logged-in browsers plus the 5 s dice hold do not fit the default 30 s on a CI runner.
  test.describe.configure({ timeout: 60_000 });
  let t: TournamentData;

  test.beforeEach(async ({ browser, context, loginAdmin: login }) => {
    const admin = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await loginAdmin(admin);
      const reset = await resetTournamentByKey(admin, KEY);
      if (!reset)
        throw new Error(
          `Could not reset ${KEY}. Run: just db::populate::fresh`,
        );
      t = reset;
    } finally {
      await admin.close();
    }
    await context.clearCookies();
    await login();
  });

  test('@cicd every viewer sees the dice roll, with no Continue, and it closes itself', async ({
    page,
    browser,
  }) => {
    const spectatorCtx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await loginAdmin(spectatorCtx);
      const spectator = await spectatorCtx.newPage();
      await openDraft(spectator, t.pk);
      await openDraft(page, t.pk);

      const viewers = [page, spectator];
      const captures = await Promise.all(
        viewers.map((viewer) => viewer.evaluateHandle(captureTieRoll)),
      );
      try {
        const picked = page.waitForResponse(
          (response) =>
            response.request().method() === 'POST' &&
            new URL(response.url()).pathname === '/api/tournaments/pick_player',
        );
        await pickFirstPlayer(page);
        const response = await picked;
        expect(response.status()).toBe(201);
        const { tie_resolution: tie } = (await response.json()) as {
          tie_resolution: TieResolution;
        };
        expect(tie).toBeDefined();
        expect(tie.pick_number).toBe(2);
        expect(tie.tied_teams).toHaveLength(3);

        await Promise.all(
          captures.map((capture) =>
            capture.evaluate(async (observation) => {
              await observation.result;
            }),
          ),
        );
        await Promise.all(
          viewers.map((viewer) =>
            expect(viewer.getByTestId('tie-roll-popup')).toHaveCount(0, {
              timeout: 8_000,
            }),
          ),
        );
        // Read the retained frame after dismissal to exercise delayed assertions.
        const snapshots = await Promise.all(
          captures.map((capture) =>
            capture.evaluate((observation) => observation.result),
          ),
        );
        for (const snapshot of snapshots) expectTieRoll(snapshot, tie);
        await expect(page.getByRole('dialog').first()).toBeVisible();
      } finally {
        await Promise.all(
          captures.map(async (capture) => {
            await capture.evaluate((observation) => observation.cancel());
            await capture.dispose();
          }),
        );
      }
    } finally {
      await spectatorCtx.close();
    }
  });

  test('@cicd closing the popup early keeps it closed (HTTP and WS copies are one roll)', async ({
    page,
  }) => {
    await openDraft(page, t.pk);
    await pickFirstPlayer(page);

    const popup = page.getByTestId('tie-roll-popup');
    await expect(popup).toBeVisible({ timeout: 15_000 });
    await page.getByTestId('tie-roll-close').click();
    await expect(popup).toHaveCount(0);
    // The picker receives the roll twice (pick response + tie_roll event); the second must not reopen it.
    await page.waitForTimeout(2_000);
    await expect(popup).toHaveCount(0);
  });
});
