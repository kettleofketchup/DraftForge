/**
 * Bracket placement on elimination (issue #843)
 *
 * A team knocked out of a bracket gets its Team.placement through every
 * result-entry path. The UI shows placement nowhere yet, so these tests read
 * it from the persisted tournament API payload.
 *
 * Uses dedicated 4-team tournaments reset per test:
 *  - 'bracket_placement_single': single elimination, semis W-R1 P0/P1 feed the final.
 *  - 'bracket_placement_double': double elimination, saved with the toolbar's Save.
 */

import type { Locator, Page } from '@playwright/test';
import {
  clickAndPersistMatchResult,
  expect,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';

type PlacedTeam = { pk: number; placement: number | null };

function matchNode(
  page: Page,
  bracketType: string,
  round: number,
  position: number,
): Locator {
  return page.locator(
    `[data-testid="bracket-match-node"][data-bracket-type="${bracketType}"][data-round="${round}"][data-position="${position}"]`,
  );
}

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

async function openMatch(page: Page, node: Locator): Promise<Locator> {
  await expect(node).toBeVisible({ timeout: 10000 });
  await node.click({ force: true });
  const dialog = page.locator('[data-testid="matchStatsModal"]');
  await expect(dialog).toBeVisible({ timeout: 5000 });
  return dialog;
}

async function closeMatch(page: Page): Promise<void> {
  const dialog = page.locator('[data-testid="matchStatsModal"]');
  await dialog.locator('[data-testid="dialog-close-button"]').click();
  await expect(dialog).toBeHidden({ timeout: 5000 });
  await expect(page).not.toHaveURL(/\/bracket\/match\//);
}

async function slotTeamPk(
  node: Locator,
  slot: 'radiant' | 'dire',
): Promise<number> {
  const pk = await node
    .locator(`[data-testid="bracket-team-slot-${slot}"]`)
    .getAttribute('data-team-pk');
  expect(pk, `${slot} slot team`).not.toBeNull();
  return Number(pk);
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

test.describe('Bracket placement on elimination (e2e)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ loginStaff }) => {
    await loginStaff();
  });

  test('@cicd single elimination: a semi-final loser is placed 3rd, the final sets 1st and 2nd', async ({
    page,
  }) => {
    test.setTimeout(60_000); // Three persisted results and four full page loads.
    const tournamentPk = await resetTournament(
      page,
      'bracket_placement_single',
    );
    await loadBracket(page, tournamentPk);

    const semi1 = matchNode(page, 'winners', 1, 0);
    await expect(semi1).toBeVisible({ timeout: 10000 });
    const semi1Winner = await slotTeamPk(semi1, 'radiant');
    const semi1Loser = await slotTeamPk(semi1, 'dire');

    let dialog = await openMatch(page, semi1);
    await clickAndPersistMatchResult(
      page,
      dialog.locator('[data-testid="radiantWinsButton"]'),
    );
    await closeMatch(page);

    let teams = await persistedPlacements(page, tournamentPk);
    expect(placementOf(teams, semi1Loser)).toBe(3);
    expect(placementOf(teams, semi1Winner)).toBeNull();

    const semi2 = matchNode(page, 'winners', 1, 1);
    const semi2Winner = await slotTeamPk(semi2, 'radiant');
    const semi2Loser = await slotTeamPk(semi2, 'dire');
    dialog = await openMatch(page, semi2);
    await clickAndPersistMatchResult(
      page,
      dialog.locator('[data-testid="radiantWinsButton"]'),
    );
    await closeMatch(page);

    const final = matchNode(page, 'winners', 2, 0);
    await expect(
      final.locator('[data-testid="bracket-team-slot-radiant"]'),
    ).toHaveAttribute('data-team-pk', String(semi1Winner));
    await expect(
      final.locator('[data-testid="bracket-team-slot-dire"]'),
    ).toHaveAttribute('data-team-pk', String(semi2Winner));
    const finalWinner = await slotTeamPk(final, 'radiant');
    const finalLoser = await slotTeamPk(final, 'dire');
    dialog = await openMatch(page, final);
    await clickAndPersistMatchResult(
      page,
      dialog.locator('[data-testid="radiantWinsButton"]'),
    );
    await closeMatch(page);

    teams = await persistedPlacements(page, tournamentPk);
    expect(placementOf(teams, finalWinner)).toBe(1);
    expect(placementOf(teams, finalLoser)).toBe(2);
    expect(placementOf(teams, semi1Loser)).toBe(3);
    expect(placementOf(teams, semi2Loser)).toBe(3);
  });

  test('@cicd double elimination: results saved with the toolbar Save place the eliminated team', async ({
    page,
  }) => {
    const tournamentPk = await resetTournament(
      page,
      'bracket_placement_double',
    );
    await loadBracket(page, tournamentPk);

    // Reseeding leaves unsaved changes, so the modal only records results
    // locally and the toolbar's Save is what sends them to the server.
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
    await expect(
      page.locator('[data-testid="bracket-unsaved-changes"]'),
    ).toBeVisible({ timeout: 10000 });

    for (const position of [0, 1]) {
      const dialog = await openMatch(
        page,
        matchNode(page, 'winners', 1, position),
      );
      await dialog.locator('[data-testid="radiantWinsButton"]').click();
      await closeMatch(page);
    }

    const losersR1 = matchNode(page, 'losers', 1, 0);
    await expect(
      losersR1.locator('[data-testid="bracket-team-slot-dire"]'),
    ).not.toHaveAttribute('data-team-status', 'empty');
    const eliminated = await slotTeamPk(losersR1, 'dire');
    const survivor = await slotTeamPk(losersR1, 'radiant');
    const dialog = await openMatch(page, losersR1);
    await dialog.locator('[data-testid="radiantWinsButton"]').click();
    await closeMatch(page);

    const saved = page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/bracket/tournaments/${tournamentPk}/save/`),
      { timeout: 15000 },
    );
    await page.locator('[data-testid="saveBracketButton"]').click();
    expect((await saved).status()).toBe(200);
    await expect(
      page.locator('[data-testid="bracket-unsaved-changes"]'),
    ).toBeHidden({ timeout: 10000 });

    const teams = await persistedPlacements(page, tournamentPk);
    expect(placementOf(teams, eliminated)).toBe(4);
    expect(placementOf(teams, survivor)).toBeNull();
    expect(teams.filter((t) => t.placement !== null)).toHaveLength(1);
  });
});
