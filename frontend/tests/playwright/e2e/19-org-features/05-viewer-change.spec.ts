import type { Page } from '@playwright/test';

import { BASE_URL } from '../../fixtures/base-url';
import {
  expect,
  loginOrgFeatures,
  moveEventToRollCall,
  orgFeaturesApi,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

const ROWS = '[data-testid^="contributions-row-"]';

async function logoutWithoutReload(page: Page): Promise<void> {
  await page.locator('header [data-testid="user-avatar"]').first().click();
  await page.getByTestId('navbarLogoutButton').click();
  await expect(page.locator('header [data-testid="user-avatar"]')).toHaveCount(0);
}

test.describe('Org features: viewer changes @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test('private org member sees only their own row, then nothing after logout @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'private_member');
    await visitAndWaitForHydration(page, `/organizations/${data.orgs.private.pk}?tab=contributions`);

    await expect(page.getByTestId('contributions-org-total')).toContainText('5');
    await expect(page.getByTestId('contributions-members-private')).toBeVisible();
    const rows = page.locator(ROWS);
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toHaveAttribute('data-own', 'true');
    await expect(rows.first().locator('td').nth(1)).toHaveText('3');

    await logoutWithoutReload(page);
    await expect(rows).toHaveCount(0);
    await expect(page.getByTestId('contributions-org-total')).toContainText('5');
    await expect(page.getByTestId('contributions-members-private')).toBeVisible();
    await expect(page.getByText(/Session expired/)).toHaveCount(0);
  });

  test('anonymous visitor sees only the private org total @cicd', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${data.orgs.private.pk}?tab=contributions`);
    await expect(page.getByTestId('contributions-org-total')).toContainText('5');
    await expect(page.getByTestId('contributions-members-private')).toBeVisible();
    await expect(page.locator(ROWS)).toHaveCount(0);
  });

  test('logout without reload clears the admin leaderboard rows @cicd', async ({ page, context }) => {
    await loginOrgFeatures(context, 'admin');
    await visitAndWaitForHydration(page, `/organizations/${data.orgs.features.pk}?tab=contributions`);
    const rows = page.locator(ROWS);
    await expect(rows).toHaveCount(2);
    await expect(page.getByTestId('contributions-admin')).toBeVisible();

    await logoutWithoutReload(page);
    await expect(rows).toHaveCount(0);
    await expect(page.getByTestId('contributions-admin')).toHaveCount(0);
    await expect(page.getByTestId('contributions-members-signin')).toBeVisible();
    await expect(page.getByTestId('contributions-org-total')).toContainText('15');
    await expect(page.getByText(/Session expired/)).toHaveCount(0);
  });

  test('a revoked promoter gets no session toast and the tab bounces @cicd', async ({
    page,
    context,
    browser,
  }) => {
    const orgPk = data.orgs.features.pk;
    const eventPk = data.events.upcoming.pk;
    await loginOrgFeatures(context, 'promoter');
    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=promotion`);
    await expect(page.getByTestId('promo-dashboard')).toBeVisible();
    await expect(page.getByTestId(`promo-event-${eventPk}`)).toBeVisible();

    const adminContext = await browser.newContext({ baseURL: BASE_URL, ignoreHTTPSErrors: true });
    try {
      await loginOrgFeatures(adminContext, 'admin');
      await orgFeaturesApi(
        adminContext,
        'DELETE',
        `/organizations/${orgPk}/promoters/${data.users.promoter.pk}/`,
      );
    } finally {
      await adminContext.close();
    }

    const denied = page.waitForResponse(
      (r) => r.url().includes(`/promotion/events/${eventPk}/candidates/`) && r.status() === 403,
    );
    await page.getByTestId(`promo-event-${eventPk}`).click();
    const body = (await (await denied).json()) as { code?: string };
    expect(body.code).toBe('not_permitted');
    await expect(page.getByTestId('promo-candidates-error')).toBeVisible();
    await expect(page.getByText(/Session expired/)).toHaveCount(0);

    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=promotion`);
    await expect(page.getByTestId('org-tab-users')).toBeVisible();
    await expect(page).not.toHaveURL(/tab=promotion/);
    await expect(page.getByTestId('org-tab-leagues')).toHaveAttribute('data-state', 'active');
    await expect(page.getByTestId('org-tab-promotion')).toHaveCount(0);
    await expect(page.getByTestId('org-tab-contributions')).toBeVisible();
    await expect(page.getByText(/Session expired/)).toHaveCount(0);
  });

  test('logout without reload hides Complete and the staff editor on a roll-call event @cicd', async ({
    page,
    context,
  }) => {
    const eventPk = data.events.upcoming.pk;
    await loginOrgFeatures(context, 'admin');
    await moveEventToRollCall(context, eventPk);
    await visitAndWaitForHydration(page, `/events/${eventPk}`);
    await expect(page.getByTestId('event-complete-btn')).toBeVisible();
    await expect(page.getByTestId('event-host-edit-btn')).toBeVisible();

    await logoutWithoutReload(page);
    await expect(page.getByTestId('event-complete-btn')).toHaveCount(0);
    await expect(page.getByTestId('event-host-edit-btn')).toHaveCount(0);
    await expect(page.getByText(/Session expired/)).toHaveCount(0);
  });
});
