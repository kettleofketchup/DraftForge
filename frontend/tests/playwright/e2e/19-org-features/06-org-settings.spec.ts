import type { Page } from '@playwright/test';

import {
  expect,
  loginOrgFeatures,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

async function expectNoSettingsAccess(page: Page): Promise<void> {
  await expect(page.getByTestId('org-tab-leagues')).toHaveAttribute(
    'data-state',
    'active',
  );
  await expect(page).not.toHaveURL(/settings=/);
  await expect(page.getByTestId('org-settings-button')).toHaveCount(0);
  await expect(page.getByTestId('org-settings-modal')).toHaveCount(0);
}

test.describe('Org features: settings modal @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request, context }) => {
    data = await resetOrgFeatures(request);
    await loginOrgFeatures(context, 'admin');
  });

  test('admin saves and reloads settings @cicd', async ({ page }) => {
    const pk = data.orgs.features.pk;
    await visitAndWaitForHydration(
      page,
      `/organizations/${pk}?settings=staff-placement`,
    );

    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    await expect(
      page.getByTestId('org-settings-tab-staff-placement'),
    ).toHaveAttribute('data-state', 'active');
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
    await expect(page.getByTestId('org-settings-save-bar')).toHaveCount(0);
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();

    await page.reload();
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    await page.getByTestId('org-settings-tab-staff-placement').click();
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

  test('admin edits the organization profile on the settings modal @cicd', async ({
    page,
  }) => {
    const pk = data.orgs.features.pk;
    await visitAndWaitForHydration(page, `/organizations/${pk}`);
    // The cog opens the settings modal on the General section.
    await page.getByTestId('org-settings-button').click();
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    await expect(page.getByTestId('org-settings-tab-general')).toHaveAttribute(
      'data-state',
      'active',
    );

    const description = page.getByTestId('org-description-input');
    const text = `Profile edited ${Date.now()}`;
    await description.fill(text);
    const saved = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'PATCH' &&
        resp.url().endsWith(`/organizations/${pk}/`),
    );
    await page.getByTestId('org-settings-save').click();
    expect((await saved).ok()).toBe(true);
    await expect(page.getByTestId('org-settings-save-bar')).toHaveCount(0);

    await page.reload();
    await expect(page.getByTestId('org-description-input')).toHaveValue(text);
  });

  test('org staff sees no settings cog and a settings link is stripped @cicd', async ({
    page,
    context,
  }) => {
    await loginOrgFeatures(context, 'staff');
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?settings=staff-placement`,
    );

    await expectNoSettingsAccess(page);
  });

  test('legacy tab=settings link opens the modal for an admin @cicd', async ({
    page,
  }) => {
    await visitAndWaitForHydration(
      page,
      `/organizations/${data.orgs.features.pk}?tab=settings&section=staff-placement`,
    );
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    await expect(page).toHaveURL(/settings=staff-placement/);
    await expect(page).not.toHaveURL(/tab=settings/);
  });

  test.describe('mobile @cicd', () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test('admin sees the settings cog @cicd', async ({ page }) => {
      await visitAndWaitForHydration(
        page,
        `/organizations/${data.orgs.features.pk}`,
      );
      await expect(page.getByTestId('org-settings-button')).toBeVisible();
    });

    test('staff has no settings cog @cicd', async ({ page, context }) => {
      await loginOrgFeatures(context, 'staff');
      await visitAndWaitForHydration(
        page,
        `/organizations/${data.orgs.features.pk}?settings=staff-placement`,
      );
      await expectNoSettingsAccess(page);
    });
  });
});
