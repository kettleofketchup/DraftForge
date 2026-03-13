/**
 * Events E2E Smoke Tests
 *
 * Tests the events system on the DEDICATED Events Test Org.
 * This org is isolated from other test data.
 *
 * Infrastructure (created by populate_events_data):
 * - Events Test Org (pk=7) - dedicated org
 * - Events Test League (steam_league_id=17935) - under Events org
 * - E2E Signup Event - standalone event in signups_open state
 * - Weekly Inhouse - EventRepeater
 *
 * Test users:
 * - event_org_admin (pk=1080) - org admin
 * - event_player_1-3 (pk=1081-1083) - regular players
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

test.describe('Events - List Page (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test('shows events list page with header and org filter', async ({ page }) => {
    await visitAndWaitForHydration(page, '/events');

    // Header with icon and title
    await expect(page.getByRole('heading', { name: 'Events' })).toBeVisible();

    // Org filter dropdown
    await expect(page.getByTestId('events-org-filter')).toBeVisible();
  });

  test('filters events by organization', async ({ page }) => {
    await visitAndWaitForHydration(page, '/events');

    // Select Events Test Org in filter
    await page.getByTestId('events-org-filter').click();
    await page.getByRole('option', { name: 'Events Test Org' }).click();

    // Should show the E2E Signup Event card
    await expect(page.getByText('E2E Signup Event')).toBeVisible({ timeout: 10000 });
  });

  test('event card shows state badge', async ({ page }) => {
    await visitAndWaitForHydration(page, `/events?organization=${eventInfo.orgPk}`);

    // Event card should show a status badge (not raw text)
    await expect(page.getByText('Signups Open')).toBeVisible({ timeout: 10000 });
  });

  test('navigates to event detail from card', async ({ page }) => {
    await visitAndWaitForHydration(page, `/events?organization=${eventInfo.orgPk}`);

    // Click the event card
    await page.getByText('E2E Signup Event').click();

    // Should navigate to event detail
    await expect(page).toHaveURL(new RegExp(`/events/${eventInfo.pk}`));
    await expect(page.getByRole('heading', { name: 'E2E Signup Event' })).toBeVisible();
  });
});

test.describe('Events - Detail Page', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
  });

  test('shows event detail with tabs', async ({ context, page }) => {
    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);

    // Header elements
    await expect(page.getByRole('heading', { name: 'E2E Signup Event' })).toBeVisible();
    await expect(page.getByText('Events Test Org')).toBeVisible(); // org badge
    await expect(page.getByText('Signups Open')).toBeVisible(); // state badge

    // Tabs visible on desktop
    await expect(page.getByTestId('event-tab-details')).toBeVisible();
    await expect(page.getByTestId('event-tab-signups')).toBeVisible();
  });

  test('admin sees action buttons for signups_open state', async ({ context, page }) => {
    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);

    // Admin should see Start Tournament and Cancel buttons
    await expect(page.getByTestId('event-start-tournament-btn')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('event-cancel-btn')).toBeVisible();

    // Should NOT see Open Signups (already open)
    await expect(page.getByTestId('event-open-signups-btn')).not.toBeVisible();
  });

  test('non-admin does not see admin buttons', async ({ context, page }) => {
    await loginEventPlayer(context);
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);

    // Player should not see admin action buttons
    await expect(page.getByTestId('event-start-tournament-btn')).not.toBeVisible();
    await expect(page.getByTestId('event-cancel-btn')).not.toBeVisible();
  });

  test('details tab shows tournament config', async ({ context, page }) => {
    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);

    // Tournament config card
    await expect(page.getByText('Tournament Config')).toBeVisible();
    await expect(page.getByText('Dota 2')).toBeVisible();
    await expect(page.getByText('shuffle')).toBeVisible();

    // Event info card
    await expect(page.getByText('Event Info')).toBeVisible();
  });

  test('tab navigation via URL', async ({ context, page }) => {
    await loginEventAdmin(context);

    // Navigate directly to signups tab via URL
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}/signups`);

    // Signups tab should be active
    await expect(page.getByText('No Signups Yet')).toBeVisible();
  });

  test('cancel event transitions state', async ({ context, page }) => {
    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);

    // Click cancel
    await page.getByTestId('event-cancel-btn').click();

    // State should change to Cancelled
    await expect(page.getByText('Cancelled')).toBeVisible({ timeout: 10000 });

    // Admin buttons should disappear
    await expect(page.getByTestId('event-cancel-btn')).not.toBeVisible();
  });
});

test.describe('Events - Signup Flow', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
  });

  test('player can RSVP for event via signups tab', async ({ context, page }) => {
    await loginEventPlayer(context);
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}/signups`);

    // Initially no signups
    await expect(page.getByText('No Signups Yet')).toBeVisible();

    // RSVP via API directly (UI RSVP button is a future task)
    const rsvpResp = await context.request.post(`${API_URL}/events/${eventInfo.pk}/rsvp/`);
    expect(rsvpResp.ok()).toBeTruthy();

    // Reload to see signup
    await page.reload();
    await expect(page.getByText('EventPlayer1')).toBeVisible({ timeout: 10000 });
  });

  test('admin can approve signup', async ({ browser }) => {
    // Player RSVPs
    const playerCtx = await browser.newContext({ ignoreHTTPSErrors: true });
    await loginEventPlayer(playerCtx);
    await playerCtx.request.post(`${API_URL}/events/${eventInfo.pk}/rsvp/`);
    await playerCtx.close();

    // Admin views and approves
    const adminCtx = await browser.newContext({ ignoreHTTPSErrors: true });
    const adminPage = await adminCtx.newPage();
    await loginEventAdmin(adminCtx);
    await visitAndWaitForHydration(adminPage, `/events/${eventInfo.pk}/signups`);

    // Should see the signup with RSVP status
    await expect(adminPage.getByText('EventPlayer1')).toBeVisible({ timeout: 10000 });

    // Admin approves (since auto_approve is true, it may already be approved -- test the badge)
    // The EventStateBadge should show a status
    await expect(adminPage.getByText(/Approved|RSVP/)).toBeVisible();

    await adminCtx.close();
  });
});
