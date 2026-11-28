/**
 * Series edits, subscriptions and deletes show up on the other series views
 * without a reload. Each test creates a throwaway series; resetEventsData
 * removes it afterwards.
 */

import type { BrowserContext, Page } from '@playwright/test';
import {
  expect,
  getEventsTestData,
  loginEventAdmin,
  postWithCsrf,
  resetEventsData,
  test,
  visitAndWaitForHydration,
  type EventInfo,
} from '../../fixtures';
import { loginAsUser } from '../../fixtures/auth';
import { API_URL } from '../../fixtures/base-url';

let eventInfo: EventInfo;

async function createSeries(
  context: BrowserContext,
  name: string,
): Promise<{ id: number; name: string }> {
  const resp = await postWithCsrf(context, `${API_URL}/events/repeaters/`, {
    organization: eventInfo.orgPk,
    name,
    frequency: 'weekly',
    day_of_week: 2,
    time_of_day: '20:00:00',
    starts_at: new Date().toISOString().slice(0, 10),
    generate_days_ahead: 3,
    is_active: true,
    tournament_name: `${name} Tournament`,
    tournament_league: eventInfo.leaguePk,
    tournament_type: 'single_elimination',
    game_type: 1,
    draft_type: 'shuffle',
    people_per_team: 5,
    number_of_teams: null,
    timezone: 'UTC',
    auto_approve: true,
    max_players: null,
    discord_notify_new_events: true,
  });
  if (!resp.ok()) {
    throw new Error(
      `Create series failed: ${resp.status()} ${await resp.text()}`,
    );
  }
  return resp.json();
}

async function markDocument(page: Page): Promise<void> {
  await page.evaluate(() => {
    (window as unknown as { __noReload?: boolean }).__noReload = true;
  });
}

async function expectSameDocument(page: Page): Promise<void> {
  expect(
    await page.evaluate(
      () => (window as unknown as { __noReload?: boolean }).__noReload,
    ),
  ).toBe(true);
}

test.describe('Events - series views stay in sync (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test.afterEach(async ({ context }) => {
    await resetEventsData(context);
  });

  test('retained occurrence refreshes its state and series link without a reload', async ({
    context,
    page,
  }) => {
    const response = await context.request.post(
      `${API_URL}/tests/signup-records/reset/`,
    );
    expect(response.status()).toBe(200);
    const data = (await response.json()) as {
      admin_pk: number;
      registered_event_pk: number;
      repeater_pk: number;
    };
    await loginAsUser(context, data.admin_pk);
    await visitAndWaitForHydration(page, `/events/${data.registered_event_pk}`);
    await markDocument(page);
    await page.getByTestId('event-series-link').click();
    await page.getByTestId('delete-series-btn').click();
    await page
      .getByTestId('delete-series-confirm-input')
      .fill('Records Weekly Series');
    await page.getByTestId('delete-series-confirm').click();
    await expect(page).toHaveURL(/\/events$/);
    await page.goBack();
    await page.goBack();
    await expect(page).toHaveURL(
      new RegExp(`/events/${data.registered_event_pk}`),
    );
    await expect(page.getByTestId('event-cancel-btn')).toHaveCount(0);
    await expect(page.getByTestId('event-series-link')).toHaveCount(0);
    await expectSameDocument(page);
  });

  test('renaming a series updates the cached /events Series tab', async ({
    context,
    page,
  }) => {
    const series = await createSeries(context, `E2E Sync Rename ${Date.now()}`);
    const renamed = `${series.name} Renamed`;

    await visitAndWaitForHydration(
      page,
      `/events?organization=${eventInfo.orgPk}`,
    );
    await markDocument(page);
    await page.getByTestId('events-tab-series').click();
    const card = page.getByTestId(`repeater-card-${series.id}`);
    await expect(card).toContainText(series.name);

    await card.click();
    await expect(page).toHaveURL(new RegExp(`/event-series/${series.id}$`));
    await page.getByTestId('edit-series-btn').click();
    const modal = page.getByTestId('edit-series-modal');
    await modal.getByTestId('edit-series-name-input').fill(renamed);
    await modal.getByTestId('form-dialog-submit').click();
    await expect(modal).toBeHidden();
    await expect(page.getByRole('heading', { name: renamed })).toBeVisible();

    await page.goBack();
    await page.getByTestId('events-tab-series').click();
    await expect(page.getByTestId(`repeater-card-${series.id}`)).toContainText(
      renamed,
    );
    await expectSameDocument(page);
  });

  test('subscribing on the series page updates the org series list', async ({
    context,
    page,
  }) => {
    const series = await createSeries(context, `E2E Sync Sub ${Date.now()}`);

    await visitAndWaitForHydration(
      page,
      `/organizations/${eventInfo.orgPk}?tab=events`,
    );
    await markDocument(page);
    const strip = page.getByTestId(`repeater-strip-${series.id}`);
    await expect(
      strip.getByRole('button', { name: 'Subscribe' }),
    ).toBeVisible();

    await strip.getByText(series.name).click();
    await expect(page).toHaveURL(new RegExp(`/event-series/${series.id}$`));
    await page.getByTestId('subscribe-series-btn').click();
    await expect(page.getByTestId('unsubscribe-series-btn')).toBeVisible();

    await page.goBack();
    await expect(
      page
        .getByTestId(`repeater-strip-${series.id}`)
        .getByRole('button', { name: 'Unsubscribe' }),
    ).toBeVisible();
    await expectSameDocument(page);
  });

  test('deleting a series drops it and its upcoming events from /events', async ({
    context,
    page,
  }) => {
    const series = await createSeries(context, `E2E Sync Delete ${Date.now()}`);
    const oneOffName = `${series.name} One-Off`;
    const scheduled = new Date(Date.now() + 86_400_000);
    scheduled.setUTCHours(3, 15, 0, 0);
    const oneOffResp = await postWithCsrf(
      context,
      `${API_URL}/events/repeaters/${series.id}/create-event/`,
      { name: oneOffName, scheduled_at: scheduled.toISOString() },
    );
    expect(oneOffResp.status()).toBe(201);
    const oneOff: { id: number } = await oneOffResp.json();

    await visitAndWaitForHydration(page, '/events');
    await markDocument(page);
    await expect(page.getByTestId(`event-card-${oneOff.id}`)).toBeVisible();
    await page.getByTestId('events-tab-series').click();
    await page.getByTestId(`repeater-card-${series.id}`).click();
    await expect(page).toHaveURL(new RegExp(`/event-series/${series.id}$`));

    await page.getByTestId('delete-series-btn').click();
    await page.getByTestId('delete-series-confirm-input').fill(series.name);
    await page.getByTestId('delete-series-confirm').click();

    await expect(page).toHaveURL(/\/events$/);
    await expect(page.getByTestId(`event-card-${oneOff.id}`)).toHaveCount(0);
    await page.getByTestId('events-tab-series').click();
    await expect(page.getByTestId(`repeater-card-${series.id}`)).toHaveCount(0);
    await expectSameDocument(page);
  });
});
