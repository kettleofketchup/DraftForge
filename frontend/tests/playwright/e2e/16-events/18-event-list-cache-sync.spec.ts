/**
 * Event state changes and signups made on the event page show up on the
 * cached /events list when the user goes back, without a reload.
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
import { API_URL } from '../../fixtures/base-url';
import { getCsrfToken } from '../../fixtures/events';
import {
  closeAddUserModal,
  searchAndAddUser,
  waitForAddUserModal,
} from '../../helpers/add-user';

let eventInfo: EventInfo;
const created: number[] = [];

async function createEvent(
  context: BrowserContext,
  name: string,
  openSignups: boolean,
): Promise<{ id: number }> {
  const resp = await postWithCsrf(
    context,
    `${API_URL}/events/${openSignups ? '?open_signups=true' : ''}`,
    {
      organization: eventInfo.orgPk,
      name,
      scheduled_at: new Date(Date.now() + 86_400_000).toISOString(),
      tournament_name: `${name} Tournament`,
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      game_type: 1,
      draft_type: 'shuffle',
      people_per_team: 5,
      number_of_teams: 2,
      max_players: 10,
      auto_approve: true,
      timezone: 'UTC',
    },
  );
  if (!resp.ok()) {
    throw new Error(
      `Create event failed: ${resp.status()} ${await resp.text()}`,
    );
  }
  const event: { id: number } = await resp.json();
  created.push(event.id);
  return event;
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

async function backToEventsList(page: Page): Promise<void> {
  for (let i = 0; i < 5 && new URL(page.url()).pathname !== '/events'; i++) {
    await page.goBack();
  }
  await expect(page).toHaveURL(/\/events\?/);
}

test.describe('Events - list stays in sync with the event page (@cicd)', () => {
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
    const csrf = await getCsrfToken(context);
    while (created.length) {
      const id = created.pop();
      await context.request.delete(`${API_URL}/events/${id}/`, {
        headers: { 'X-CSRFToken': csrf },
      });
    }
    await resetEventsData(context);
  });

  test('opening signups updates the event card badge', async ({
    context,
    page,
  }) => {
    const event = await createEvent(
      context,
      `E2E List Open ${Date.now()}`,
      false,
    );

    await visitAndWaitForHydration(
      page,
      `/events?organization=${eventInfo.orgPk}`,
    );
    await markDocument(page);
    const card = page.getByTestId(`event-card-${event.id}`);
    await expect(card).toContainText('Upcoming');

    await card.click();
    await expect(page).toHaveURL(new RegExp(`/events/${event.id}`));
    await page.getByTestId('event-open-signups-btn').click();
    await expect(page.getByTestId('event-start-rollcall-btn')).toBeVisible();

    await backToEventsList(page);
    await expect(page.getByTestId(`event-card-${event.id}`)).toContainText(
      'Signups Open',
    );
    await expectSameDocument(page);
  });

  test('a staff-added signup updates the event card count', async ({
    context,
    page,
  }) => {
    const event = await createEvent(
      context,
      `E2E List Add ${Date.now()}`,
      true,
    );

    await visitAndWaitForHydration(
      page,
      `/events?organization=${eventInfo.orgPk}`,
    );
    await markDocument(page);
    const card = page.getByTestId(`event-card-${event.id}`);
    await expect(card.getByTestId('event-card-signup-count')).toHaveText(
      /^0 signups \//,
    );

    await card.click();
    await expect(page).toHaveURL(new RegExp(`/events/${event.id}`));
    await page.getByTestId('event-tab-signups').click();
    await page.getByTestId('admin-add-signup-btn').click();
    await waitForAddUserModal(page);
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/events/${event.id}/admin-signup/`) &&
          r.request().method() === 'POST',
      ),
      searchAndAddUser(page, 'event_player_1'),
    ]);
    expect(response.status()).toBe(201);
    await closeAddUserModal(page);

    await backToEventsList(page);
    await expect(
      page
        .getByTestId(`event-card-${event.id}`)
        .getByTestId('event-card-signup-count'),
    ).toHaveText(/^1 signup \//);
    await expectSameDocument(page);
  });
});
