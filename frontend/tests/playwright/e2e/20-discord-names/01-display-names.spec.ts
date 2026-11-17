/**
 * Context-aware Discord display names.
 *
 * Populate seeds three DTX-only users (populate_discord_name_sync_users):
 *   - name_sync_dragonclaw: global name "GwaihirTheWindlord", DTX server
 *     nickname "DragonClaw"
 *   - name_sync_globalonly: global name "WindlordGlobal", no server nickname
 *   - name_sync_noname: no Discord names at all
 *
 * In the DTX org the server nickname wins; outside any org (profile page) the
 * global name wins, then the username. Search in the DTX tournament's
 * add-player modal finds a member by their global name.
 */

import {
  expect,
  getTournamentByKey,
  loginAdmin as loginAdminContext,
  test,
  visitAndWaitForHydration,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';
import {
  NAME_SYNC_GLOBAL_ONLY_USERNAME,
  NAME_SYNC_NO_NAME_USERNAME,
  NAME_SYNC_USERNAME,
} from '../../fixtures/constants';

const DTX_ORG_NAME = 'DTX';

let dtxOrgPk: number;
let dtxTournamentPk: number;
const userPks: Record<string, number> = {};

test.describe('Discord display names (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    await loginAdminContext(context);

    const orgs = await (
      await context.request.get(`${API_URL}/organizations/`)
    ).json();
    const orgList = Array.isArray(orgs) ? orgs : (orgs.results ?? []);
    const dtx = orgList.find((o: { name: string }) => o.name === DTX_ORG_NAME);
    if (!dtx)
      throw new Error(
        `Org "${DTX_ORG_NAME}" not found. Run just db::populate::all`,
      );
    dtxOrgPk = dtx.pk;

    const tournament = await getTournamentByKey(context, 'completed_bracket');
    if (!tournament) throw new Error('No completed_bracket tournament found');
    // The tournament detail serializer nests the league; TournamentData types it as a pk.
    const league = tournament.league as unknown as {
      organization?: { pk: number };
    } | null;
    if (league?.organization?.pk !== dtxOrgPk) {
      throw new Error('completed_bracket is expected to be a DTX tournament');
    }
    dtxTournamentPk = tournament.pk;

    const members = await (
      await context.request.get(`${API_URL}/organizations/${dtxOrgPk}/users/`)
    ).json();
    for (const username of [
      NAME_SYNC_USERNAME,
      NAME_SYNC_GLOBAL_ONLY_USERNAME,
      NAME_SYNC_NO_NAME_USERNAME,
    ]) {
      const member = members.find(
        (u: { username?: string }) => u.username === username,
      );
      if (!member)
        throw new Error(
          `"${username}" is not a DTX member. Run just db::populate::all`,
        );
      userPks[username] = member.pk;
    }

    await context.close();
  });

  test.beforeEach(async ({ loginAdmin }) => {
    await loginAdmin();
  });

  test('@cicd DTX members page shows the DTX server nickname', async ({
    page,
  }) => {
    await visitAndWaitForHydration(page, `/organizations/${dtxOrgPk}`);
    await page.locator('[data-testid="org-tab-users"]').click();

    await page
      .getByPlaceholder('Search members...')
      .first()
      .fill(NAME_SYNC_USERNAME);
    const card = page.locator(`[data-testid="usercard-${NAME_SYNC_USERNAME}"]`);
    await expect(card).toBeVisible({ timeout: 10000 });
    await expect(card.getByTestId('usercard-display-name')).toHaveText(
      'DragonClaw',
    );
  });

  test('@cicd profile page shows the global name, then the username', async ({
    page,
  }) => {
    const header = page
      .locator('[data-testid="user-card-display-name"]')
      .first();

    await visitAndWaitForHydration(
      page,
      `/user/${userPks[NAME_SYNC_USERNAME]}`,
    );
    await expect(header).toHaveText('GwaihirTheWindlord', { timeout: 15000 });
    await expect(page.getByText('DragonClaw', { exact: true })).toHaveCount(0);

    await visitAndWaitForHydration(
      page,
      `/user/${userPks[NAME_SYNC_GLOBAL_ONLY_USERNAME]}`,
    );
    await expect(header).toHaveText('WindlordGlobal', { timeout: 15000 });

    await visitAndWaitForHydration(
      page,
      `/user/${userPks[NAME_SYNC_NO_NAME_USERNAME]}`,
    );
    await expect(header).toHaveText(NAME_SYNC_NO_NAME_USERNAME, {
      timeout: 15000,
    });
  });

  test('@cicd DTX tournament add-player search finds a member by global name', async ({
    page,
  }) => {
    await visitAndWaitForHydration(
      page,
      `/tournament/${dtxTournamentPk}/players`,
    );
    await page.locator('[data-testid="tournamentAddPlayerBtn"]').click();

    const modal = page.locator('[data-testid="add-user-modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });
    await modal.locator('[data-testid="add-user-search"]').fill('gwaihir');

    const result = modal
      .locator(`[data-testid="site-user-result-${NAME_SYNC_USERNAME}"]`)
      .first();
    await expect(result).toBeVisible({ timeout: 10000 });
    await expect(result).toContainText('DragonClaw');
  });
});
