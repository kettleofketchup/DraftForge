/**
 * Edit User on League Page
 *
 * @cicd smoke test verifying that editing a user's Friend ID on a league page
 * saves and shows the new value when the modal reopens.
 *
 * Uses isolated "User Edit League" data — does not touch other test entities.
 */

import {
  expect,
  fillEditField,
  nextSteamAccountId,
  openEditModal,
  readEditField,
  saveEditModal,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

const USER_EDIT_LEAGUE_NAME = 'User Edit League';
const ALT_STEAM_ACCOUNT_ID = 2_900_000_301;

let leaguePk: number;

test.describe('Edit User on League Page (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Look up User Edit League by name
    const leaguesResp = await context.request.get(`${API_URL}/leagues/`);
    const leagues = await leaguesResp.json();
    const leagueList = Array.isArray(leagues)
      ? leagues
      : (leagues.results ?? []);
    const editLeague = leagueList.find(
      (l: { name: string }) => l.name === USER_EDIT_LEAGUE_NAME,
    );
    if (!editLeague)
      throw new Error(
        `League "${USER_EDIT_LEAGUE_NAME}" not found. Run just db::populate::all`,
      );
    leaguePk = editLeague.pk;

    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  // Dedicated user — see USER_EDIT_USERS in backend/tests/data/users.py.
  const TARGET_USERNAME = 'edit_user_league';

  test('@cicd smoke: edit user Friend ID via league user card', async ({
    page,
  }) => {
    await visitAndWaitForHydration(page, `/leagues/${leaguePk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    const usersTab = page.locator('[data-testid="league-tab-users"]');
    await expect(usersTab).toBeVisible({ timeout: 5000 });
    await usersTab.click();

    const targetCard = page.locator(
      `[data-testid="usercard-${TARGET_USERNAME}"]`,
    );
    await expect(targetCard).toBeVisible({ timeout: 10000 });

    await openEditModal(page, targetCard);
    const originalId = await readEditField(page, 'steam_account_id');
    const newId = nextSteamAccountId(originalId, ALT_STEAM_ACCOUNT_ID);

    await fillEditField(page, 'steam_account_id', newId);
    await saveEditModal(page);

    // Reopening re-seeds the form from the cached user, so the saved id shows.
    await openEditModal(page, targetCard);
    await expect(
      page.locator('[data-testid="edit-user-steam_account_id"]'),
    ).toHaveValue(newId);
    await fillEditField(page, 'steam_account_id', originalId);
    await saveEditModal(page);
  });
});
