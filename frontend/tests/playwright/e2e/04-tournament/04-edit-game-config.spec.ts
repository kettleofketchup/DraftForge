/**
 * Org admin edits game config on an event tournament (E2E).
 *
 * Uses the auth-matrix fixtures: org pk=8, league pk=9. The org admin is not
 * a league admin/staff nor site staff. Each test creates its own event (and
 * so its own tournament); afterAll deletes those events, which tears down
 * their tournaments.
 */

import type { BrowserContext } from '@playwright/test';

import {
  expect,
  loginAuthMatrixOrgAdmin,
  postWithCsrf,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';
import { getCsrfToken } from '../../fixtures/events';

const AUTH_MATRIX_ORG_PK = 8;
const AUTH_MATRIX_LEAGUE_PK = 9;

const createdEventIds: number[] = [];
const createdTournamentPks: number[] = [];

async function createEventTournament(
  context: BrowserContext,
  leaguePk: number | null,
): Promise<number> {
  const name = `Game Config ${Date.now()}`;
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
  const resp = await postWithCsrf(context, `${API_URL}/events/`, {
    organization: AUTH_MATRIX_ORG_PK,
    name,
    scheduled_at: tomorrow,
    tournament_name: name,
    ...(leaguePk !== null ? { tournament_league: leaguePk } : {}),
    tournament_type: 'single_elimination',
    game_type: 1,
  });
  expect(resp.ok(), `Create event failed: ${await resp.text()}`).toBeTruthy();
  const body = (await resp.json()) as { id: number; tournament: number };
  createdEventIds.push(body.id);
  createdTournamentPks.push(body.tournament);
  return body.tournament;
}

test.describe('Tournament game config editing (e2e)', () => {
  test.describe.configure({ mode: 'serial' });

  let tournamentPk: number;

  test.beforeEach(async ({ context }) => {
    await loginAuthMatrixOrgAdmin(context);
  });

  test.afterAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await loginAuthMatrixOrgAdmin(context);
    const csrf = await getCsrfToken(context);
    for (const id of createdEventIds) {
      const resp = await context.request.delete(`${API_URL}/events/${id}/`, {
        headers: { 'X-CSRFToken': csrf },
      });
      expect(resp.status(), `Delete event ${id} failed`).toBe(204);
    }
    for (const pk of createdTournamentPks) {
      const resp = await context.request.get(`${API_URL}/tournaments/${pk}/`);
      expect(resp.status(), `Tournament ${pk} leaked after event delete`).toBe(
        404,
      );
    }
    await context.close();
  });

  test('org admin sets Turbo on an event tournament', async ({
    context,
    page,
  }) => {
    tournamentPk = await createEventTournament(context, AUTH_MATRIX_LEAGUE_PK);

    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);
    await page.getByTestId('tournament-edit-btn').click();
    await page.getByTestId('tournament-form-tab-config').click();

    const gameMode = page.getByTestId('lobby-config-game-mode');
    await expect(gameMode).toBeVisible();
    await gameMode.click();
    await expect(
      page.getByRole('option', { name: 'Turbo', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole('option', { name: "Captain's Mode", exact: true }),
    ).toBeVisible();
    await page.getByRole('option', { name: 'Turbo', exact: true }).click();

    await expect(page.getByTestId('config-dota-lobby-mode')).toBeEnabled();
    await expect(
      page.getByTestId('config-dota-lobby-from-event'),
    ).toBeVisible();

    await page.getByTestId('tournament-submit-button').click();
    await expect(page.getByRole('dialog')).toBeHidden({ timeout: 10000 });

    await page.reload();
    await page.getByTestId('tournament-edit-btn').click();
    await page.getByTestId('tournament-form-tab-config').click();
    await expect(page.getByTestId('lobby-config-game-mode')).toHaveText(
      'Turbo',
    );

    const resp = await context.request.get(
      `${API_URL}/tournaments/${tournamentPk}/`,
    );
    expect(resp.ok()).toBeTruthy();
    expect((await resp.json()).game_mode).toBe('turbo');
  });

  test('org admin sees no Delete button', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);
    await expect(page.getByTestId('tournament-edit-btn')).toBeVisible();
    await expect(page.getByTestId('tournament-delete-btn')).toBeHidden();
  });

  test('org admin sees no Edit on a leagueless event tournament', async ({
    context,
    page,
  }) => {
    const leaguelessPk = await createEventTournament(context, null);
    await visitAndWaitForHydration(page, `/tournament/${leaguelessPk}`);
    await expect(page.getByTestId('tournamentDetailPage')).toBeVisible();
    await expect(page.getByTestId('tournament-edit-btn')).toBeHidden({
      timeout: 5000,
    });
  });
});
