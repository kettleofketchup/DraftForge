/**
 * Unlinking a Steam match returns the bracket game to pending (issue #921).
 *
 * Uses the 'bracket_unset_winner' tournament; Winners R1 position 0 is
 * pending after a reset, so this also pins unlinking a never-linked game.
 */

import type { Page } from '@playwright/test';
import { expect, test, visitAndWaitForHydration } from '../../fixtures';
import { getCsrfToken } from '../../fixtures/events';

let tournamentPk = 0;

const TARGET_MATCH_SELECTOR =
  '[data-testid="bracket-match-node"][data-bracket-type="winners"][data-round="1"][data-position="0"]';

type ApiGame = {
  pk: number;
  bracket_type: string;
  round: number;
  position: number;
  status: string;
};

async function fetchTargetGame(page: Page): Promise<ApiGame> {
  const resp = await page
    .context()
    .request.get(`/api/bracket/tournaments/${tournamentPk}/`);
  expect(resp.status()).toBe(200);
  const games = (await resp.json()).matches as ApiGame[];
  const game = games.find(
    (g) => g.bracket_type === 'winners' && g.round === 1 && g.position === 0,
  );
  expect(game).toBeDefined();
  return game!;
}

test.describe('Bracket Steam unlink status (e2e)', () => {
  // Shares the reset tournament with 04-bracket-unset-winner.
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ loginStaff, page }) => {
    await loginStaff();
    const resetResp = await page
      .context()
      .request.post('/api/tests/reset-tournament/bracket_unset_winner/');
    expect(resetResp.status()).toBe(200);
    tournamentPk = (await resetResp.json()).pk;
  });

  test('@cicd unlinking a Steam match keeps the bracket loadable and the game pending', async ({
    page,
  }) => {
    const { pk: gamePk } = await fetchTargetGame(page);

    const unlinkResp = await page
      .context()
      .request.delete(`/api/steam/games/${gamePk}/unlink-match/`, {
        headers: { 'X-CSRFToken': await getCsrfToken(page.context()) },
      });
    expect(unlinkResp.status()).toBe(200);

    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);
    await expect(page.locator('[data-testid="bracketContainer"]')).toBeVisible({
      timeout: 15000,
    });
    const node = page.locator(TARGET_MATCH_SELECTOR);
    await expect(node).toBeVisible({ timeout: 10000 });
    await expect(node).toContainText('Upcoming');
    await expect(page.getByText('No bracket generated yet.')).toHaveCount(0);

    expect((await fetchTargetGame(page)).status).toBe('pending');
  });
});
