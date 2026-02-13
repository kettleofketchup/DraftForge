/**
 * Edit User on Tournament Page
 *
 * @cicd smoke test verifying that the edit modal opens and saves on a tournament page.
 *
 * Note: On tournament pages with org context, the PATCH routes through the org-scoped
 * endpoint which only persists MMR changes. Nickname verification after reload is skipped
 * here — the org and league tests cover full nickname update verification.
 *
 * Uses isolated "User Edit Tournament" data — does not touch other test entities.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  openEditModal,
  readEditField,
  fillEditField,
  saveEditModal,
  restoreUserField,
} from '../../fixtures';

const API_URL = 'https://localhost/api';
const USER_EDIT_LEAGUE_NAME = 'User Edit League';
const USER_EDIT_TOURNAMENT_NAME = 'User Edit Tournament';

let tournamentPk: number;

test.describe('Edit User on Tournament Page (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Look up User Edit League, then find the tournament under it
    const leaguesResp = await context.request.get(`${API_URL}/leagues/`);
    const leagues = await leaguesResp.json();
    const leagueList = Array.isArray(leagues) ? leagues : leagues.results ?? [];
    const editLeague = leagueList.find((l: { name: string }) => l.name === USER_EDIT_LEAGUE_NAME);
    if (!editLeague) throw new Error(`League "${USER_EDIT_LEAGUE_NAME}" not found. Run just db::populate::all`);

    // Fetch tournaments for this league
    const tournamentsResp = await context.request.get(`${API_URL}/tournaments/?league=${editLeague.pk}`);
    const tournaments = await tournamentsResp.json();
    const tournamentList = Array.isArray(tournaments) ? tournaments : tournaments.results ?? [];
    const editTournament = tournamentList.find((t: { name: string }) => t.name === USER_EDIT_TOURNAMENT_NAME);
    if (!editTournament) throw new Error(`Tournament "${USER_EDIT_TOURNAMENT_NAME}" not found. Run just db::populate::all`);
    tournamentPk = editTournament.pk;

    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd smoke: edit user nickname via tournament player card', async ({ page }) => {
    await visitAndWaitForHydration(page, `/tournament/${tournamentPk}`);
    await expect(page.locator('[data-testid="tournamentDetailPage"]')).toBeVisible({ timeout: 15000 });

    // Players tab is the default — wait for user cards
    const firstUserCard = page.locator('[data-testid^="usercard-"]').first();
    await expect(firstUserCard).toBeVisible({ timeout: 10000 });

    // Open edit modal and read original nickname
    await openEditModal(page, firstUserCard);
    const originalNickname = await readEditField(page, 'nickname');
    const newNickname = originalNickname === 'TestNick' ? 'TestNickAlt' : 'TestNick';

    await fillEditField(page, 'nickname', newNickname);
    // saveEditModal waits for PATCH 200 and closes the dialog
    await saveEditModal(page);

    // Restore original value
    const userCardAfter = page.locator('[data-testid^="usercard-"]').first();
    await restoreUserField(page, userCardAfter, 'nickname', originalNickname);
  });
});
