/**
 * WebSocket Toast Notification Tests (Category 3)
 *
 * Tests that draft events trigger appropriate toast notifications:
 * - No toasts from initial_events on first connect
 * - player_picked toast shows "picked" with player name
 *
 * Tournament: 'draft_captain_turn' (snake draft, captain is admin, 0 picks)
 */

import {
  test,
  expect,
  getTournamentByKey,
  resetTournamentByKey,
  TournamentPage,
  DraftWebSocketHelper,
} from '../../fixtures';

interface TournamentWithDraft {
  pk: number;
  draft?: { pk: number };
}

test.describe('WebSocket Toast Notifications', () => {
  let tournamentPk: number;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const result = await getTournamentByKey(context, 'draft_captain_turn');
    if (!result) throw new Error('Could not find draft_captain_turn tournament');
    const tournament = result as unknown as TournamentWithDraft;
    tournamentPk = tournament.pk;
    await context.close();
  });

  test('no toasts from initial_events on first connect', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    const tournamentPage = new TournamentPage(page);

    await tournamentPage.goto(tournamentPk);
    await tournamentPage.clickTeamsTab();
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();
    await wsHelper.waitForConnection();
    await wsHelper.waitForMessage('initial_events');

    // No toasts should appear from initial_events replay
    await wsHelper.assertNoToast(2000);
  });

  test('player_picked event shows toast with pick info', async ({
    page,
    context,
    loginAdmin,
  }) => {
    await loginAdmin();

    // Reset tournament BEFORE navigating (admin is captain with first pick)
    const resetData = await resetTournamentByKey(context, 'draft_captain_turn');
    if (resetData) tournamentPk = resetData.pk;

    const wsHelper = new DraftWebSocketHelper(page);
    const tournamentPage = new TournamentPage(page);

    // Navigate AFTER reset so we get fresh state
    await tournamentPage.goto(tournamentPk);
    await tournamentPage.clickTeamsTab();
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();
    await wsHelper.waitForConnection();
    await wsHelper.waitForMessage('initial_events');

    // Captain picks the first available player
    const dialog = page.locator('[role="dialog"]');
    const pickButton = dialog.locator('[data-testid="pickPlayerButton"]').first();
    await expect(pickButton).toBeVisible({ timeout: 5000 });
    await pickButton.click();

    // Confirm the pick in the confirmation dialog
    const confirmButton = page.getByRole('button', { name: 'Confirm Pick' });
    await expect(confirmButton).toBeVisible({ timeout: 3000 });

    await confirmButton.click();

    // Toast should appear with "picked" text after the pick action
    const toast = await wsHelper.waitForToast(/picked/i, 5000);
    await expect(toast).toBeVisible();
  });
});
