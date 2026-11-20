import {
  expect,
  loginOrgFeatures,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

test.describe('Org features: conduct @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test('public viewer sees the ranking @cicd', async ({ page, context }) => {
    await loginOrgFeatures(context, 'member');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=conduct`,
    );

    await expect(page.getByTestId('conduct-tab')).toBeVisible();
    expect(data.conduct.ranked_org_user_pks.length).toBeGreaterThan(0);
    for (const pk of data.conduct.ranked_org_user_pks) {
      await expect(page.getByTestId(`conduct-row-${pk}`)).toBeVisible();
    }
  });

  test('a non-member sees the members-only note @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'outsider');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=conduct`,
    );

    await expect(page.getByTestId('conduct-members-only')).toBeVisible();
    await expect(
      page.getByTestId(`conduct-row-${data.conduct.ranked_org_user_pks[0]}`),
    ).toHaveCount(0);
  });

  test('staff sees member history @cicd', async ({ page, context }) => {
    await loginOrgFeatures(context, 'staff');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=conduct`,
    );

    const pk = data.conduct.completed_event_member_org_user_pk;
    await page.getByTestId(`conduct-row-${pk}`).click();
    await expect(page.getByTestId('conduct-history')).toBeVisible();
    await expect(
      page.getByTestId(`conduct-history-row-${data.events.completed.pk}`),
    ).toBeVisible();
  });

  test('staff marks a no-show with a reason @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'staff');
    const orgPk = data.orgs.features.pk;
    const eventPk = data.events.completed.pk;
    const pk = data.conduct.completed_event_member_org_user_pk;

    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=conduct`);
    const rate = page.getByTestId(`conduct-row-${pk}-rate`);
    await expect(rate).toBeVisible();
    const before = (await rate.textContent()) ?? '';

    await visitAndWaitForHydration(page, `/events/${eventPk}`);
    await expect(page.getByTestId('attendance-panel')).toBeVisible();
    await page.getByTestId(`attendance-outcome-${pk}`).click();
    await page.getByTestId('attendance-outcome-option-no_show').click();
    await page.getByTestId('attendance-save').click();
    await page.getByTestId('conduct-reason-input').fill('Did not show');
    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/conduct/events/${eventPk}/attendance/`) &&
          r.request().method() === 'PUT' &&
          r.ok(),
      ),
      page.getByTestId('conduct-reason-confirm').click(),
    ]);

    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=conduct`);
    await page.getByTestId(`conduct-row-${pk}`).click();
    await expect(
      page
        .getByTestId(`conduct-history-row-${eventPk}`)
        .getByTestId('conduct-outcome-no_show'),
    ).toBeVisible();
    await expect(page.getByTestId(`conduct-row-${pk}-rate`)).not.toHaveText(
      before,
    );
  });

  test('forecast card shows on the conduct event @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'staff');
    await visitAndWaitForHydration(
      page,
      `/events/${data.events.conduct_upcoming.pk}`,
    );

    await expect(page.getByTestId('conduct-forecast')).toContainText(
      '6 signed up',
    );
  });

  test('admin edits settings @cicd', async ({ page, context }) => {
    await loginOrgFeatures(context, 'admin');
    const pk = data.orgs.features.pk;
    await visitAndWaitForHydration(page, `/organizations/${pk}?tab=settings`);

    const halfLife = page.getByTestId('conduct-setting-half_life_days');
    await expect(halfLife).toBeVisible();
    await halfLife.fill('120');
    const saved = page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes(`/organizations/${pk}/conduct/settings/`),
    );
    await page.getByTestId('conduct-settings-save').click();
    expect((await saved).status()).toBe(200);

    await page.reload();
    await expect(
      page.getByTestId('conduct-setting-half_life_days'),
    ).toHaveValue('120');
  });
});
