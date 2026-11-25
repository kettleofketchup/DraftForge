/**
 * Events E2E: the series page reflects an event action without a reload.
 *
 * Cancelling an event and returning through the "Event Series" header button
 * must move the card to Past with the Cancelled badge.
 */

import {
  expect,
  getEventsTestData,
  loginEventAdmin,
  postWithCsrf,
  resetEventsData,
  test,
  triggerEventGeneration,
  visitAndWaitForHydration,
  type EventInfo,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

const SERIES_NAME = 'E2E Series Refresh';

let eventInfo: EventInfo;

test.describe('Events - Series page stays fresh (@cicd)', () => {
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

  test('a cancelled event moves to Past on return to the series page', async ({
    context,
    page,
  }) => {
    const createResp = await postWithCsrf(
      context,
      `${API_URL}/events/repeaters/`,
      {
        organization: eventInfo.orgPk,
        name: SERIES_NAME,
        description: 'Series under test',
        frequency: 'daily',
        day_of_week: 0,
        time_of_day: '20:00:00',
        starts_at: todayISO(),
        generate_days_ahead: 3,
        is_active: true,
        tournament_name: 'E2E Series Refresh Tournament',
        tournament_league: eventInfo.leaguePk,
        tournament_type: 'single_elimination',
        game_type: 1,
        draft_type: 'shuffle',
        people_per_team: 5,
        number_of_teams: null,
        timezone: 'UTC',
        auto_approve: true,
        max_players: null,
      },
    );
    expect(createResp.ok()).toBeTruthy();
    const series: { id: number } = await createResp.json();
    await triggerEventGeneration(context);

    await visitAndWaitForHydration(page, `/event-series/${series.id}`);
    await expect(page.getByRole('heading', { name: /^Past/ })).toHaveCount(0);

    const cards = page.locator('a[href^="/events/"]');
    await expect(cards.first()).toBeVisible();
    const href = await cards.first().getAttribute('href');
    expect(href).toBeTruthy();
    const eventId = href!.split('/').pop();

    await cards.first().click();
    await expect(page).toHaveURL(new RegExp(`/events/${eventId}$`));

    const [cancelResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/events/${eventId}/cancel/`) &&
          r.request().method() === 'POST',
      ),
      page.getByTestId('event-cancel-btn').click(),
    ]);
    expect(cancelResp.ok()).toBeTruthy();

    await page.getByRole('button', { name: SERIES_NAME, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/event-series/${series.id}$`));

    await expect(page.getByRole('heading', { name: /^Past/ })).toBeVisible();
    const cancelledCard = page.locator(`a[href="/events/${eventId}"]`);
    await expect(cancelledCard).toContainText('Cancelled');
  });
});
