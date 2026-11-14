import {
  expect,
  loginOrgFeatures,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

test.describe('Org features: smoke @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test('admin sees the contributions tab on the unlocked org @cicd', async ({ page, context }) => {
    await loginOrgFeatures(context, 'admin');
    await visitAndWaitForHydration(page, `/organizations/${data.orgs.features.pk}`);
    await expect(page.getByTestId('org-tab-contributions')).toBeVisible();
  });
});
