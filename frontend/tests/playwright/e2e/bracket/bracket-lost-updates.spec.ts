/**
 * Bracket writes that must not undo each other (issue #963)
 *
 * Uses 'bracket_unset_winner': 4 teams, double elimination, all games pending.
 *
 *  1. A Save built from a bracket another admin has since changed returns 409
 *     `bracket_stale`, keeps the local edits, and Reload loads the server copy.
 *  2. Two winners entered back to back both persist, with the first result's
 *     response held until the second request is sent.
 */

import type { Locator, Page, Route } from '@playwright/test';
import { expect, test, visitAndWaitForHydration } from '../../fixtures';
import { getCsrfToken } from '../../fixtures/events';

type TeamRef = { pk: number } | null;
type ApiGame = {
  pk: number;
  bracket_type: string;
  round: number;
  position: number;
  status: string;
  radiant_team: TeamRef;
  dire_team: TeamRef;
  winning_team: TeamRef;
};

let tournamentPk = 0;

const nodeSelector = (position: number) =>
  `[data-testid="bracket-match-node"][data-bracket-type="winners"][data-round="1"][data-position="${position}"]`;

async function loadBracket(page: Page): Promise<void> {
  await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);
  await expect(page.locator('[data-testid="bracketContainer"]')).toBeVisible({
    timeout: 15000,
  });
  await page.waitForLoadState('networkidle');
}

async function fetchGame(page: Page, position: number): Promise<ApiGame> {
  const resp = await page
    .context()
    .request.get(`/api/bracket/tournaments/${tournamentPk}/`);
  expect(resp.status()).toBe(200);
  const game = ((await resp.json()).matches as ApiGame[]).find(
    (g) =>
      g.bracket_type === 'winners' && g.round === 1 && g.position === position,
  );
  if (!game) throw new Error(`winners R1 P${position} not found`);
  return game;
}

async function openModal(page: Page, position: number): Promise<Locator> {
  const node = page.locator(nodeSelector(position));
  await expect(node).toBeVisible({ timeout: 10000 });
  await node.click();
  const dialog = page.locator('[data-testid="matchStatsModal"]');
  await expect(dialog).toBeVisible({ timeout: 5000 });
  return dialog;
}

async function closeModal(page: Page): Promise<void> {
  const dialog = page.locator('[data-testid="matchStatsModal"]');
  await dialog.locator('[data-testid="dialog-close-button"]').click();
  await expect(dialog).toBeHidden({ timeout: 5000 });
}

test.describe('Bracket lost updates (e2e)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ loginStaff, page }) => {
    await loginStaff();
    const reset = await page
      .context()
      .request.post('/api/tests/reset-tournament/bracket_unset_winner/');
    expect(reset.status()).toBe(200);
    tournamentPk = (await reset.json()).pk;
  });

  test('@cicd a stale Save is refused, keeps the edits, and Reload loads the newer result', async ({
    page,
  }) => {
    await loadBracket(page);

    await page
      .locator(
        '[data-testid="reseedBracketButton"], [data-testid="generateBracketButton"]',
      )
      .click();
    await page.locator('[data-testid="randomSeedingOption"]').click();
    const regenerate = page.locator(
      '[data-testid="regenerateBracketConfirmButton"]',
    );
    await regenerate.click();
    await regenerate.waitFor({ state: 'hidden', timeout: 5000 });
    const unsaved = page.locator('[data-testid="bracket-unsaved-changes"]');
    await expect(unsaved).toBeVisible({ timeout: 10000 });

    const target = await fetchGame(page, 0);
    const advanced = await page
      .context()
      .request.post(`/api/bracket/games/${target.pk}/advance-winner/`, {
        data: { winner: 'radiant' },
        headers: { 'X-CSRFToken': await getCsrfToken(page.context()) },
      });
    expect(advanced.status()).toBe(200);

    const saved = page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/bracket/tournaments/${tournamentPk}/save/`),
      { timeout: 15000 },
    );
    await page.locator('[data-testid="saveBracketButton"]').click();
    const response = await saved;
    expect(response.status()).toBe(409);
    expect((await response.json()).code).toBe('bracket_stale');

    const toast = page.locator('[data-sonner-toast][data-type="error"]');
    await expect(toast).toContainText('changed since you loaded it', {
      timeout: 10000,
    });
    await expect(unsaved).toBeVisible();
    expect((await fetchGame(page, 0)).winning_team?.pk).toBe(
      target.radiant_team?.pk,
    );

    await toast.getByRole('button', { name: 'Reload bracket' }).click();
    await expect(unsaved).toBeHidden({ timeout: 10000 });
    await expect(
      page
        .locator(nodeSelector(0))
        .locator('[data-testid="bracket-winner-check-radiant"]'),
    ).toBeVisible({ timeout: 10000 });
  });

  test('@cicd two winners entered back to back both persist', async ({
    page,
  }) => {
    const first = await fetchGame(page, 0);
    const second = await fetchGame(page, 1);
    await loadBracket(page);

    const secondSent = page
      .waitForRequest(
        (r) =>
          r.method() === 'POST' &&
          r.url().includes(`/bracket/games/${second.pk}/advance-winner/`),
        { timeout: 15000 },
      )
      .then(() => true)
      .catch(() => false);
    await page.route(
      `**/bracket/games/${first.pk}/advance-winner/`,
      async (route: Route) => {
        const response = await route.fetch();
        await secondSent;
        await route.fulfill({ response });
      },
    );
    const firstDone = page.waitForResponse(
      (r) => r.url().includes(`/bracket/games/${first.pk}/advance-winner/`),
      { timeout: 20000 },
    );

    let dialog = await openModal(page, 0);
    await dialog.locator('[data-testid="radiantWinsButton"]').click();
    await closeModal(page);
    dialog = await openModal(page, 1);
    await dialog.locator('[data-testid="direWinsButton"]').click();

    expect(await secondSent).toBe(true);
    expect((await firstDone).status()).toBe(200);
    await closeModal(page);
    await expect(
      page.locator('[data-testid="bracket-unsaved-changes"]'),
    ).toBeHidden({ timeout: 10000 });

    expect((await fetchGame(page, 0)).winning_team?.pk).toBe(
      first.radiant_team?.pk,
    );
    expect((await fetchGame(page, 1)).winning_team?.pk).toBe(
      second.dire_team?.pk,
    );
    await expect(
      page
        .locator(nodeSelector(0))
        .locator('[data-testid="bracket-winner-check-radiant"]'),
    ).toBeVisible();
    await expect(
      page
        .locator(nodeSelector(1))
        .locator('[data-testid="bracket-winner-check-dire"]'),
    ).toBeVisible();
  });
});
