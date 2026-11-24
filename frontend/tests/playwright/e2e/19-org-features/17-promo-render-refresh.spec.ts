import type { Locator, Page } from '@playwright/test';

import {
  expect,
  loginOrgFeatures,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Pick the first candidate and the template, returning the DM textarea. */
async function compose(
  page: Page,
  eventPk: number,
  templatePk: number,
): Promise<Locator> {
  await expect(page.getByTestId(`promo-event-${eventPk}`)).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  const firstSelect = page.locator('[data-testid^="promo-select-"]').first();
  await expect(firstSelect).toBeVisible();
  await firstSelect.click();
  await page.getByTestId('promo-template-select').click();
  await page.getByTestId(`promo-template-option-${templatePk}`).click();
  return page.getByTestId('promo-message-text');
}

test.describe('Org features: promo DMs follow org and event edits @cicd', () => {
  let data: OrgFeaturesTestData;
  let templatePk: number;

  test.beforeEach(async ({ request, context }) => {
    data = await resetOrgFeatures(request);
    const template = data.templates.find(
      (t) => t.org_pk === data.orgs.features.pk && t.name === 'First invite',
    );
    expect(template, 'seeded "First invite" template').toBeDefined();
    templatePk = template!.pk;
    await loginOrgFeatures(context, 'admin');
  });

  test.afterEach(async ({ request }) => {
    await resetOrgFeatures(request);
  });

  test('renaming the org re-renders the open DM without a reload', async ({
    page,
  }) => {
    test.setTimeout(60_000);
    const org = data.orgs.features;
    const eventPk = data.events.upcoming.pk;
    const renamed = `${org.name} Renamed`;

    await visitAndWaitForHydration(
      page,
      `/organizations/${org.pk}?tab=promotion&event=${eventPk}`,
    );
    const message = await compose(page, eventPk, templatePk);
    await expect(message).toHaveValue(
      new RegExp(`from ${escapeRegExp(org.name)} here\\.`),
    );

    await page.getByTestId('org-settings-button').click();
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    await page.getByTestId('org-settings-tab-general').click();
    await page.getByTestId('org-name-input').fill(renamed);
    const saved = page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().endsWith(`/organizations/${org.pk}/`),
    );
    await page.getByTestId('org-settings-save').click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByTestId('org-settings-save-bar')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('org-settings-modal')).toHaveCount(0);

    if (!(await message.isVisible())) {
      await compose(page, eventPk, templatePk);
    }
    await expect(message).toHaveValue(
      new RegExp(`from ${escapeRegExp(renamed)} here\\.`),
    );
  });

  test('renaming the event re-renders its DM without a reload', async ({
    page,
  }) => {
    test.setTimeout(60_000);
    const orgPk = data.orgs.features.pk;
    const event = data.events.upcoming;
    const renamed = `${event.name} Renamed`;

    await visitAndWaitForHydration(page, `/events/${event.pk}`);
    await page.getByTestId('event-promote-btn').click();
    await expect(page).toHaveURL(
      new RegExp(`/organizations/${orgPk}\\?.*tab=promotion`),
    );
    const message = await compose(page, event.pk, templatePk);
    await expect(message).toHaveValue(
      new RegExp(`\\*\\*${escapeRegExp(event.name)}\\*\\*`),
    );

    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`/events/${event.pk}$`));
    await page.getByTestId('event-edit-btn').click();
    await page.getByTestId('edit-event-name-input').fill(renamed);
    const saved = page.waitForResponse(
      (r) =>
        r.request().method() === 'PATCH' &&
        r.url().includes(`/events/${event.pk}/`),
    );
    await page
      .getByTestId('edit-event-modal')
      .getByTestId('form-dialog-submit')
      .click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByTestId('edit-event-modal')).toBeHidden();

    await page.goForward();
    await expect(page).toHaveURL(new RegExp(`/organizations/${orgPk}`));
    await compose(page, event.pk, templatePk);
    await expect(message).toHaveValue(
      new RegExp(`\\*\\*${escapeRegExp(renamed)}\\*\\*`),
    );
  });
});
