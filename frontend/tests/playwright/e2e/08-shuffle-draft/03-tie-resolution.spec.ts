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
import {
  test,
  expect,
  loginAdmin,
  resetTournamentByKey,
  type TournamentData,
} from '../../fixtures';

const KEY = 'shuffle_tie_resolution';

async function openDraft(page: Page, tournamentPk: number): Promise<void> {
  await page.goto(`/tournament/${tournamentPk}`);
  await page.getByTestId('tournamentDetailPage').waitFor({ state: 'visible', timeout: 15_000 });
  await page.getByTestId('teamsTab').click();
  await page.getByTestId('teamsTabContent').waitFor({ state: 'visible' });
  await page
    .locator(
      '[data-testid="liveTeamDraftButton"], [data-testid="startTeamDraftButton"], [data-testid="viewTeamDraftButton"]'
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

test.describe.serial('Shuffle draft - tie roll popup', () => {
  let t: TournamentData;

  test.beforeEach(async ({ browser, context, loginAdmin: login }) => {
    const admin = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      await loginAdmin(admin);
      const reset = await resetTournamentByKey(admin, KEY);
      if (!reset) throw new Error(`Could not reset ${KEY}. Run: just db::populate::fresh`);
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

      await pickFirstPlayer(page);

      for (const viewer of [page, spectator]) {
        const popup = viewer.getByTestId('tie-roll-popup');
        await expect(popup).toBeVisible({ timeout: 15_000 });
        await expect(popup).toHaveCount(1);
        await expect(popup).toHaveAttribute('data-pick-number', '2');
        await expect(popup).toContainText('Tie for pick #2');
        await expect(popup.locator('[data-testid^="tie-roll-row-"]')).toHaveCount(3);
        await expect(popup.getByRole('button', { name: /continue/i })).toHaveCount(0);
      }

      const winnerId = await page.getByTestId('tie-roll-popup').getAttribute('data-winner-id');
      await expect(spectator.getByTestId('tie-roll-popup')).toHaveAttribute('data-winner-id', winnerId!);
      for (const viewer of [page, spectator]) {
        await expect(viewer.getByTestId('tie-roll-result')).toContainText('picks next', { timeout: 6_000 });
        await expect(viewer.getByTestId(`tie-roll-row-${winnerId}`)).toHaveAttribute('data-winner', 'true');
      }

      for (const viewer of [page, spectator]) {
        await expect(viewer.getByTestId('tie-roll-popup')).toHaveCount(0, { timeout: 8_000 });
      }
      await expect(page.getByRole('dialog').first()).toBeVisible();
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
