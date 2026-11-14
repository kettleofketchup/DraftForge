import type { Page } from '@playwright/test';

import {
  expect,
  leaderboardByUser,
  loginOrgFeatures,
  moveEventToRollCall,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

async function pickUser(page: Page, opener: string, username: string): Promise<void> {
  await page.getByTestId(opener).click();
  const modal = page.getByTestId('add-user-modal');
  await expect(modal).toBeVisible();
  await modal.getByTestId('add-user-search').fill(username);
  await modal.getByTestId(`add-user-btn-${username}`).first().click();
}

test.describe('Org features: host and helpers @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test('completing an event awards the host 10 and the helper 5 @cicd', async ({
    page,
    context,
  }) => {
    test.setTimeout(60_000);
    const orgPk = data.orgs.features.pk;
    const eventPk = data.events.upcoming.pk;
    const host = data.users.member;
    const helper = data.users.owner;

    await loginOrgFeatures(context, 'admin');
    const before = await leaderboardByUser(context, orgPk);
    expect(before.has(host.pk)).toBe(false);
    expect(before.has(helper.pk)).toBe(false);

    await visitAndWaitForHydration(page, `/events/${eventPk}`);
    await pickUser(page, 'event-host-edit-btn', host.username);
    await expect(page.getByTestId('add-user-modal')).toBeHidden();

    await pickUser(page, 'event-helper-add-btn', helper.username);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('add-user-modal')).toBeHidden();
    await expect(page.getByTestId(`event-helper-remove-${helper.pk}`)).toBeVisible();

    const saved = page.waitForResponse(
      (r) => r.request().method() === 'PUT' && r.url().includes(`/events/${eventPk}/staff/`),
    );
    await page.getByTestId('event-staff-save-btn').click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByTestId('event-staff-save-btn')).toHaveCount(0);

    await moveEventToRollCall(context, eventPk);
    await page.reload();
    await page.getByTestId('event-complete-btn').click();
    const completed = page.waitForResponse(
      (r) => r.request().method() === 'POST' && r.url().includes(`/events/${eventPk}/complete/`),
    );
    await page.getByTestId('event-complete-dialog-confirm').click();
    expect((await completed).status()).toBe(200);
    await expect(page.getByTestId('event-complete-btn')).toHaveCount(0);

    const after = await leaderboardByUser(context, orgPk);
    expect(after.get(host.pk)?.points).toBe(10);
    expect(after.get(helper.pk)?.points).toBe(5);

    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=contributions`);
    await expect(
      page.getByTestId(`contributions-row-${after.get(host.pk)!.org_user_pk}`).locator('td').nth(2),
    ).toHaveText('10');
    await expect(
      page.getByTestId(`contributions-row-${after.get(helper.pk)!.org_user_pk}`).locator('td').nth(2),
    ).toHaveText('5');
  });
});
