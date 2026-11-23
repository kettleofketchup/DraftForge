/**
 * Create Event E2E Tests
 *
 * Tests creating events (one-off and recurring) from the organization
 * Events tab using the CreateEventModal.
 *
 * Uses the dedicated Events Test Org (pk=7) infrastructure.
 */

import type { Page } from '@playwright/test';
import {
  expect,
  getEventsTestData,
  loginEventAdmin,
  loginEventPlayer,
  resetEventsData,
  test,
  visitAndWaitForHydration,
  type EventInfo,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

/** Fields are split across sections; inactive panels are hidden. */
async function openTab(page: Page, tab: 'event' | 'tournament' | 'lobby') {
  const trigger = page.getByTestId(`event-modal-tab-${tab}`);
  await trigger.click();
  await expect(trigger).toHaveAttribute('data-state', 'active');
}

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

    await page.getByTestId('org-tab-events').click();

    // Use data-testid per the project's testing skill: getByRole with text
    // matching is fragile on the org page where "Events" is a substring of
    // multiple headings (h1 "Events Test Org", h3 "Events (N)", h3 "Repeating
    // Events (N)").
    await expect(page.getByTestId('org-events-heading')).toBeVisible();
    await expect(page.getByTestId('create-event-btn')).toBeVisible();
  });

  test('non-admin cannot see create event button', async ({
    context,
    page,
  }) => {
    await loginEventPlayer(context);
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();

    await expect(page.getByTestId('org-events-heading')).toBeVisible();
    await expect(page.getByTestId('create-event-btn')).not.toBeVisible();
  });

  test('opens create event modal with form fields', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    // Modal should appear with title
    await expect(
      page.getByRole('heading', { name: 'Create Event' }),
    ).toBeVisible();

    // Core fields visible
    await expect(page.getByTestId('event-name-input')).toBeVisible();
    await expect(page.getByTestId('event-scheduled-input')).toBeVisible();
    await openTab(page, 'tournament');
    await expect(page.getByTestId('event-tournament-name-input')).toBeVisible();
    await openTab(page, 'event');

    // Recurring checkbox visible but unchecked
    const recurringCheckbox = page.getByTestId('event-recurring-checkbox');
    await expect(recurringCheckbox).toBeVisible();
    await expect(recurringCheckbox).not.toBeChecked();

    // Recurring-only fields should NOT be visible
    await expect(page.getByTestId('event-frequency-select')).not.toBeVisible();
    await expect(page.getByTestId('event-day-select')).not.toBeVisible();
  });

  test('settings search jumps to a field in another section', async ({
    page,
  }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);
    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();
    await expect(page.getByTestId('event-modal-tab-event')).toHaveAttribute(
      'data-state',
      'active',
    );

    await page.getByTestId('event-modal-tab-event').focus();
    await page.keyboard.press('/');
    const search = page.getByTestId('event-modal-search');
    await expect(search).toBeFocused();
    await search.fill('team size');
    // A registry keyword: "team size" is in neither the label nor the description.
    await expect(
      page.getByTestId('event-modal-search-hit').filter({
        has: page.locator('span', { hasText: /^People Per Team$/ }),
      }),
    ).toContainText('Tournament');
    await expect(page.getByTestId('event-modal-tab-discord')).toHaveCount(0);
    await page.keyboard.press('Enter');

    await expect(
      page.getByTestId('event-modal-tab-tournament'),
    ).toHaveAttribute('data-state', 'active');
    await expect(page.getByTestId('event-people-per-team-input')).toBeFocused();
    // Enter picked the result; it must not have submitted the form.
    await expect(page.getByTestId('create-event-modal')).toBeVisible();
  });

  test('toggling recurring shows repeater fields', async ({ page }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    await page.getByTestId('event-recurring-checkbox').check();

    // Title should change
    await expect(
      page.getByRole('heading', { name: 'Create Recurring Event' }),
    ).toBeVisible();

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
    await openTab(page, 'tournament');
    await page
      .getByTestId('event-tournament-name-input')
      .fill('E2E Tournament');

    // Select league
    await page.getByTestId('event-league-select').click();
    await page
      .getByRole('option', { name: 'Events Test League', exact: true })
      .click();

    // Set scheduled date (tomorrow)
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dateStr = tomorrow.toISOString().slice(0, 16); // YYYY-MM-DDTHH:mm
    await openTab(page, 'event');
    await page.getByTestId('event-scheduled-input').fill(dateStr);

    await page.getByTestId('form-dialog-submit').click();

    // Modal should close and event should appear in list
    await expect(
      page.getByRole('heading', { name: 'Create Event' }),
    ).not.toBeVisible({ timeout: 10000 });
    await expect(page.getByText('E2E One-Off Test').first()).toBeVisible({
      timeout: 10000,
    });
  });

  test('creates event with double elimination bracket type', async ({
    page,
  }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    await page.getByTestId('event-name-input').fill('E2E Double Elim Event');
    await openTab(page, 'tournament');
    await page.getByTestId('event-tournament-name-input').fill('DE Tournament');

    await page.getByTestId('event-league-select').click();
    await page
      .getByRole('option', { name: 'Events Test League', exact: true })
      .click();

    // Select Double Elimination bracket type
    await page.getByTestId('event-bracket-select').click();
    await page.getByRole('option', { name: 'Double Elimination' }).click();

    // Set scheduled date
    await openTab(page, 'event');
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    await page
      .getByTestId('event-scheduled-input')
      .fill(tomorrow.toISOString().slice(0, 16));

    await page.getByTestId('form-dialog-submit').click();

    // Verify event created with correct tournament_type via API
    await expect(
      page.getByRole('heading', { name: 'Create Event' }),
    ).not.toBeVisible({ timeout: 10000 });
    const resp = await page.request.get(
      `${API_URL}/events/?organization=${eventInfo.orgPk}`,
    );
    expect(resp.ok()).toBeTruthy();
    const events = await resp.json();
    const created = events.find(
      (e: { name: string }) => e.name === 'E2E Double Elim Event',
    );
    expect(created).toBeTruthy();
    expect(created.tournament_type).toBe('double_elimination');
  });

  test('switching game to Deadlock updates people per team', async ({
    page,
  }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    await openTab(page, 'tournament');

    // Default should be 5 (Dota 2)
    await expect(page.getByTestId('event-people-per-team-input')).toHaveValue(
      '5',
    );

    // Switch to Deadlock
    await page.getByTestId('event-game-select').click();
    await page.getByRole('option', { name: 'Deadlock' }).click();

    // People per team should auto-update to 6
    await expect(page.getByTestId('event-people-per-team-input')).toHaveValue(
      '6',
    );

    // Switch back to Dota 2
    await page.getByTestId('event-game-select').click();
    await page.getByRole('option', { name: 'Dota 2' }).click();

    // Should reset to 5
    await expect(page.getByTestId('event-people-per-team-input')).toHaveValue(
      '5',
    );
  });

  test('max teams and people per team can be cleared and retyped', async ({
    page,
  }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);
    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();
    await openTab(page, 'tournament');

    const maxTeams = page.getByTestId('event-max-teams-input');
    const unlimited = page.getByTestId('event-unlimited-checkbox');
    if (await unlimited.isChecked()) await unlimited.uncheck();
    await expect(maxTeams).toBeEnabled();

    await maxTeams.click();
    await maxTeams.press('ControlOrMeta+a');
    await maxTeams.press('Backspace');
    await expect(maxTeams).toHaveValue('');
    await expect(maxTeams).toBeEnabled();
    await expect(unlimited).not.toBeChecked();

    await maxTeams.pressSequentially('16');
    await expect(maxTeams).toHaveValue('16');
    await maxTeams.blur();
    await expect(maxTeams).toHaveValue('16');
    await expect(unlimited).not.toBeChecked();

    const people = page.getByTestId('event-people-per-team-input');
    await people.click();
    await people.press('ControlOrMeta+a');
    await people.press('Backspace');
    await expect(people).toHaveValue('');
    await people.pressSequentially('3');
    await expect(people).toHaveValue('3');
  });

  test('league combobox: search filters and selects on create', async ({
    page,
  }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);
    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    await openTab(page, 'tournament');

    const trigger = page.getByTestId('event-league-select');
    await trigger.click();

    // Type into the cmdk search input — first 3 chars of the seeded league name
    await page.getByTestId('event-league-search').fill('Eve');

    // Pick the seeded events league via its preserved per-item data-testid
    await page.getByTestId(`event-league-option-${eventInfo.leaguePk}`).click();

    // Trigger should now show the selected league name
    await expect(trigger).toContainText('Events Test League');
  });

  test('league combobox: clear selection on create submits null', async ({
    page,
  }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);
    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    // Pick a league
    await openTab(page, 'tournament');
    await page.getByTestId('event-league-select').click();
    await page.getByTestId(`event-league-option-${eventInfo.leaguePk}`).click();

    // Reopen and clear
    await page.getByTestId('event-league-select').click();
    await page.getByTestId('event-league-clear').click();

    // Trigger should show the placeholder again
    await expect(page.getByTestId('event-league-select')).toContainText(
      /select league/i,
    );

    // Fill the rest of the required fields (mirroring the one-off-event test)
    await page
      .getByTestId('event-tournament-name-input')
      .fill('E2E Tournament');
    await openTab(page, 'event');
    await page.getByTestId('event-name-input').fill('E2E Clear-League Test');
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    await page
      .getByTestId('event-scheduled-input')
      .fill(tomorrow.toISOString().slice(0, 16));

    // Capture the POST payload as the form submits
    const createReqPromise = page.waitForRequest(
      (req) => req.url().includes('/api/events') && req.method() === 'POST',
    );
    await page.getByTestId('form-dialog-submit').click();
    const createReq = await createReqPromise;

    const body = createReq.postDataJSON();
    expect(body.tournament_league ?? null).toBeNull();
  });

  test('league combobox: mobile renders a Select fallback with clear sentinel', async ({
    page,
  }) => {
    // Set mobile viewport before navigation so the page renders its mobile-nav
    // layout (a `MobileNavDropdown` instead of a horizontal tablist).
    await page.setViewportSize({ width: 375, height: 812 }); // iPhone 13-ish

    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    // The desktop `org-tab-events` button is hidden by `md:block`/`md:hidden`
    // at this width — switch tabs via the mobile dropdown instead.
    await page.getByTestId('page-nav-trigger').click();
    await page.getByTestId('page-nav-events').click();
    await page.getByTestId('create-event-btn').click();
    await openTab(page, 'tournament');

    const trigger = page.getByTestId('event-league-select');

    // Mobile branch uses shadcn Select — there should be no cmdk search input.
    await trigger.click();
    await expect(page.getByTestId('event-league-search')).toHaveCount(0);

    // The "— No league —" sentinel should round-trip to null in the form.
    await page.getByTestId('event-league-clear').click();
    await expect(trigger).toContainText(/select league/i);

    // Picking a real league still works
    await trigger.click();
    await page.getByTestId(`event-league-option-${eventInfo.leaguePk}`).click();
    await expect(trigger).toContainText('Events Test League');
  });

  test('creates a recurring event (event repeater) via modal', async ({
    page,
  }) => {
    await visitAndWaitForHydration(page, `/organizations/${eventInfo.orgPk}`);

    await page.getByTestId('org-tab-events').click();
    await page.getByTestId('create-event-btn').click();

    // Fill basic fields
    await page.getByTestId('event-name-input').fill('E2E Weekly Recurring');
    await openTab(page, 'tournament');
    await page
      .getByTestId('event-tournament-name-input')
      .fill('E2E Recurring Tourney');

    // Select league
    await page.getByTestId('event-league-select').click();
    await page
      .getByRole('option', { name: 'Events Test League', exact: true })
      .click();

    // Toggle recurring
    await openTab(page, 'event');
    await page.getByTestId('event-recurring-checkbox').check();
    await expect(
      page.getByRole('heading', { name: 'Create Recurring Event' }),
    ).toBeVisible();

    // Fill recurring fields
    await page.getByTestId('event-frequency-select').click();
    await page.getByRole('option', { name: 'Weekly' }).click();

    await page.getByTestId('event-day-select').click();
    await page.getByRole('option', { name: 'Wednesday' }).click();

    await page.getByTestId('event-time-input').fill('19:00');

    // Set start date
    const today = new Date().toISOString().slice(0, 10);
    await page.getByTestId('event-starts-input').fill(today);

    await page.getByTestId('form-dialog-submit').click();

    // Modal should close with success
    await expect(
      page.getByRole('heading', { name: 'Create Recurring Event' }),
    ).not.toBeVisible({ timeout: 10000 });

    // Verify via API that the repeater was created
    const resp = await page.request.get(
      `${API_URL}/events/repeaters/?organization=${eventInfo.orgPk}`,
    );
    expect(resp.ok()).toBeTruthy();
    const repeaters = await resp.json();
    const created = repeaters.find(
      (r: { name: string }) => r.name === 'E2E Weekly Recurring',
    );
    expect(created).toBeTruthy();
    expect(created.frequency).toBe('weekly');
    expect(created.day_of_week).toBe(3); // Wednesday
  });
});
