import {
  expect,
  expectNoSessionToast,
  loginOrgFeatures,
  orgFeaturesApi,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

test.describe('Org features: locked org @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test('locked admin sees no locked feature tabs or promoter section @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'locked_admin');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.locked.pk}`,
    );

    await expect(page.getByTestId('org-tab-users')).toBeVisible();
    await expect(page.getByTestId('org-tab-claims')).toBeVisible();
    await expect(page.getByTestId('org-tab-contributions')).toHaveCount(0);
    await expect(page.getByTestId('org-tab-promotion')).toHaveCount(0);

    await page.getByTestId('edit-organization-button').click();
    await expect(page.getByTestId('edit-organization-modal')).toBeVisible();
    const addAdmin = page.getByTestId('add-admin-btn');
    await addAdmin.scrollIntoViewIfNeeded();
    await expect(addAdmin).toBeVisible();
    await expect(page.getByTestId('promoters-section')).toHaveCount(0);
    await expectNoSessionToast(page);
  });

  test('a promotion deep link bounces to leagues without a session toast @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'locked_admin');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.locked.pk}?tab=promotion`,
    );

    await expect(page.getByTestId('org-tab-users')).toBeVisible();
    await expect(page).not.toHaveURL(/tab=promotion/);
    await expect(page.getByTestId('org-tab-leagues')).toHaveAttribute(
      'data-state',
      'active',
    );
    await expect(page.getByTestId('promotion-tab')).toHaveCount(0);
    await expectNoSessionToast(page);
  });

  test('locked admin sees no Promote button on the locked org event @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'locked_admin');
    const start = new Date(Date.now() + 3 * 24 * 3600 * 1000);
    const event = await orgFeaturesApi<{ id: number }>(
      context,
      'POST',
      '/events/',
      {
        organization: data.orgs.locked.pk,
        name: 'Locked Upcoming Event',
        description: 'Upcoming event on the locked org.',
        scheduled_at: start.toISOString(),
      },
    );

    await visitAndWaitForHydration(page, `/events/${event.id}`);
    // The staff editor needs the settled per-viewer org payload, like the Promote button.
    await expect(page.getByTestId('event-host-edit-btn')).toBeVisible();
    await expect(page.getByTestId('event-promote-btn')).toHaveCount(0);
  });

  test('a plain member sees no Promote button on the unlocked org event @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'member');
    await visitAndWaitForHydration(page, `/events/${data.events.upcoming.pk}`);
    await expect(page.getByTestId('event-title')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('event-promote-btn')).toHaveCount(0);

    await loginOrgFeatures(context, 'promoter');
    await visitAndWaitForHydration(page, `/events/${data.events.upcoming.pk}`);
    await expect(page.getByTestId('event-promote-btn')).toBeVisible();
  });
});
