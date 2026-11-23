/**
 * Org member search matches the Discord names a card shows, not just the
 * username. Uses the DTX name-sync users from
 * backend/tests/populate/organizations.py (NAME_SYNC_USERS).
 */

import { expect, test, visitAndWaitForHydration } from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';
import {
  NAME_SYNC_GLOBAL_ONLY_USERNAME,
  NAME_SYNC_USERNAME,
} from '../../fixtures/constants';

const DTX_ORG_NAME = 'DTX';

let dtxPk: number;

test.describe('Org member search by display name (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const resp = await context.request.get(`${API_URL}/organizations/`);
    const orgs: { pk: number; name: string }[] = await resp.json();
    const dtx = orgs.find((o) => o.name === DTX_ORG_NAME);
    if (!dtx) throw new Error('DTX org not found. Run just db::populate::all');
    dtxPk = dtx.pk;
    await context.close();
  });

  test.beforeEach(async ({ page, loginAdmin }) => {
    await loginAdmin();
    await visitAndWaitForHydration(page, `/organizations/${dtxPk}`);
    await page.getByTestId('org-tab-users').click();
  });

  test('finds a member by global Discord name and shows their server nickname', async ({
    page,
  }) => {
    const search = page.getByPlaceholder('Search members...');
    await expect(search).toBeVisible({ timeout: 15000 });

    await search.fill('Gwaihir');
    const card = page.getByTestId(`usercard-${NAME_SYNC_USERNAME}`);
    await expect(card).toBeVisible({ timeout: 10000 });
    await expect(card).toContainText('DragonClaw');
  });

  test('finds a member known only by their global Discord name', async ({
    page,
  }) => {
    const search = page.getByPlaceholder('Search members...');
    await expect(search).toBeVisible({ timeout: 15000 });

    await search.fill('windlordglobal');
    await expect(
      page.getByTestId(`usercard-${NAME_SYNC_GLOBAL_ONLY_USERNAME}`),
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByTestId(`usercard-${NAME_SYNC_USERNAME}`),
    ).toHaveCount(0);
  });
});
