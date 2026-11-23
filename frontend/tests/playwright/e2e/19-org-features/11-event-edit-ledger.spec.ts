import {
  expect,
  loginOrgFeatures,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

test.describe('Org features: event edits reach the contributions ledger @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test.afterEach(async ({ request }) => {
    await resetOrgFeatures(request);
  });

  test('renaming a completed event updates the ledger without a reload', async ({
    page,
    context,
  }) => {
    test.setTimeout(60_000);
    const orgPk = data.orgs.features.pk;
    const completed = data.events.completed;
    const renamed = `${completed.name} Renamed`;

    await loginOrgFeatures(context, 'admin');
    await visitAndWaitForHydration(
      page,
      `/organizations/${orgPk}?tab=contributions`,
    );
    const ledger = page.getByTestId('contributions-ledger');
    const oldLinks = ledger.getByRole('link', {
      name: completed.name,
      exact: true,
    });
    await expect(oldLinks.first()).toBeVisible();

    await oldLinks.first().click();
    await expect(page).toHaveURL(new RegExp(`/events/${completed.pk}$`));
    await page.getByTestId('event-edit-btn').click();
    await page.getByTestId('edit-event-name-input').fill(renamed);
    const saved = page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes(`/events/${completed.pk}/`),
    );
    await page
      .getByTestId('edit-event-modal')
      .getByTestId('form-dialog-submit')
      .click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByTestId('edit-event-modal')).toBeHidden();

    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`/organizations/${orgPk}`));
    await expect(
      ledger.getByRole('link', { name: renamed, exact: true }).first(),
    ).toBeVisible();
    await expect(oldLinks).toHaveCount(0);
  });
});
