/**
 * Edit User on League Page
 *
 * @cicd smoke test verifying that editing a user's nickname on a league page
 * updates the UI successfully.
 *
 * Uses isolated "User Edit League" data — does not touch other test entities.
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

let leaguePk: number;

test.describe('Edit User on League Page (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Look up User Edit League by name
    const leaguesResp = await context.request.get(`${API_URL}/leagues/`);
    const leagues = await leaguesResp.json();
    const leagueList = Array.isArray(leagues) ? leagues : leagues.results ?? [];
    const editLeague = leagueList.find((l: { name: string }) => l.name === USER_EDIT_LEAGUE_NAME);
    if (!editLeague) throw new Error(`League "${USER_EDIT_LEAGUE_NAME}" not found. Run just db::populate::all`);
    leaguePk = editLeague.pk;

    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  // Dedicated user — see USER_EDIT_USERS in backend/tests/data/users.py.
  const TARGET_USERNAME = 'edit_user_league';

  test('@cicd smoke: edit user nickname via league user card', async ({ page }) => {
    await visitAndWaitForHydration(page, `/leagues/${leaguePk}`);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 });

    const usersTab = page.locator('[data-testid="league-tab-users"]');
    await expect(usersTab).toBeVisible({ timeout: 5000 });
    await usersTab.click();

    const targetCard = page.locator(`[data-testid="usercard-${TARGET_USERNAME}"]`);
    await expect(targetCard).toBeVisible({ timeout: 10000 });

    await openEditModal(page, targetCard);
    const originalNickname = await readEditField(page, 'nickname');
    const newNickname = originalNickname === 'TestNick' ? 'TestNickAlt' : 'TestNick';

    await fillEditField(page, 'nickname', newNickname);
    await saveEditModal(page);

    await expect(targetCard.getByText(newNickname).first()).toBeVisible({ timeout: 5000 });

    await restoreUserField(page, targetCard, 'nickname', originalNickname);
  });
});
