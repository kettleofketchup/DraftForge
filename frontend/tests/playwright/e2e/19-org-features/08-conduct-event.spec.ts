import type { Page } from '@playwright/test';
import {
  expect,
  loginOrgFeatures,
  orgFeaturesApi,
  resetOrgFeatures,
  test,
  visitAndWaitForHydration,
  type OrgFeaturesTestData,
} from '../../fixtures';

const ATTENDANCE_ROW = /^attendance-row-/;

async function saveWithReason(
  page: Page,
  eventPk: number,
  reason: string,
  tooShort?: string,
): Promise<void> {
  await page.getByTestId('attendance-save').click();
  await expect(page.getByTestId('conduct-reason-dialog')).toBeVisible();
  const input = page.getByTestId('conduct-reason-input');
  if (tooShort) {
    await input.fill(tooShort);
    await expect(page.getByTestId('conduct-reason-confirm')).toBeDisabled();
  }
  await input.fill(reason);
  const saved = page.waitForResponse(
    (r) =>
      r.request().method() === 'PUT' &&
      r.url().includes(`/conduct/events/${eventPk}/attendance/`),
  );
  await page.getByTestId('conduct-reason-confirm').click();
  expect((await saved).status()).toBe(200);
  await expect(page.getByTestId('conduct-reason-dialog')).toHaveCount(0);
}

test.describe('Org features: event conduct @cicd', () => {
  let data: OrgFeaturesTestData;

  test.beforeEach(async ({ request }) => {
    data = await resetOrgFeatures(request);
  });

  test('staff sees the turnout forecast and show-rate badges @cicd', async ({
    page,
    context,
  }) => {
    const eventPk = data.events.conduct_upcoming.pk;
    await loginOrgFeatures(context, 'staff');
    await visitAndWaitForHydration(page, `/events/${eventPk}`);

    await expect(page.getByTestId('conduct-forecast-summary')).toContainText(
      '6 signed up',
    );
    await page.getByTestId('event-tab-signups').click();
    await expect(page.getByTestId('conduct-badge')).toHaveCount(6);

    await loginOrgFeatures(context, 'member');
    await visitAndWaitForHydration(page, `/events/${eventPk}`);
    await expect(page.getByTestId('event-tab-signups')).toBeVisible();
    await expect(page.getByTestId('conduct-forecast')).toHaveCount(0);
    await page.getByTestId('event-tab-signups').click();
    await expect(page.getByTestId('conduct-badge')).toHaveCount(0);
  });

  test('roll call shows default attendance and badges @cicd', async ({
    page,
    context,
  }) => {
    const eventPk = data.events.conduct_upcoming.pk;
    await loginOrgFeatures(context, 'staff');
    await orgFeaturesApi(
      context,
      'POST',
      `/events/${eventPk}/start_roll_call/`,
    );

    await visitAndWaitForHydration(page, `/events/${eventPk}`);
    const rows = page
      .getByTestId('attendance-table')
      .getByTestId(ATTENDANCE_ROW);
    await expect(rows).toHaveCount(6);
    for (const row of await rows.all()) {
      await expect(row).toContainText('Attended (default)');
    }

    await visitAndWaitForHydration(page, `/rollcall/${eventPk}`);
    await expect(page.getByTestId('conduct-badge')).toHaveCount(6);
  });

  test('staff marks a no-show with a reason and the ranking reflects it @cicd', async ({
    page,
    context,
  }) => {
    const orgPk = data.orgs.features.pk;
    const eventPk = data.events.completed.pk;
    const pk = data.conduct.completed_event_member_org_user_pk;
    await loginOrgFeatures(context, 'staff');

    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=conduct`);
    const value = page.getByTestId(`conduct-row-${pk}-value`);
    await expect(value).toBeVisible();
    const before = (await value.textContent())?.trim();
    expect(before).toBeTruthy();
    expect(before).not.toBe('New');

    await visitAndWaitForHydration(page, `/events/${eventPk}`);
    await page.getByTestId(`attendance-select-${pk}`).check();
    await page.getByTestId('attendance-bulk-no-show').click();

    await saveWithReason(page, eventPk, 'Did not show', 'ab');
    await expect(page.getByTestId(`attendance-outcome-${pk}`)).toContainText(
      'No-show',
    );

    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=conduct`);
    await expect(page.getByTestId(`conduct-row-${pk}-value`)).not.toHaveText(
      before!,
    );
    await page.getByTestId(`conduct-row-${pk}`).click();
    const historyRow = page
      .getByTestId('conduct-history')
      .getByTestId(`conduct-history-row-${eventPk}`);
    await expect(historyRow).toBeVisible();
    await expect(
      historyRow.getByTestId('conduct-outcome-no_show'),
    ).toBeVisible();
  });

  test('staff adds a walk-in @cicd', async ({ page, context }) => {
    const orgPk = data.orgs.features.pk;
    const eventPk = data.events.completed.pk;
    const walkInPk = data.conduct.new_member_org_user_pk;
    await loginOrgFeatures(context, 'staff');
    const { member } = await orgFeaturesApi<{
      member: { user_pk: number; username: string };
    }>(context, 'GET', `/organizations/${orgPk}/conduct/members/${walkInPk}/`);

    await visitAndWaitForHydration(page, `/events/${eventPk}`);
    await expect(page.getByTestId(`attendance-row-${walkInPk}`)).toHaveCount(0);
    await page.getByTestId('attendance-add-walkin').click();
    await page.getByTestId('attendance-walkin-search').fill(member.username);
    await page
      .getByTestId(`attendance-walkin-option-${member.user_pk}`)
      .click();
    await saveWithReason(page, eventPk, 'Played as a sub');

    const row = page.getByTestId(`attendance-row-${walkInPk}`);
    await expect(row).toBeVisible();
    await expect(
      page.getByTestId(`attendance-source-${walkInPk}`),
    ).toContainText('Walk-in');

    await visitAndWaitForHydration(page, `/organizations/${orgPk}?tab=conduct`);
    await page.getByTestId(`conduct-row-${walkInPk}`).click();
    await expect(
      page
        .getByTestId('conduct-history')
        .getByTestId(`conduct-history-row-${eventPk}`),
    ).toBeVisible();
  });
});
