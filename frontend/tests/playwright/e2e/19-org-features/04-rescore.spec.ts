import { BASE_URL } from '../../fixtures/base-url';
import {
  expect,
  leaderboardByUser,
  loginOrgFeatures,
  orgFeaturesApi,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

test.describe('Org features: rescoring @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test('changing promo_message with apply-to-past rescores and reset restores Default @cicd', async ({
    page,
    context,
    browser,
  }) => {
    test.setTimeout(60_000);
    const orgPk = data.orgs.features.pk;
    const eventPk = data.events.upcoming.pk;
    const promoterPk = data.users.promoter.pk;
    const template = data.templates.find((t) => t.org_pk === orgPk);
    expect(template).toBeDefined();

    const promoterContext = await browser.newContext({ baseURL: BASE_URL, ignoreHTTPSErrors: true });
    try {
      await loginOrgFeatures(promoterContext, 'promoter');
      const pool = await orgFeaturesApi<{ rows: { user_pk: number }[] }>(
        promoterContext,
        'GET',
        `/organizations/${orgPk}/promotion/events/${eventPk}/candidates/`,
      );
      expect(pool.rows.length).toBeGreaterThan(0);
      await orgFeaturesApi(promoterContext, 'POST', `/organizations/${orgPk}/promotion/events/${eventPk}/sends/`, {
        template_id: template!.pk,
        recipient_id: pool.rows[0].user_pk,
        text: 'Come play in the next event!',
      });
    } finally {
      await promoterContext.close();
    }

    await loginOrgFeatures(context, 'admin');
    const promoterRow = (await leaderboardByUser(context, orgPk)).get(promoterPk);
    expect(promoterRow?.points, 'promoter: 5 (seeded helper) + 1 (promo)').toBe(6);

    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=contributions`);
    const points = page.getByTestId(`contributions-row-${promoterRow!.org_user_pk}`).locator('td').nth(2);
    await expect(points).toHaveText('6');

    const badge = page.getByTestId('point-value-badge-promo_message');
    await expect(badge).toHaveText('Default');
    await page.getByTestId('point-value-promo_message').fill('3');
    await page.getByTestId('point-value-save-promo_message').click();
    await expect(page.getByTestId('rescore-dialog')).toBeVisible();
    await page.getByTestId('rescore-apply-past').click();
    await page.getByTestId('rescore-confirm').click();
    await expect(page.getByTestId('rescore-dialog')).toBeHidden();

    await expect(badge).toHaveText('Changed');
    await expect(points).toHaveText('8');

    await page.getByTestId('point-value-reset-promo_message').click();
    await expect(page.getByTestId('rescore-dialog')).toBeVisible();
    await page.getByTestId('rescore-apply-past').click();
    await page.getByTestId('rescore-confirm').click();
    await expect(page.getByTestId('rescore-dialog')).toBeHidden();

    await expect(badge).toHaveText('Default');
    await expect(page.getByTestId('point-value-reset-promo_message')).toHaveCount(0);
    await expect(points).toHaveText('6');
  });
});
