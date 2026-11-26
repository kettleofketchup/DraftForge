/**
 * Bracket Save refuses to reopen a team with a player on a live team (issue #922)
 *
 * Uses 'placement_reopen_conflict': single elimination where Reopen B beat
 * Reopen A (placement 3) and reopen_conflict_a2 has since joined live Reopen C.
 * Reseeding and saving would clear A's placement, so Save must return 409.
 */

import type { Page } from '@playwright/test';
import { expect, test, visitAndWaitForHydration } from '../../fixtures';

type PlacedTeam = { pk: number; name: string; placement: number | null };
type TeamRef = { pk: number } | number | null | undefined;
type SavedMatch = {
  bracket_type: string;
  round: number;
  position: number;
  winning_team?: TeamRef;
};

async function resetTournament(page: Page, key: string): Promise<number> {
  const resp = await page
    .context()
    .request.post(`/api/tests/reset-tournament/${key}/`);
  expect(resp.status()).toBe(200);
  return (await resp.json()).pk as number;
}

async function loadBracket(page: Page, tournamentPk: number): Promise<void> {
  await visitAndWaitForHydration(page, `/tournament/${tournamentPk}/games`);
  await expect(page.locator('[data-testid="bracketContainer"]')).toBeVisible({
    timeout: 15000,
  });
  await page.waitForLoadState('networkidle');
}

async function persistedPlacements(
  page: Page,
  tournamentPk: number,
): Promise<PlacedTeam[]> {
  const response = await page
    .context()
    .request.get(`/api/tournaments/${tournamentPk}/`);
  expect(response.status()).toBe(200);
  const body = await response.json();
  return body.teams as PlacedTeam[];
}

function placementOf(teams: PlacedTeam[], pk: number): number | null {
  const team = teams.find((t) => t.pk === pk);
  expect(team, `team ${pk}`).toBeDefined();
  return team!.placement;
}

function teamPk(teams: PlacedTeam[], name: string): number {
  const team = teams.find((t) => t.name === name);
  expect(team, name).toBeDefined();
  return team!.pk;
}

async function semi1WinnerPk(
  page: Page,
  tournamentPk: number,
): Promise<number | null> {
  const response = await page
    .context()
    .request.get(`/api/bracket/tournaments/${tournamentPk}/`);
  expect(response.status()).toBe(200);
  const matches = (await response.json()).matches as SavedMatch[];
  const semi1 = matches.find(
    (m) => m.bracket_type === 'winners' && m.round === 1 && m.position === 0,
  );
  expect(semi1, 'semi-final 1').toBeDefined();
  const winner = semi1!.winning_team;
  if (winner == null) return null;
  return typeof winner === 'number' ? winner : winner.pk;
}

test.describe('Bracket Save reopen roster conflict (e2e)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ loginStaff }) => {
    await loginStaff();
  });

  test('@cicd toolbar Save that would reopen a knocked-out team with a player on a live team is refused', async ({
    page,
  }) => {
    const tournamentPk = await resetTournament(
      page,
      'placement_reopen_conflict',
    );
    const before = await persistedPlacements(page, tournamentPk);
    const teamA = teamPk(before, 'Reopen A');
    const teamB = teamPk(before, 'Reopen B');
    expect(placementOf(before, teamA)).toBe(3);
    expect(await semi1WinnerPk(page, tournamentPk)).toBe(teamB);

    await loadBracket(page, tournamentPk);

    await page
      .locator(
        '[data-testid="reseedBracketButton"], [data-testid="generateBracketButton"]',
      )
      .click();
    const randomSeeding = page.locator('[data-testid="randomSeedingOption"]');
    await randomSeeding.waitFor({ state: 'visible', timeout: 5000 });
    await randomSeeding.click();
    const regenerate = page.locator(
      '[data-testid="regenerateBracketConfirmButton"]',
    );
    await regenerate.waitFor({ state: 'visible', timeout: 5000 });
    await regenerate.click();
    await regenerate.waitFor({ state: 'hidden', timeout: 5000 });
    const unsaved = page.locator('[data-testid="bracket-unsaved-changes"]');
    await expect(unsaved).toBeVisible({ timeout: 10000 });

    const saved = page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/bracket/tournaments/${tournamentPk}/save/`),
      { timeout: 15000 },
    );
    await page.locator('[data-testid="saveBracketButton"]').click();
    expect((await saved).status()).toBe(409);

    await expect(
      page.locator('[data-sonner-toast][data-type="error"]'),
    ).toContainText('also play for', { timeout: 10000 });
    await expect(unsaved).toBeVisible();

    const after = await persistedPlacements(page, tournamentPk);
    expect(placementOf(after, teamA)).toBe(3);
    expect(await semi1WinnerPk(page, tournamentPk)).toBe(teamB);
  });
});
