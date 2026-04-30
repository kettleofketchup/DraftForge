/**
 * Create Event E2E Tests
 *
 * Tests creating events (one-off and recurring) from the organization
 * Events tab using the CreateEventModal.
 *
 * Uses the dedicated Events Test Org (pk=7) infrastructure.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getEventsTestData,
  resetEventsData,
  loginEventAdmin,
  loginEventPlayer,
  type EventInfo,
} from '../../fixtures';

const API_URL = 'https://localhost/api';

let eventInfo: EventInfo;

test.describe('Events - Create Event (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test('org page shows events tab with create button', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    // Click the Events tab
    await page.getByTestId('org-tab-events').click();

    // Should see Events heading and Create Event button
    await expect(page.getByRole('heading', { name: 'Events' })).toBeVisible();
    await expect(page.getByTestId('create-event-btn')).toBeVisible();
  });

  test('non-admin cannot see create event button', async ({ context, page }) => {
    await loginEventPlayer(context);
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();

    await expect(page.getByRole('heading', { name: 'Events' })).toBeVisible();
    await expect(page.getByTestId('create-event-btn')).not.toBeVisible();
  });

  test('opens create event modal with form fields', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    // Modal should appear with title
    await expect(page.getByRole('heading', { name: 'Create Event' })).toBeVisible();

    // Core fields visible
    await expect(page.getByTestId('event-name-input')).toBeVisible();
    await expect(page.getByTestId('event-tournament-name-input')).toBeVisible();
    await expect(page.getByTestId('event-scheduled-input')).toBeVisible();

    // Recurring checkbox visible but unchecked
    const recurringCheckbox = page.getByTestId('event-recurring-checkbox');
    await expect(recurringCheckbox).toBeVisible();
    await expect(recurringCheckbox).not.toBeChecked();

    // Recurring-only fields should NOT be visible
    await expect(page.getByTestId('event-frequency-select')).not.toBeVisible();
    await expect(page.getByTestId('event-day-select')).not.toBeVisible();
  });

  test('toggling recurring shows repeater fields', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    // Check the recurring checkbox
    await page.getByTestId('event-recurring-checkbox').check();

    // Title should change
    await expect(page.getByRole('heading', { name: 'Create Recurring Event' })).toBeVisible();

    // Recurring fields should now be visible
    await expect(page.getByTestId('event-frequency-select')).toBeVisible();
    await expect(page.getByTestId('event-day-select')).toBeVisible();
    await expect(page.getByTestId('event-time-input')).toBeVisible();
    await expect(page.getByTestId('event-starts-input')).toBeVisible();
    await expect(page.getByTestId('event-generate-days-input')).toBeVisible();

    // Scheduled Date & Time should NOT be visible (only for one-off events)
    await expect(page.getByTestId('event-scheduled-input')).not.toBeVisible();
  });

  test('creates a one-off event via modal', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    // Fill out form
    await page.getByTestId('event-name-input').fill('E2E One-Off Test');
    await page.getByTestId('event-tournament-name-input').fill('E2E Tournament');

    // Select league
    await page.getByTestId('event-league-select').click();
    await page.getByRole('option', { name: 'Events Test League', exact: true }).click();

    // Set scheduled date (tomorrow)
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dateStr = tomorrow.toISOString().slice(0, 16); // YYYY-MM-DDTHH:mm
    await page.getByTestId('event-scheduled-input').fill(dateStr);

    // Submit
    await page.getByTestId('form-dialog-submit').click();

    // Modal should close and event should appear in list
    await expect(page.getByRole('heading', { name: 'Create Event' })).not.toBeVisible({ timeout: 10000 });
    await expect(page.getByText('E2E One-Off Test').first()).toBeVisible({ timeout: 10000 });
  });

  test('creates event with double elimination bracket type', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    await page.getByTestId('event-name-input').fill('E2E Double Elim Event');
    await page.getByTestId('event-tournament-name-input').fill('DE Tournament');

    await page.getByTestId('event-league-select').click();
    await page.getByRole('option', { name: 'Events Test League', exact: true }).click();

    // Select Double Elimination bracket type
    await page.getByTestId('event-bracket-select').click();
    await page.getByRole('option', { name: 'Double Elimination' }).click();

    // Set scheduled date
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    await page.getByTestId('event-scheduled-input').fill(tomorrow.toISOString().slice(0, 16));

    await page.getByTestId('form-dialog-submit').click();

    // Verify event created with correct tournament_type via API
    await expect(page.getByRole('heading', { name: 'Create Event' })).not.toBeVisible({ timeout: 10000 });
    const resp = await page.request.get(`${API_URL}/events/?organization=${eventInfo.orgPk}`);
    expect(resp.ok()).toBeTruthy();
    const events = await resp.json();
    const created = events.find((e: { name: string }) => e.name === 'E2E Double Elim Event');
    expect(created).toBeTruthy();
    expect(created.tournament_type).toBe('double_elimination');
  });

  test('switching game to Deadlock updates people per team', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    // Default should be 5 (Dota 2)
    await expect(page.getByTestId('event-people-per-team-input')).toHaveValue('5');

    // Switch to Deadlock
    await page.getByTestId('event-game-select').click();
    await page.getByRole('option', { name: 'Deadlock' }).click();

    // People per team should auto-update to 6
    await expect(page.getByTestId('event-people-per-team-input')).toHaveValue('6');

    // Switch back to Dota 2
    await page.getByTestId('event-game-select').click();
    await page.getByRole('option', { name: 'Dota 2' }).click();

    // Should reset to 5
    await expect(page.getByTestId('event-people-per-team-input')).toHaveValue('5');
  });

  test('creates a recurring event (event repeater) via modal', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    // Fill basic fields
    await page.getByTestId('event-name-input').fill('E2E Weekly Recurring');
    await page.getByTestId('event-tournament-name-input').fill('E2E Recurring Tourney');

    // Select league
    await page.getByTestId('event-league-select').click();
    await page.getByRole('option', { name: 'Events Test League', exact: true }).click();

    // Toggle recurring
    await page.getByTestId('event-recurring-checkbox').check();
    await expect(page.getByRole('heading', { name: 'Create Recurring Event' })).toBeVisible();

    // Fill recurring fields
    await page.getByTestId('event-frequency-select').click();
    await page.getByRole('option', { name: 'Weekly' }).click();

    await page.getByTestId('event-day-select').click();
    await page.getByRole('option', { name: 'Wednesday' }).click();

    await page.getByTestId('event-time-input').fill('19:00');

    // Set start date
    const today = new Date().toISOString().slice(0, 10);
    await page.getByTestId('event-starts-input').fill(today);

    // Submit
    await page.getByTestId('form-dialog-submit').click();

    // Modal should close with success
    await expect(page.getByRole('heading', { name: 'Create Recurring Event' })).not.toBeVisible({ timeout: 10000 });

    // Verify via API that the repeater was created
    const resp = await page.request.get(`${API_URL}/events/repeaters/?organization=${eventInfo.orgPk}`);
    expect(resp.ok()).toBeTruthy();
    const repeaters = await resp.json();
    const created = repeaters.find((r: { name: string }) => r.name === 'E2E Weekly Recurring');
    expect(created).toBeTruthy();
    expect(created.frequency).toBe('weekly');
    expect(created.day_of_week).toBe(3); // Wednesday
  });
});
