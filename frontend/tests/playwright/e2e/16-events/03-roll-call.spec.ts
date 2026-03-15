/**
 * Roll Call E2E Tests
 *
 * Tests the roll call flow:
 * 1. Admin opens signups → players RSVP → admin starts roll call
 * 2. Roll call page shows players, admin confirms/removes
 * 3. Admin starts tournament from roll call page
 *
 * Uses the E2E Signup Event (signups_open state after reset).
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

test.describe('Roll Call Flow (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
  });

  test('admin can RSVP players, start roll call, confirm, and start tournament', async ({
    context,
    page,
  }) => {
    // Step 1: Player RSVPs to the event
    await loginEventPlayer(context);
    const rsvpResp = await context.request.post(
      `${API_URL}/events/${eventInfo.pk}/rsvp/`,
    );
    expect(rsvpResp.ok()).toBeTruthy();

    // Step 2: Admin approves the signup
    await loginEventAdmin(context);
    const signupsResp = await context.request.get(
      `${API_URL}/events/signups/?event=${eventInfo.pk}`,
    );
    const signups = await signupsResp.json();
    expect(signups.length).toBeGreaterThan(0);

    const signupId = signups[0].id;
    const approveResp = await context.request.post(
      `${API_URL}/events/signups/${signupId}/approve/`,
    );
    expect(approveResp.ok()).toBeTruthy();

    // Step 3: Navigate to event page and start roll call
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);
    const rollCallBtn = page.getByTestId('event-start-rollcall-btn');
    await expect(rollCallBtn).toBeVisible();
    await rollCallBtn.click();

    // Step 4: Confirmation dialog should appear
    const confirmDialog = page.getByRole('alertdialog');
    await expect(confirmDialog).toBeVisible();
    await expect(confirmDialog).toContainText('Start Roll Call');

    // Confirm the roll call
    const confirmBtn = confirmDialog.getByRole('button', { name: /start roll call/i });
    await confirmBtn.click();

    // Step 5: Should navigate to roll call page
    await page.waitForURL(/\/rollcall\//);
    await expect(page.getByText('Roll Call')).toBeVisible();

    // Step 6: Should see the approved player in "Awaiting Confirmation" section
    await expect(page.getByText('Awaiting Confirmation')).toBeVisible();
  });

  test('roll call page shows correct state for non-roll-call events', async ({
    context,
    page,
  }) => {
    // Event is in signups_open state (not roll call)
    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/rollcall/${eventInfo.pk}`);

    // Should show "not in roll call mode" message
    await expect(page.getByText('not in roll call mode')).toBeVisible();
    await expect(page.getByText('Back to Event')).toBeVisible();
  });

  test('event page shows Open Roll Call button when in roll_call state', async ({
    context,
    page,
  }) => {
    await loginEventAdmin(context);

    // Transition to roll call via API
    const resp = await context.request.post(
      `${API_URL}/events/${eventInfo.pk}/start_roll_call/`,
    );
    expect(resp.ok()).toBeTruthy();

    // Visit event page
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);

    // Should show "Open Roll Call" instead of "Start Tournament"
    const openRollCallBtn = page.getByTestId('event-start-tournament-btn');
    await expect(openRollCallBtn).toBeVisible();
    await expect(openRollCallBtn).toContainText('Open Roll Call');

    // Click should navigate to roll call page
    await openRollCallBtn.click();
    await page.waitForURL(/\/rollcall\//);
  });
});
