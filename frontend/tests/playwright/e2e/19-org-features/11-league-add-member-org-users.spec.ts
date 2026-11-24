/**
 * Adding a non-member to a league makes them an org member; going back to the
 * org Users tab shows them without a reload.
 */

import type { Page } from '@playwright/test';

import {
  expect,
  loginOrgFeatures,
  orgFeaturesApi,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

interface LeagueRef {
  pk: number;
  name: string;
}

async function usersTabCount(page: Page): Promise<number> {
  const tab = page.getByTestId('org-tab-users');
  await expect(tab).toHaveText(/Users \(\d+\)/);
  return Number((await tab.innerText()).match(/\((\d+)\)/)![1]);
}

test.describe('Org features: league member adds reach the org @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request, context }) => {
    data = await resetOrgFeatures(request);
    await loginOrgFeatures(context, 'admin');
  });

  test.afterEach(async ({ request }) => {
    await resetOrgFeatures(request);
  });

  test('a new league member shows on the org Users tab @cicd', async ({
    context,
    page,
  }) => {
    const org = data.orgs.features;
    const outsider = data.users.outsider;
    const leagues = await orgFeaturesApi<
      LeagueRef[] | { results: LeagueRef[] }
    >(context, 'GET', `/leagues/?organization=${org.pk}`);
    const league = (Array.isArray(leagues) ? leagues : leagues.results)[0];
    expect(league, 'features org has a league').toBeTruthy();

    await visitAndWaitForHydration(page, `/organizations/${org.pk}?tab=users`);
    await expect(page.getByTestId('org-tab-users')).toHaveAttribute(
      'data-state',
      'active',
    );
    const before = await usersTabCount(page);
    // VirtualizedUserGrid leaves off-screen cards out of the DOM; search first.
    const search = page.getByPlaceholder('Search members...');
    await search.fill(outsider.username);
    await expect(page.getByTestId(`usercard-${outsider.username}`)).toHaveCount(
      0,
    );
    await search.clear();
    await page.evaluate(() => {
      (window as Window & { __sameDocument?: boolean }).__sameDocument = true;
    });

    await page.getByTestId('org-tab-leagues').click();
    await page.locator(`a[href="/leagues/${league.pk}"]`).first().click();
    await expect(page).toHaveURL(new RegExp(`/leagues/${league.pk}`));
    await page.getByTestId('league-tab-users').click();

    await page.getByTestId('league-add-member-btn').click();
    const modal = page.getByTestId('add-user-modal');
    await expect(modal).toBeVisible();
    await modal.getByTestId('add-user-search').fill(outsider.username);
    const added = page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/leagues/${league.pk}/members/`),
    );
    await modal.getByTestId(`add-user-btn-${outsider.username}`).click();
    expect((await added).ok()).toBe(true);
    await page.keyboard.press('Escape');
    await expect(modal).toBeHidden();

    await page
      .getByRole('link', { name: org.name, exact: true })
      .first()
      .click();
    await expect(page).toHaveURL(new RegExp(`/organizations/${org.pk}`));
    await page.getByTestId('org-tab-users').click();

    await expect(page.getByTestId('org-tab-users')).toHaveText(
      `Users (${before + 1})`,
    );
    await page.getByPlaceholder('Search members...').fill(outsider.username);
    await expect(
      page.getByTestId(`usercard-${outsider.username}`),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () =>
          (window as Window & { __sameDocument?: boolean }).__sameDocument ===
          true,
      ),
    ).toBe(true);
  });
});
