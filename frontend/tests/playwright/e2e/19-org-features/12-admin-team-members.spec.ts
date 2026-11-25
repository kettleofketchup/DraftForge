/**
 * Adding a non-member to the admin team or as an event helper makes them an
 * org member; the org Users tab shows them without a reload.
 */

import type { Page } from '@playwright/test';

import {
  expect,
  loginOrgFeatures,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

async function pickUser(
  page: Page,
  opener: string,
  username: string,
): Promise<void> {
  await page.getByTestId(opener).click();
  const modal = page.getByTestId('add-user-modal');
  await expect(modal).toBeVisible();
  await modal.getByTestId('add-user-search').fill(username);
  await modal.getByTestId(`add-user-btn-${username}`).click();
}

async function usersTabCount(page: Page): Promise<number> {
  const tab = page.getByTestId('org-tab-users');
  await expect(tab).toHaveText(/Users \(\d+\)/);
  return Number((await tab.innerText()).match(/\((\d+)\)/)![1]);
}

// The Users tab virtualizes its grid, so filter to the card before asserting.
async function expectMemberCard(page: Page, username: string): Promise<void> {
  await page.getByPlaceholder('Search members...').fill(username);
  await expect(page.getByTestId(`usercard-${username}`)).toBeVisible();
}

async function markDocument(page: Page): Promise<() => Promise<boolean>> {
  await page.evaluate(() => {
    (window as Window & { __sameDocument?: boolean }).__sameDocument = true;
  });
  return () =>
    page.evaluate(
      () =>
        (window as Window & { __sameDocument?: boolean }).__sameDocument ===
        true,
    );
}

test.describe('Org features: new members from staff adds @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request, context }) => {
    data = await resetOrgFeatures(request);
    await loginOrgFeatures(context, 'admin');
  });

  test.afterEach(async ({ request }) => {
    await resetOrgFeatures(request);
  });

  test('adding staff in Admin Team updates the Users tab @cicd', async ({
    page,
  }) => {
    const orgPk = data.orgs.features.pk;
    const outsider = data.users.outsider;

    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=users`);
    await expect(page.getByTestId('org-tab-users')).toHaveAttribute(
      'data-state',
      'active',
    );
    const before = await usersTabCount(page);
    await page.getByPlaceholder('Search members...').fill(outsider.username);
    await expect(page.getByText('No matching users found')).toBeVisible();
    const sameDocument = await markDocument(page);

    await page.getByTestId('org-settings-button').click();
    await expect(page.getByTestId('org-settings-modal')).toBeVisible();
    await page.getByTestId('org-settings-tab-admins').click();

    const added = page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes(`/organizations/${orgPk}/staff/`),
    );
    await pickUser(page, 'add-staff-btn', outsider.username);
    expect((await added).ok()).toBe(true);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('add-user-modal')).toBeHidden();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('org-settings-modal')).toBeHidden();

    await expect(page.getByTestId('org-tab-users')).toHaveText(
      `Users (${before + 1})`,
    );
    await expectMemberCard(page, outsider.username);
    expect(await sameDocument()).toBe(true);
  });

  test('a new event helper shows on the org Users tab @cicd', async ({
    page,
  }) => {
    const orgPk = data.orgs.features.pk;
    const eventPk = data.events.upcoming.pk;
    const outsider = data.users.outsider;

    await visitAndWaitForHydration(page, `/events/${eventPk}`);
    await pickUser(page, 'event-helper-add-btn', outsider.username);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('add-user-modal')).toBeHidden();
    await expect(
      page.getByTestId(`event-helper-remove-${outsider.pk}`),
    ).toBeVisible();

    const saved = page.waitForResponse(
      (r) =>
        r.request().method() === 'PUT' &&
        r.url().includes(`/events/${eventPk}/staff/`),
    );
    await page.getByTestId('event-staff-save-btn').click();
    expect((await saved).status()).toBe(200);

    const sameDocument = await markDocument(page);
    await page
      .getByRole('link', { name: data.orgs.features.name, exact: true })
      .first()
      .click();
    await expect(page).toHaveURL(new RegExp(`/organizations/${orgPk}`));
    await page.getByTestId('org-tab-users').click();
    await expectMemberCard(page, outsider.username);
    expect(await sameDocument()).toBe(true);
  });
});
