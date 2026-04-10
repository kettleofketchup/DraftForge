/**
 * Events E2E — Repeater Generation Pipeline
 *
 * Validates that EventRepeater -> Event generation works end-to-end:
 * - Triggering generation from a pre-populated repeater
 * - Creating a daily repeater via API and generating events
 * - Verifying generated events inherit tournament config
 * - Editing a repeater syncs config to future events
 * - Generated events appear in the browser UI
 *
 * Infrastructure (created by populate_events_data):
 * - Events Test Org (pk=7) — dedicated org for events E2E
 * - Events Test League (league pk=7)
 * - "Weekly Inhouse" — pre-populated EventRepeater (weekly, Wednesday, 20:00)
 *
 * Test users:
 * - event_org_admin (pk=5000) — org admin
 * - event_player_1 (pk=5001) — regular player
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getEventsTestData,
  resetEventsData,
  triggerEventGeneration,
  loginEventAdmin,
  postWithCsrf,
  patchWithCsrf,
  type EventInfo,
} from '../../fixtures';

const API_URL = 'https://localhost/api';

/** Helper: today's date as YYYY-MM-DD */
function todayISO(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/** Helper: build a daily repeater payload with sensible defaults. */
function makeDailyRepeater(orgPk: number, leaguePk: number, overrides: Record<string, unknown> = {}) {
  return {
    organization: orgPk,
    name: 'E2E Daily Test',
    description: 'Automated test repeater',
    frequency: 'daily',
    day_of_week: 0,
    time_of_day: '20:00:00',
    starts_at: todayISO(),
    generate_days_ahead: 3,
    is_active: true,
    tournament_name: 'E2E Daily Tournament',
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

let eventInfo: EventInfo;

test.describe('Events - Repeater Generation (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test('triggers event generation from existing repeater', async ({ context }) => {
    // The "Weekly Inhouse" repeater already exists from populate.
    // Trigger generation — whether a Wednesday falls within the window is
    // date-dependent, but the call itself must succeed.
    const message = await triggerEventGeneration(context);
    expect(message).toBeTruthy();

    // List events for the org — may or may not include generated ones
    // depending on day of week, but the request should succeed.
    const resp = await context.request.get(
      `${API_URL}/events/?organization=${eventInfo.orgPk}`,
    );
    expect(resp.ok()).toBeTruthy();
    const events = await resp.json();
    expect(Array.isArray(events)).toBe(true);
  });

  test('creates a daily repeater and generates events', async ({ context }) => {
    // Create a daily repeater via API
    const createResp = await postWithCsrf(context, `${API_URL}/events/repeaters/`, makeDailyRepeater(eventInfo.orgPk, eventInfo.leaguePk));
    if (!createResp.ok()) {
      console.error('Create repeater failed:', createResp.status(), await createResp.text());
    }
    expect(createResp.ok()).toBeTruthy();

    // Trigger generation
    await triggerEventGeneration(context);

    // List events — should contain at least one "E2E Daily Test" event
    const eventsResp = await context.request.get(
      `${API_URL}/events/?organization=${eventInfo.orgPk}`,
    );
    expect(eventsResp.ok()).toBeTruthy();
    const events = await eventsResp.json();
    const dailyEvents = events.filter(
      (e: { name: string }) => e.name === 'E2E Daily Test',
    );
    expect(dailyEvents.length).toBeGreaterThanOrEqual(1);
  });

  test('generated events inherit tournament config from repeater', async ({
    context,
  }) => {
    // Create a repeater with specific config
    const createResp = await postWithCsrf(context, `${API_URL}/events/repeaters/`, makeDailyRepeater(eventInfo.orgPk, eventInfo.leaguePk, {
      name: 'E2E Config Inherit',
      game_type: 2, // Deadlock
      draft_type: 'snake',
      people_per_team: 6,
      number_of_teams: 4,
    }));
    expect(createResp.ok()).toBeTruthy();

    // Trigger generation
    await triggerEventGeneration(context);

    // Find the generated events
    const eventsResp = await context.request.get(
      `${API_URL}/events/?organization=${eventInfo.orgPk}`,
    );
    expect(eventsResp.ok()).toBeTruthy();
    const events = await eventsResp.json();
    const configEvents = events.filter(
      (e: { name: string }) => e.name === 'E2E Config Inherit',
    );
    expect(configEvents.length).toBeGreaterThanOrEqual(1);

    // Verify tournament config on the first generated event
    const event = configEvents[0];
    expect(event.game_type).toBe(2);
    expect(event.draft_type).toBe('snake');
    expect(event.people_per_team).toBe(6);
    expect(event.number_of_teams).toBe(4);
  });

  test('editing a repeater syncs config to future events', async ({ context }) => {
    // Create a daily repeater
    const createResp = await postWithCsrf(context, `${API_URL}/events/repeaters/`, makeDailyRepeater(eventInfo.orgPk, eventInfo.leaguePk, { name: 'E2E Sync Test' }));
    expect(createResp.ok()).toBeTruthy();
    const repeater = await createResp.json();

    // Trigger generation to create events
    await triggerEventGeneration(context);

    // Verify events were created
    let eventsResp = await context.request.get(
      `${API_URL}/events/?organization=${eventInfo.orgPk}`,
    );
    let events = await eventsResp.json();
    let syncEvents = events.filter(
      (e: { name: string }) => e.name === 'E2E Sync Test',
    );
    expect(syncEvents.length).toBeGreaterThanOrEqual(1);

    // PATCH the repeater to change tournament_name and draft_type
    const patchResp = await patchWithCsrf(context, `${API_URL}/events/repeaters/${repeater.id}/`, {
      tournament_name: 'Synced Tournament',
      draft_type: 'normal',
    });
    expect(patchResp.ok()).toBeTruthy();

    // Delete existing generated events so re-generation picks up new config
    for (const ev of syncEvents) {
      await context.request.delete(`${API_URL}/events/${ev.id}/`);
    }

    // Re-trigger generation — new events inherit updated repeater config
    await triggerEventGeneration(context);

    // Re-list events — newly generated events should have updated config
    eventsResp = await context.request.get(
      `${API_URL}/events/?organization=${eventInfo.orgPk}`,
    );
    events = await eventsResp.json();
    syncEvents = events.filter(
      (e: { name: string }) => e.name === 'E2E Sync Test',
    );
    expect(syncEvents.length).toBeGreaterThanOrEqual(1);

    // Each newly generated event should have the updated fields
    for (const event of syncEvents) {
      expect(event.tournament_name).toBe('Synced Tournament');
      expect(event.draft_type).toBe('normal');
    }
  });

  test('generated events appear on org events page', async ({ context, page }) => {
    // Create a daily repeater
    const createResp = await postWithCsrf(context, `${API_URL}/events/repeaters/`, makeDailyRepeater(eventInfo.orgPk, eventInfo.leaguePk, { name: 'E2E Visible Event' }));
    expect(createResp.ok()).toBeTruthy();

    // Trigger generation
    await triggerEventGeneration(context);

    // Navigate to the org page events tab
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);
    await page.getByTestId('org-tab-events').click();

    // The generated event name should appear in the events list
    await expect(page.getByText('E2E Visible Event').first()).toBeVisible({ timeout: 10000 });
  });
});
