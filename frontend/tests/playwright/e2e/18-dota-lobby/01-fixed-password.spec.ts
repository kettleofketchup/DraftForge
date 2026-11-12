/**
 * A fixed series password reaches the event, its tournament and the lobby.
 *
 * The Lobby Test Series is in fixed mode. Saving a new fixed password on the
 * series cascades to its upcoming, on-schedule event and that event's
 * tournament; the lobby staff then create for the first game is created in
 * the simulated dota_lobby with exactly that password. After the reset
 * between tests, the seeded password is back on the event and in the next
 * lobby.
 */

import {
  expect,
  expectLobbyState,
  getLobbyRow,
  getSimLobby,
  loginDotaLobby,
  openBracket,
  openMatchModal,
  patchWithCsrf,
  requestLobby,
  resetDotaLobbyData,
  hasSimulator,
  SIMULATOR_SKIP_REASON,
  test,
  waitForLobbyRow,
  type DotaLobbyTestData,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

test.describe('Dota lobby: fixed series password (e2e)', () => {
  test.describe.configure({ mode: 'serial' });

  let data: DotaLobbyTestData;

  test.beforeEach(async ({ context }) => {
    test.skip(!(await hasSimulator(context)), SIMULATOR_SKIP_REASON);
    data = await resetDotaLobbyData(context);
  });

  test('@cicd the series password cascades and the lobby is created with it', async ({
    context,
    page,
  }) => {
    test.setTimeout(90_000);
    await loginDotaLobby(context, 'staff');

    // A new fixed password, so the assertions cannot pass on the seeded one.
    const password = `Fixed-${Date.now().toString(36)}`;
    const patch = await patchWithCsrf(
      context,
      `${API_URL}/events/repeaters/${data.series.pk}/`,
      { dota_lobby_password_mode: 'fixed', dota_lobby_password: password },
    );
    expect(patch.status(), await patch.text()).toBe(200);

    // The event follows its series.
    const eventPassword = await context.request.get(
      `${API_URL}/events/${data.series_event.pk}/lobby-password/`,
    );
    expect(eventPassword.status()).toBe(200);
    expect(await eventPassword.json()).toMatchObject({
      mode: 'fixed',
      password,
      source: 'series',
    });

    // Staff create the lobby from the match dialog.
    const tournament = data.series_event.tournament;
    const game = tournament.games[0];
    await openBracket(page, tournament.pk);
    const dialog = await openMatchModal(page, game.pk);
    await expect(dialog.locator('[data-testid="lobby-panel"]')).toBeVisible();
    await dialog.locator('[data-testid="lobby-create-btn"]').click();

    const row = await waitForLobbyRow(context, game.pk);
    expect(row.password).toBe(password);

    // The simulated game coordinator lobby got exactly that password.
    const simLobby = await getSimLobby(context, row.lobby_id!);
    expect(simLobby.password).toBe(password);
    expect(simLobby.league_id).toBe(data.league.steam_league_id);

    // And the dialog shows it to staff.
    await expectLobbyState(dialog, ['waiting', 'ready']);
    await expect(dialog.locator('[data-testid="lobby-password"]')).toHaveText(password);
  });

  test('the seeded series password is what a lobby gets after a reset', async ({
    context,
  }) => {
    test.setTimeout(60_000);
    await loginDotaLobby(context, 'staff');
    const resp = await context.request.get(
      `${API_URL}/events/repeaters/${data.series.pk}/lobby-password/`,
    );
    expect(resp.status()).toBe(200);
    expect(await resp.json()).toMatchObject({ mode: 'fixed', password: data.fixed_password });

    // The reset cascades it to the event again, not only to the series row:
    // the first test moved the series and its event to a `Fixed-...` one.
    const eventPassword = await context.request.get(
      `${API_URL}/events/${data.series_event.pk}/lobby-password/`,
    );
    expect(eventPassword.status()).toBe(200);
    expect(await eventPassword.json()).toMatchObject({
      mode: 'fixed',
      password: data.fixed_password,
      source: 'series',
    });

    // And a lobby created now gets it.
    const game = data.series_event.tournament.games[0];
    const before = await getLobbyRow(context, game.pk);
    await requestLobby(context, game.pk);
    const row = await waitForLobbyRow(context, game.pk, undefined, { previousId: before?.id });
    expect(row.password).toBe(data.fixed_password);
    expect((await getSimLobby(context, row.lobby_id!)).password).toBe(data.fixed_password);
  });
});
