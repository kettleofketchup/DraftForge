/**
 * Who sees the lobby password.
 *
 * The series event's second game (Lobby Gamma vs Lobby Delta) gets a lobby:
 * created in the simulated dota_lobby when it runs, otherwise a seeded row
 * (the CI stack), since who sees the password is DraftForge's alone. Then,
 * with the fixed series password:
 * - a registered player (approved signup, on no team) sees it on the event page;
 * - a rostered player (Lobby Gamma's captain) sees it in the match dialog;
 * - a signed-in user who is neither, and league staff who are not org staff,
 *   see it nowhere: the event endpoint answers 404, the lobby API leaves it
 *   out, and neither page shows it.
 */

import {
  expect,
  loginDotaLobby,
  openBracket,
  openMatchModal,
  requestLobby,
  resetDotaLobbyData,
  hasSimulator,
  seedLobbyRow,
  test,
  visitAndWaitForHydration,
  waitForLobbyRow,
  type DotaLobbyRole,
  type DotaLobbyTestData,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

test.describe('Dota lobby: password visibility (e2e)', () => {
  test.describe.configure({ mode: 'serial' });

  let data: DotaLobbyTestData;
  let gamePk: number;

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(90_000);
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      const simulated = await hasSimulator(context);
      data = await resetDotaLobbyData(context);
      gamePk = data.series_event.tournament.games[1].pk;
      if (simulated) {
        await loginDotaLobby(context, 'staff');
        await requestLobby(context, gamePk);
        await waitForLobbyRow(context, gamePk);
      } else {
        const row = await seedLobbyRow(context, gamePk);
        expect(row.state).toBe('waiting');
        expect(row.password).toBe(data.fixed_password);
      }
    } finally {
      await context.close();
    }
  });

  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  async function eventPasswordStatus(
    context: import('@playwright/test').BrowserContext,
  ): Promise<{ status: number; password?: string }> {
    const resp = await context.request.get(
      `${API_URL}/events/${data.series_event.pk}/lobby-password/`,
    );
    return {
      status: resp.status(),
      password: resp.ok() ? (await resp.json()).password : undefined,
    };
  }

  async function gameLobby(context: import('@playwright/test').BrowserContext) {
    const resp = await context.request.get(`${API_URL}/games/${gamePk}/lobby/`);
    expect(resp.status()).toBe(200);
    return resp.json();
  }

  test('@cicd a registered player sees the password on the event page', async ({
    context,
    page,
  }) => {
    await loginDotaLobby(context, 'registered');
    expect(await eventPasswordStatus(context)).toEqual({
      status: 200,
      password: data.fixed_password,
    });

    await visitAndWaitForHydration(page, `/events/${data.series_event.pk}`);
    await expect(page.locator('[data-testid="event-lobby-password-value"]')).toHaveText(
      data.fixed_password,
      { timeout: 15_000 },
    );

    // Not on a team of this game: the lobby API leaves the password out.
    const body = await gameLobby(context);
    expect(body.lobby.password).toBeUndefined();
  });

  test('@cicd a rostered player sees the password in the match dialog', async ({
    context,
    page,
  }) => {
    await loginDotaLobby(context, 'rostered');
    const body = await gameLobby(context);
    expect(body.is_player).toBe(true);
    expect(body.lobby.password).toBe(data.fixed_password);

    await openBracket(page, data.series_event.tournament.pk);
    const dialog = await openMatchModal(page, gamePk);
    await expect(dialog.locator('[data-testid="lobby-password"]')).toHaveText(
      data.fixed_password,
      { timeout: 15_000 },
    );
  });

  const hidden: { role: DotaLobbyRole; title: string; manages: boolean }[] = [
    { role: 'unregistered', title: 'a user who is not registered', manages: false },
    { role: 'league-staff', title: 'league staff who are not org staff', manages: true },
  ];

  for (const { role, title, manages } of hidden) {
    test(`@cicd ${title} never sees the password`, async ({ context, page }) => {
      await loginDotaLobby(context, role);
      expect((await eventPasswordStatus(context)).status).toBe(404);

      const body = await gameLobby(context);
      expect(body.can_manage).toBe(manages);
      expect(body.lobby.password ?? null).toBeNull();

      // The card only renders from its own query: wait for the page's request
      // to settle (404) before checking that nothing shows, so the absence
      // check cannot pass on a page that has not asked yet.
      const passwordPath = `/api/events/${data.series_event.pk}/lobby-password/`;
      const passwordResponse = page.waitForResponse(
        (r) => new URL(r.url()).pathname === passwordPath && r.request().method() === 'GET',
        { timeout: 20_000 },
      );
      await visitAndWaitForHydration(page, `/events/${data.series_event.pk}`);
      await expect(page.locator('[data-testid="event-tab-details"]')).toBeVisible({
        timeout: 15_000,
      });
      expect((await passwordResponse).status()).toBe(404);
      await expect(page.locator('[data-testid="event-lobby-password"]')).toHaveCount(0);

      await openBracket(page, data.series_event.tournament.pk);
      const dialog = await openMatchModal(page, gamePk);
      await expect(dialog.locator('[data-testid="lobby-state-badge"]')).toBeVisible({
        timeout: 15_000,
      });
      await expect(dialog.locator('[data-testid="lobby-staff-controls"]')).toHaveCount(
        manages ? 1 : 0,
      );
      await expect(dialog.locator('[data-testid="lobby-password"]')).toHaveCount(0);
    });
  }
});
