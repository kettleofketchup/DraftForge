/**
 * The Lobby bots tab lists the simulated bots and their league access.
 *
 * sim_bot_1..3 administer the Lobby Test League (steam league 17940) and
 * sim_bot_4 administers none (docker/dota-lobby/simulator.yaml). A site admin
 * sees three verified rows and one missing row; bots sort by SteamID, which
 * puts sim_bot_4 last. An org admin sees only the three holders.
 */

import {
  expect,
  hasSimulator,
  LeaguePage,
  loginAdmin,
  loginDotaLobby,
  resetDotaLobbyData,
  SIMULATOR_SKIP_REASON,
  test,
  type DotaLobbyTestData,
} from '../../fixtures';

const PROFILE_URL = /^https:\/\/steamcommunity\.com\/profiles\/\d{17}$/;

test.describe('Dota lobby: league bot access (e2e)', () => {
  let data: DotaLobbyTestData;

  test.beforeEach(async ({ context }) => {
    test.skip(!(await hasSimulator(context)), SIMULATOR_SKIP_REASON);
    data = await resetDotaLobbyData(context);
  });

  test('@cicd an org admin deep-linking to the tab sees only the holders', async ({
    context,
    page,
  }) => {
    await loginDotaLobby(context, 'staff');
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(data.league.pk, 'lobby-bots');

    const table = page.locator('[data-testid="bot-access-table"]');
    await expect(table).toBeVisible({ timeout: 20_000 });
    await leaguePage.assertTabActive('lobby-bots');

    for (const position of [1, 2, 3]) {
      await expect(
        page.locator(`[data-testid="bot-access-row-${position}"]`),
      ).toContainText('Verified');
    }
    await expect(page.locator('[data-testid="bot-access-row-4"]')).toHaveCount(
      0,
    );
    await expect(
      page.locator('[data-testid="bot-access-summary"]'),
    ).toContainText('3 bots can host lobbies');
    await expect(
      page.locator('[data-testid="bot-access-roster-note"]'),
    ).toBeVisible();
  });

  test('@cicd a site admin sees every bot and its access', async ({
    context,
    page,
  }) => {
    await loginAdmin(context);
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(data.league.pk, 'lobby-bots');

    const table = page.locator('[data-testid="bot-access-table"]');
    await expect(table).toBeVisible({ timeout: 20_000 });
    await expect(
      page.locator('[data-testid="bot-access-roster-note"]'),
    ).toHaveCount(0);

    for (const position of [1, 2, 3]) {
      await expect(
        page.locator(`[data-testid="bot-access-row-${position}"]`),
      ).toContainText('Verified');
      await expect(
        page.locator(`[data-testid="bot-access-profile-link-${position}"]`),
      ).toHaveAttribute('href', PROFILE_URL);
    }
    const missing = page.locator('[data-testid="bot-access-row-4"]');
    await expect(missing).toContainText('Missing');
    await expect(
      page.locator('[data-testid="bot-access-profile-link-4"]'),
    ).toHaveAttribute('href', PROFILE_URL);

    const admins = page.locator('[data-testid="bot-access-admins-link"]');
    await expect(admins).toHaveAttribute(
      'href',
      `https://www.dota2.com/league/${data.league.steam_league_id}/admins`,
    );
    await expect(admins).toHaveAttribute('rel', /noopener/);
  });

  test('@cicd refresh re-checks access and keeps the rows', async ({
    context,
    page,
  }) => {
    test.setTimeout(60_000);
    await loginDotaLobby(context, 'staff');
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(data.league.pk, 'lobby-bots');
    await expect(
      page.locator('[data-testid="bot-access-row-1"]'),
    ).toContainText('Verified', { timeout: 20_000 });

    const refreshed = page.waitForResponse(
      (r) =>
        r.url().includes(`/leagues/${data.league.pk}/bot-access/refresh/`) &&
        r.request().method() === 'POST',
      { timeout: 30_000 },
    );
    await page.locator('[data-testid="bot-access-refresh"]').click();
    expect((await refreshed).status()).toBe(200);

    await expect(
      page.locator('[data-testid="bot-access-refresh"]'),
    ).toBeEnabled({ timeout: 30_000 });
    await expect(
      page.locator('[data-testid="bot-access-row-1"]'),
    ).toContainText('Verified');
    await expect(
      page.locator('[data-testid="bot-access-row-3"]'),
    ).toContainText('Verified');
    await expect(page.locator('[data-testid="bot-access-row-4"]')).toHaveCount(
      0,
    );
    await expect(
      page.locator('[data-testid="bot-access-refresh-outcome"]'),
    ).toHaveCount(0);
    await expect(
      page.locator('[data-sonner-toast][data-type="error"]'),
    ).toHaveCount(0);
  });

  test('@cicd league staff get no tab, and the direct URL falls back to info', async ({
    context,
    page,
  }) => {
    await loginDotaLobby(context, 'league-staff');
    const leaguePage = new LeaguePage(page);
    await leaguePage.goto(data.league.pk, 'lobby-bots');

    await leaguePage.assertTabActive('info');
    await expect(leaguePage.lobbyBotsTab).toHaveCount(0);
    await expect(leaguePage.botAccessPanel).toHaveCount(0);
  });
});
