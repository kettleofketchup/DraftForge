/**
 * A lobby from request to result, against the simulated dota_lobby.
 *
 * Lobby Lifecycle Tournament, one game. Staff create the lobby; the
 * simulator's auto mode has the invited players join and sit on their
 * rostered sides, so the lobby becomes ready. A player's chat line reaches
 * the bot, staff launch, and the simulator starts the match: the game goes
 * live and its bracket node shows the in-game dot. When the simulated match
 * ends, the lobby's result is offered (never submitted) on the winner
 * buttons, and a new lobby is no longer offered: staff confirm the winner,
 * or, after resetting the game, replay the match on purpose.
 */

import {
  bracketNode,
  closeMatchModal,
  expect,
  expectLobbyState,
  getSimLobby,
  loginDotaLobby,
  openBracket,
  openMatchModal,
  resetDotaLobbyData,
  sim,
  hasSimulator,
  SIMULATOR_SKIP_REASON,
  test,
  waitForLobbyRow,
  type DotaLobbyTestData,
} from '../../fixtures';
import type { Locator, Page } from '@playwright/test';

test.describe('Dota lobby: lifecycle with the simulator (e2e)', () => {
  test.describe.configure({ mode: 'serial' });

  let data: DotaLobbyTestData;

  test.beforeEach(async ({ context }) => {
    test.skip(!(await hasSimulator(context)), SIMULATOR_SKIP_REASON);
    data = await resetDotaLobbyData(context);
  });

  async function saveBracket(page: Page): Promise<void> {
    const unsaved = page.locator('[data-testid="bracket-unsaved-changes"]');
    await expect(unsaved).toBeVisible();
    await page.locator('[data-testid="saveBracketButton"]').click();
    await expect(unsaved).toBeHidden({ timeout: 15_000 });
  }

  async function reopen(page: Page, gamePk: number): Promise<Locator> {
    await page.reload();
    await expect(page.locator('[data-testid="bracketContainer"]')).toBeVisible({
      timeout: 20_000,
    });
    return openMatchModal(page, gamePk);
  }

  test('@cicd join, launch, match start and end, provisional winner, replay', async ({
    context,
    page,
  }) => {
    test.setTimeout(180_000);
    await loginDotaLobby(context, 'staff');
    const tournament = data.lifecycle_tournament;
    const game = tournament.games[0];
    const [radiantTeam, direTeam] = Object.values(tournament.teams);

    await openBracket(page, tournament.pk);
    let dialog = await openMatchModal(page, game.pk);
    await dialog.locator('[data-testid="lobby-create-btn"]').click();

    // Auto join: every rostered player joins and sits on their side.
    const row = await waitForLobbyRow(context, game.pk);
    await expectLobbyState(dialog, 'ready', 45_000);
    const seated = await getSimLobby(context, row.lobby_id!);
    const seatOf = (accountId: number) =>
      seated.members.find((m) => m.account_id === accountId)?.team;
    for (const player of radiantTeam) expect(seatOf(player.account_id)).toBe('radiant');
    for (const player of direTeam) expect(seatOf(player.account_id)).toBe('dire');
    const captain = radiantTeam[0];
    await expect(
      dialog.locator(`[data-testid="lobby-player-status-${captain.pk}"]`),
    ).not.toHaveText('', { timeout: 15_000 });

    // A player's chat command reaches the bot through the simulated chat.
    const chat = await sim.post(context, `lobbies/${row.lobby_id}/chat`, {
      account_id: captain.account_id,
      text: '!help',
    });
    expect(chat.status(), await chat.text()).toBe(200);
    expect((await chat.json()).delivered).toBe(true);

    // Staff launch the ready lobby; the simulator starts the match.
    await dialog.locator('[data-testid="lobby-launch-btn"]').click();
    await expectLobbyState(dialog, 'in_game', 45_000);
    await expect(dialog.locator('[data-testid="match-status-live"]')).toBeVisible({
      timeout: 30_000,
    });
    await expect(dialog.locator('[data-testid="lobby-match-id"]')).toBeVisible();
    await closeMatchModal(page);
    await expect(bracketNode(page, game.pk).locator('[data-testid="match-lobby-dot"]')).toHaveAttribute(
      'data-lobby-state',
      'in_game',
      { timeout: 30_000 },
    );

    // The simulated match ends with a Radiant win.
    const end = await sim.post(context, `lobbies/${row.lobby_id}/end`, { result: 'radiant' });
    expect(end.status(), await end.text()).toBe(200);
    await waitForLobbyRow(context, game.pk, (r) => r.provisional_winner_side === 'radiant');

    // The lobby's result is a suggestion on the winner buttons, not a result.
    dialog = await openMatchModal(page, game.pk);
    await expect(dialog.locator('[data-testid="lobby-provisional-result"]')).toBeVisible({
      timeout: 30_000,
    });
    await expect(dialog.locator('[data-testid="radiantWinsButton"]')).toHaveAttribute(
      'data-lobby-suggested',
      'true',
    );
    await expect(dialog.locator('[data-testid="direWinsButton"]')).not.toHaveAttribute(
      'data-lobby-suggested',
      /.*/,
    );
    await expect(dialog.locator('[data-testid="match-status-final"]')).toHaveCount(0);

    // Once the lobby has finished, no new lobby is offered for a played match.
    await expectLobbyState(dialog, 'finished', 45_000);
    await expect(dialog.locator('[data-testid="lobby-create-btn"]')).toHaveCount(0);
    await expect(dialog.locator('[data-testid="lobby-replay-btn"]')).toHaveCount(0);

    // Staff confirm the suggested winner.
    await dialog.locator('[data-testid="radiantWinsButton"]').click();
    await closeMatchModal(page);
    await saveBracket(page);
    dialog = await reopen(page, game.pk);
    await expect(dialog.locator('[data-testid="match-status-final"]')).toBeVisible();
    await expect(dialog.locator('[data-testid="lobby-create-btn"]')).toHaveCount(0);

    // A disputed result: staff reset the game. Retry stays hidden; replaying
    // the match is offered instead.
    await dialog.locator('[data-testid="unsetWinnerButton"]').click();
    await closeMatchModal(page);
    await saveBracket(page);
    dialog = await reopen(page, game.pk);
    await expect(dialog.locator('[data-testid="lobby-replay-btn"]')).toBeVisible({
      timeout: 30_000,
    });
    await expect(dialog.locator('[data-testid="lobby-create-btn"]')).toHaveCount(0);

    await dialog.locator('[data-testid="lobby-replay-btn"]').click();
    await page.locator('[data-testid="lobby-replay-confirm"]').click();
    const replay = await waitForLobbyRow(context, game.pk, undefined, { previousId: row.id });
    expect(replay.lobby_id).not.toBe(row.lobby_id);
    await expectLobbyState(dialog, ['waiting', 'ready'], 45_000);
  });
});
