import type { BrowserContext } from '@playwright/test';

import {
  expect,
  loginOrgFeatures,
  orgFeaturesApi,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

const ALL_CODES = [
  'gate_outside',
  'gate_out_of_range',
  'over_capacity',
  'special_seat_role_mismatch',
  'maybe_special_seat',
  'maybe_forced_main',
];

async function resetOrgSettings(
  context: BrowserContext,
  orgPk: number,
): Promise<void> {
  await loginOrgFeatures(context, 'admin');
  await orgFeaturesApi(context, 'PATCH', `/organizations/${orgPk}/settings/`, {
    staff_override_policy: 'silent',
    staff_override_warning_codes: ALL_CODES,
  });
}

test.describe('Org features: settings tab @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request, context }) => {
    data = await resetOrgFeatures(request);
    await resetOrgSettings(context, data.orgs.features.pk);
  });

  test.afterEach(async ({ context }) => {
    await resetOrgSettings(context, data.orgs.features.pk);
  });

  test('admin saves and reloads settings @cicd', async ({ page }) => {
    const pk = data.orgs.features.pk;
    await visitAndWaitForHydration(page, `/organizations/${pk}?tab=settings`);

    await expect(page.getByTestId('org-settings-tab')).toBeVisible();
    const policy = page.getByTestId('org-settings-policy-select');
    await expect(policy).toHaveText('Silent');
    await policy.click();
    await page.getByTestId('org-settings-policy-option-confirm').click();
    await expect(policy).toHaveText('Confirm');

    const overCapacity = page.getByTestId('org-settings-code-over_capacity');
    await expect(overCapacity).toBeChecked();
    await overCapacity.uncheck();

    const saved = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'PATCH' &&
        resp.url().includes(`/organizations/${pk}/settings/`),
    );
    await page.getByTestId('org-settings-save').click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByTestId('org-settings-save')).toBeDisabled();

    await page.reload();
    await expect(page.getByTestId('org-settings-tab')).toBeVisible();
    await expect(page.getByTestId('org-settings-policy-select')).toHaveText(
      'Confirm',
    );
    await expect(
      page.getByTestId('org-settings-code-over_capacity'),
    ).not.toBeChecked();
    await expect(
      page.getByTestId('org-settings-code-gate_outside'),
    ).toBeChecked();
  });

  test('staff sees no Settings tab @cicd', async ({ page, context }) => {
    await loginOrgFeatures(context, 'staff');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=settings`,
    );

    await expect(page.getByTestId('org-tab-leagues')).toHaveAttribute(
      'data-state',
      'active',
    );
    await expect(page).not.toHaveURL(/tab=settings/);
    await expect(page.getByTestId('org-tab-settings')).toHaveCount(0);
    await expect(page.getByTestId('org-settings-tab')).toHaveCount(0);
  });

  test.describe('mobile page nav @cicd', () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test('admin sees Settings in page nav @cicd', async ({ page }) => {
      await visitAndWaitForHydration(
        page,
        `/organizations/${data.orgs.features.pk}`,
      );

      await page.getByTestId('page-nav-trigger').click();
      const option = page.getByTestId('page-nav-settings');
      await expect(option).toBeVisible();
      await expect(option).toHaveText('Settings');
    });

    test('staff has no Settings in page nav @cicd', async ({
      page,
      context,
    }) => {
      await loginOrgFeatures(context, 'staff');
      await visitAndWaitForHydration(
        page,
        `/organizations/${data.orgs.features.pk}`,
      );

      await page.getByTestId('page-nav-trigger').click();
      await expect(page.getByTestId('page-nav-leagues')).toBeVisible();
      await expect(page.getByTestId('page-nav-settings')).toHaveCount(0);
    });
  });
});
