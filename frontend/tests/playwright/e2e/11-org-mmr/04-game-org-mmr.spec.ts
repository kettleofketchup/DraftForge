/**
 * Per-game org MMR: edit both games on the org Users tab, then see each
 * tournament show only its own game's value.
 *
 * Uses the isolated "Game MMR Org" data (backend tests.data.game_org_mmr).
 * (a) owns gom_edit (8006), reset to Dota 3000 / Deadlock 1500 per test;
 * (b) owns gom_display (8005) and sets its values itself.
 */

import type { Page } from '@playwright/test';
import {
  expect,
  fillEditField,
  openEditModal,
  readEditField,
  saveEditModal,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { setApprovedMmr } from '../../fixtures/events';
import {
  GAME_TYPE_DEADLOCK,
  GAME_TYPE_DOTA2,
  getGameOrgMmrData,
  type GameOrgMmrData,
} from '../../fixtures/game-org-mmr';

let data: GameOrgMmrData;

async function openTournamentCard(
  page: Page,
  tournamentPk: number,
  username: string,
) {
  await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);
  await expect(page.getByTestId('tournamentDetailPage')).toBeVisible({
    timeout: 15000,
  });
  const playersTab = page.getByTestId('playersTab');
  if (await playersTab.isVisible()) await playersTab.click();
  const search = page.getByTestId('userSearchInput');
  await expect(search).toBeVisible({ timeout: 10000 });
  await search.fill(username);
  await page.waitForTimeout(800);
  await page.keyboard.press('Escape');
  const card = page.getByTestId(`usercard-${username}`);
  await expect(card).toBeVisible({ timeout: 10000 });
  return card;
}

test.describe('Per-game org MMR (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    data = await getGameOrgMmrData(context);
    await context.close();
  });

  test.describe('edit', () => {
    test.beforeEach(async ({ context, loginAdmin }) => {
      const edit = data.users.edit.pk;
      await setApprovedMmr(context, data.org.pk, edit, 3000, GAME_TYPE_DOTA2);
      await setApprovedMmr(
        context,
        data.org.pk,
        edit,
        1500,
        GAME_TYPE_DEADLOCK,
      );
      await loginAdmin();
    });

    test('edits both games on the org Users tab and shows Deadlock in a Deadlock tournament', async ({
      page,
    }) => {
      const username = data.users.edit.username;
      await visitAndWaitForHydration(page, `/organizations/${data.org.pk}`);
      await page.getByTestId('org-tab-users').click();

      const card = page.getByTestId(`usercard-${username}`);
      await expect(card).toBeVisible({ timeout: 10000 });
      await expect(card.getByTestId('usercard-org-mmr-dota2')).toContainText(
        '3000',
      );
      await expect(card.getByTestId('usercard-org-mmr-deadlock')).toContainText(
        '1500',
      );

      await openEditModal(page, card);
      expect(await readEditField(page, 'mmr')).toBe('3000');
      expect(await readEditField(page, 'mmr-deadlock')).toBe('1500');
      await fillEditField(page, 'mmr', '4321');
      await fillEditField(page, 'mmr-deadlock', '2345');
      await saveEditModal(page);

      await expect(card.getByTestId('usercard-org-mmr-dota2')).toContainText(
        '4321',
        {
          timeout: 10000,
        },
      );
      await expect(card.getByTestId('usercard-org-mmr-deadlock')).toContainText(
        '2345',
      );

      await page.reload();
      await page.getByTestId('org-tab-users').click();
      const reloaded = page.getByTestId(`usercard-${username}`);
      await expect(
        reloaded.getByTestId('usercard-org-mmr-dota2'),
      ).toContainText('4321', {
        timeout: 10000,
      });
      await expect(
        reloaded.getByTestId('usercard-org-mmr-deadlock'),
      ).toContainText('2345');
      await openEditModal(page, reloaded);
      expect(await readEditField(page, 'mmr')).toBe('4321');
      expect(await readEditField(page, 'mmr-deadlock')).toBe('2345');
      await page.keyboard.press('Escape');

      const tCard = await openTournamentCard(
        page,
        data.tournaments.deadlock.pk,
        username,
      );
      const tile = tCard.getByTestId('usercard-org-mmr-deadlock');
      await expect(tile).toContainText('Deadlock');
      await expect(tile).toContainText('2345');
      await expect(tCard.getByTestId('usercard-org-mmr-dota2')).toHaveCount(0);
    });
  });

  test.describe('display', () => {
    test.beforeEach(async ({ context, loginAdmin }) => {
      const display = data.users.display.pk;
      await setApprovedMmr(
        context,
        data.org.pk,
        display,
        3777,
        GAME_TYPE_DOTA2,
      );
      await setApprovedMmr(
        context,
        data.org.pk,
        display,
        2888,
        GAME_TYPE_DEADLOCK,
      );
      await loginAdmin();
    });

    test('each tournament shows its own game', async ({ page }) => {
      const username = data.users.display.username;

      const deadlockCard = await openTournamentCard(
        page,
        data.tournaments.deadlock.pk,
        username,
      );
      const deadlockTile = deadlockCard.getByTestId(
        'usercard-org-mmr-deadlock',
      );
      await expect(deadlockTile).toContainText('Deadlock');
      await expect(deadlockTile).toContainText('2888');
      await expect(
        deadlockCard.getByTestId('usercard-org-mmr-dota2'),
      ).toHaveCount(0);

      const dotaCard = await openTournamentCard(
        page,
        data.tournaments.dota.pk,
        username,
      );
      const dotaTile = dotaCard.getByTestId('usercard-org-mmr-dota2');
      await expect(dotaTile).toContainText('Dota 2');
      await expect(dotaTile).toContainText('3777');
      await expect(
        dotaCard.getByTestId('usercard-org-mmr-deadlock'),
      ).toHaveCount(0);
    });
  });
});
