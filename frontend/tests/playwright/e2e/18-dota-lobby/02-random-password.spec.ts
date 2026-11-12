/**
 * Random password mode: a regenerated password only reaches new lobbies.
 *
 * The Lobby Random Event generates its own password. A lobby created before
 * a regenerate keeps the old password, in DraftForge and in the simulated
 * game coordinator; the lobby staff recreate afterwards gets the new one.
 */

import {
  expect,
  expectLobbyState,
  getSimLobby,
  loginDotaLobby,
  openBracket,
  openMatchModal,
  postWithCsrf,
  requestLobby,
  resetDotaLobbyData,
  sim,
  hasSimulator,
  SIMULATOR_SKIP_REASON,
  test,
  waitForLobbyRow,
  type DotaLobbyTestData,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

test.describe('Dota lobby: random event password (e2e)', () => {
  test.describe.configure({ mode: 'serial' });

  let data: DotaLobbyTestData;

  test.beforeEach(async ({ context }) => {
    test.skip(!(await hasSimulator(context)), SIMULATOR_SKIP_REASON);
    data = await resetDotaLobbyData(context);
  });

  test('@cicd regenerating the password affects only lobbies created afterwards', async ({
    context,
    page,
  }) => {
    test.setTimeout(120_000);
    await loginDotaLobby(context, 'staff');
    const event = data.random_event;
    const game = event.tournament.games[0];

    const before = await context.request.get(`${API_URL}/events/${event.pk}/lobby-password/`);
    expect(before.status()).toBe(200);
    const { mode, password: oldPassword } = await before.json();
    expect(mode).toBe('random');
    expect(oldPassword).toMatch(/^[a-z2-9]{12}$/);

    // A lobby made with the current password.
    await requestLobby(context, game.pk);
    const first = await waitForLobbyRow(context, game.pk);
    expect(first.password).toBe(oldPassword);
    expect((await getSimLobby(context, first.lobby_id!)).password).toBe(oldPassword);

    // Staff regenerate it.
    const regen = await postWithCsrf(
      context,
      `${API_URL}/events/${event.pk}/lobby-password/regenerate/`,
    );
    expect(regen.status(), await regen.text()).toBe(200);
    const newPassword = (await regen.json()).password as string;
    expect(newPassword).not.toBe(oldPassword);

    // The existing lobby keeps the password it was created with.
    expect((await getSimLobby(context, first.lobby_id!)).password).toBe(oldPassword);
    await openBracket(page, event.tournament.pk);
    const dialog = await openMatchModal(page, game.pk);
    await expectLobbyState(dialog, ['waiting', 'ready']);
    await expect(dialog.locator('[data-testid="lobby-password"]')).toHaveText(oldPassword);

    // A recreated lobby uses the new one.
    await dialog.locator('[data-testid="lobby-recreate-btn"]').click();
    const second = await waitForLobbyRow(context, game.pk, undefined, { previousId: first.id });
    expect(second.password).toBe(newPassword);
    expect((await getSimLobby(context, second.lobby_id!)).password).toBe(newPassword);
    await expect(dialog.locator('[data-testid="lobby-password"]')).toHaveText(newPassword, {
      timeout: 30_000,
    });

    // The replaced lobby is closed in dota_lobby.
    await expect
      .poll(async () => (await sim.get(context, `lobbies/${first.lobby_id}`)).status(), {
        timeout: 30_000,
      })
      .toBe(404);
  });
});
