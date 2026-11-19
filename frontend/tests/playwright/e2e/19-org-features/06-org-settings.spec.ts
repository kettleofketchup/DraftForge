import type { Page } from '@playwright/test';

import {
  expect,
  loginOrgFeatures,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

async function expectSettingsRedirected(page: Page): Promise<void> {
  await expect(page.getByTestId('org-tab-leagues')).toHaveAttribute(
    'data-state',
    'active',
  );
  await expect(page).not.toHaveURL(/tab=settings/);
}

test.describe('Org features: settings tab @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request, context }) => {
    data = await resetOrgFeatures(request);
    await loginOrgFeatures(context, 'admin');
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

    await expectSettingsRedirected(page);
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
      await expect(page.getByTestId('org-tab-settings')).toHaveCount(1);

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
        `/organizations/${data.orgs.features.pk}?tab=settings`,
      );
      await expectSettingsRedirected(page);

      await page.getByTestId('page-nav-trigger').click();
      await expect(page.getByTestId('page-nav-leagues')).toBeVisible();
      await expect(page.getByTestId('page-nav-settings')).toHaveCount(0);
    });
  });
});
