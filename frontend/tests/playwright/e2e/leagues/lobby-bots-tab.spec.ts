/**
 * The Lobby bots league tab is shown to league admins only.
 *
 * League 1 is linked to a Steam league, but whether the lobby service runs
 * depends on the stack, so these tests check visibility and that the panel
 * renders, not its service state.
 */

import {
  expect,
  LeaguePage,
  loginLeagueAdmin,
  loginLeagueStaff,
  test,
} from '../../fixtures';

const LEAGUE_PK = 1;

test.describe('League page - Lobby bots tab (e2e)', () => {
  test('@cicd a logged-out visitor gets no tab', async ({ page }) => {
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(LEAGUE_PK);

    await expect(leaguePage.infoTab).toBeVisible();
    await expect(leaguePage.lobbyBotsTab).toHaveCount(0);
  });

  test('@cicd league staff get no tab, and the direct URL falls back to info', async ({
    context,
    page,
  }) => {
    await loginLeagueStaff(context);
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(LEAGUE_PK, 'lobby-bots');

    await leaguePage.assertTabActive('info');
    await expect(leaguePage.lobbyBotsTab).toHaveCount(0);
    await expect(leaguePage.botAccessPanel).toHaveCount(0);
  });

  test('@cicd a league admin opens the tab and sees the panel', async ({
    context,
    page,
  }) => {
    await loginLeagueAdmin(context);
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(LEAGUE_PK);

    await expect(leaguePage.lobbyBotsTab).toBeVisible();
    await leaguePage.clickLobbyBotsTab();
    await expect(leaguePage.botAccessPanel).toBeVisible();
    await leaguePage.assertTabActive('lobby-bots');
  });

  test('@cicd a league admin deep-linking to the tab stays on it', async ({
    context,
    page,
  }) => {
    await loginLeagueAdmin(context);
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(LEAGUE_PK, 'lobby-bots');

    await expect(leaguePage.botAccessPanel).toBeVisible();
    await leaguePage.assertTabActive('lobby-bots');
    await expect(page).toHaveURL(
      new RegExp(`/leagues/${LEAGUE_PK}/lobby-bots`),
    );
  });
});
