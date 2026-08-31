/**
 * Events E2E — One-off events from a series + series reactivation
 *
 * Covers the two staff actions on /event-series/:repeaterId:
 * - "Add one-off event" → POST /api/events/repeaters/<pk>/create-event/
 * - "Reactivate"        → POST /api/events/repeaters/<pk>/reactivate/
 * - Neither action is offered to a non-staff viewer.
 *
 * Every test creates its own throwaway series. resetEventsData deletes every
 * repeater in Events Test Org except the seeded "Weekly Inhouse", so mutating
 * that one would poison later specs in the events-sequential project.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getEventsTestData,
  resetEventsData,
  loginEventAdmin,
  loginEventPlayer,
  postWithCsrf,
  type EventInfo,
} from '../../fixtures';

const DOCKER_HOST = process.env.DOCKER_HOST || 'localhost';
const API_URL = `https://${DOCKER_HOST}/api`;

/** Today's date as YYYY-MM-DD (UTC — every series here is timezone: 'UTC'). */
function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * A `datetime-local` value `days` out at `hhmm`, expressed in UTC.
 * The series is created with timezone 'UTC', so the modal's localToUTC()
 * maps this string onto the identical UTC instant.
 */
function utcSlot(days: number, hhmm: string): string {
  const d = new Date(Date.now() + days * 86_400_000);
  return `${d.toISOString().slice(0, 10)}T${hhmm}`;
}

/** Series payload with every field the one-off modal prefills from. */
function makeSeries(
  orgPk: number,
  leaguePk: number,
  overrides: Record<string, unknown> = {},
) {
  return {
    organization: orgPk,
    name: 'E2E One-Off Series',
    description: 'Series under test',
    frequency: 'weekly',
    day_of_week: 2,
    time_of_day: '20:00:00',
    starts_at: todayISO(),
    generate_days_ahead: 3,
    is_active: true,
    tournament_name: 'E2E One-Off Tournament',
    tournament_league: leaguePk,
    tournament_type: 'single_elimination',
    game_type: 1,
    draft_type: 'shuffle',
    people_per_team: 5,
    number_of_teams: null,
    timezone: 'UTC',
    auto_approve: true,
    max_players: null,
    ...overrides,
  };
}

async function createSeries(
  context: import('@playwright/test').BrowserContext,
  payload: Record<string, unknown>,
) {
  const resp = await postWithCsrf(context, `${API_URL}/events/repeaters/`, payload);
  if (!resp.ok()) {
    throw new Error(`Create series failed: ${resp.status()} ${await resp.text()}`);
  }
  return resp.json();
}

let eventInfo: EventInfo;

test.describe('Events - Series one-off + reactivate (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test('staff creates a one-off event from the series page', async ({
    context,
    page,
  }) => {
    const series = await createSeries(
      context,
      makeSeries(eventInfo.orgPk, eventInfo.leaguePk),
    );

    await visitAndWaitForHydration(page, `/event-series/${series.id}`);

    await page.getByTestId('create-one-off-btn').click();
    await expect(page.getByTestId('create-one-off-modal')).toBeVisible();

    const ONE_OFF_NAME = 'E2E Holiday Special';
    // 03:15 never coincides with the series' 20:00 cadence slot, so the
    // backend's occurrence-collision guard stays out of the way.
    const slot = utcSlot(3, '03:15');
    await page.getByTestId('one-off-name-input').fill(ONE_OFF_NAME);
    await page.getByTestId('one-off-scheduled-input').fill(slot);

    const [createResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/events/repeaters/${series.id}/create-event/`) &&
          r.request().method() === 'POST',
      ),
      page.getByTestId('form-dialog-submit').click(),
    ]);
    expect(createResp.status()).toBe(201);

    await expect(page.getByTestId('create-one-off-modal')).toBeHidden();

    // The new row lands in the Upcoming grid carrying the one-off badge.
    await expect(page.getByRole('heading', { name: /^Upcoming/ })).toBeVisible();
    const card = page
      .locator('a[href^="/events/"]')
      .filter({ hasText: ONE_OFF_NAME });
    await expect(card).toHaveCount(1);
    await expect(card.getByTestId('one-off-badge')).toBeVisible();

    // ... and is flagged off-schedule server-side, inheriting the series config.
    const eventsResp = await context.request.get(
      `${API_URL}/events/?event_repeater=${series.id}`,
    );
    expect(eventsResp.ok()).toBeTruthy();
    const events = await eventsResp.json();
    const created = events.find((e: { name: string }) => e.name === ONE_OFF_NAME);
    expect(created).toBeTruthy();
    expect(created.is_off_schedule).toBe(true);
    expect(created.state).toBe('upcoming');
    expect(new Date(created.scheduled_at).toISOString().slice(0, 16)).toBe(slot);
  });

  test('staff reactivates a paused series and gets non-duplicated events', async ({
    context,
    page,
  }) => {
    const series = await createSeries(
      context,
      makeSeries(eventInfo.orgPk, eventInfo.leaguePk, {
        name: 'E2E Paused Series',
        frequency: 'daily',
        is_active: false,
      }),
    );

    await visitAndWaitForHydration(page, `/event-series/${series.id}`);

    await expect(page.getByTestId('series-active-badge')).toHaveText('Inactive');
    await expect(page.getByTestId('reactivate-series-btn')).toBeVisible();

    await page.getByTestId('reactivate-series-btn').click();
    await expect(page.getByTestId('reactivate-series-dialog')).toBeVisible();

    const [reactivateResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/events/repeaters/${series.id}/reactivate/`) &&
          r.request().method() === 'POST',
      ),
      page.getByTestId('reactivate-series-confirm').click(),
    ]);
    expect(reactivateResp.status()).toBe(200);

    await expect(page.getByTestId('series-active-badge')).toHaveText('Active');
    await expect(page.getByTestId('reactivate-series-btn')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: /^Upcoming/ })).toBeVisible();

    const eventsResp = await context.request.get(
      `${API_URL}/events/?event_repeater=${series.id}`,
    );
    expect(eventsResp.ok()).toBeTruthy();
    const events: { scheduled_at: string }[] = await eventsResp.json();
    expect(events.length).toBeGreaterThan(0);

    // Every cadence slot appears exactly once — reactivate must not stack a
    // fresh generation on top of rows an earlier schedule left behind.
    const slots = events.map((e) => e.scheduled_at);
    expect(new Set(slots).size).toBe(slots.length);

    // The UI shows the same number of upcoming cards the API reports.
    await expect(page.locator('a[href^="/events/"]')).toHaveCount(events.length);
  });

  test('non-staff sees neither the one-off nor the reactivate action', async ({
    context,
    page,
  }) => {
    const series = await createSeries(
      context,
      makeSeries(eventInfo.orgPk, eventInfo.leaguePk, {
        name: 'E2E Non-Staff Series',
        is_active: false,
      }),
    );

    await loginEventPlayer(context);
    await visitAndWaitForHydration(page, `/event-series/${series.id}`);

    // Guard against asserting on an unauthenticated or unrendered page:
    // Subscribe only renders once the user store has a current user.
    await expect(
      page.getByRole('heading', { name: 'E2E Non-Staff Series' }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Subscribe' })).toBeVisible();

    await expect(page.getByTestId('create-one-off-btn')).toHaveCount(0);
    await expect(page.getByTestId('reactivate-series-btn')).toHaveCount(0);
    await expect(page.getByTestId('edit-series-btn')).toHaveCount(0);
  });
});
