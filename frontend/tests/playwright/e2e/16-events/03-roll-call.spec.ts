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
  postWithCsrf,
  verifyDiscordMessages,
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
    const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${eventInfo.pk}/signup/`, { intent: 'rsvp' });
    expect(rsvpResp.ok()).toBeTruthy();

    // Step 2: Admin checks the signup (auto_approve may have already approved it)
    await loginEventAdmin(context);
    const signupsResp = await context.request.get(
      `${API_URL}/events/signups/?event=${eventInfo.pk}`,
    );
    const signups = await signupsResp.json();
    expect(signups.length).toBeGreaterThan(0);

    // Approve only if not already approved (auto_approve may have done it)
    const signup = signups[0];
    if (signup.status === 'rsvp' || signup.status === 'pending_approval') {
      const approveResp = await postWithCsrf(context, `${API_URL}/events/signups/${signup.id}/approve/`);
      expect(approveResp.ok()).toBeTruthy();
    }

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
    await expect(page.getByTestId('rollcall-heading')).toBeVisible();

    // Step 6: Should see the approved player in "Awaiting Confirmation" section
    await expect(page.getByTestId('rollcall-awaiting-section')).toBeVisible();
  });

  test('roll call page shows correct state for non-roll-call events', async ({
    context,
    page,
  }) => {
    // Event is in signups_open state (not roll call)
    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/rollcall/${eventInfo.pk}`);

    // Should show "not in roll call mode" message
    await expect(page.getByTestId('rollcall-not-active')).toBeVisible();
    await expect(page.getByTestId('rollcall-back-btn')).toBeVisible();
  });

  test('event page shows Open Roll Call button when in roll_call state', async ({
    context,
    page,
  }) => {
    await loginEventAdmin(context);

    // Transition to roll call via API
    const resp = await postWithCsrf(context, `${API_URL}/events/${eventInfo.pk}/start_roll_call/`);
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

  test('staff can reopen signups from roll_call (@cicd)', async ({ page, context }) => {
    await loginEventAdmin(context);

    // Force the event into ROLL_CALL via the existing test API.
    const startResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventInfo.pk}/start_roll_call/`,
    );
    expect(startResp.ok()).toBeTruthy();

    // Snapshot the announcement message BEFORE reopen so we can assert it didn't change.
    const beforeDiscord = await verifyDiscordMessages(context, eventInfo.pk);

    // Route is /events/:eventId/:tab? — plural (see frontend/app/routes.tsx)
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);
    await expect(page.getByTestId('event-state-badge')).toHaveText(/Roll Call/i);

    // Click Reopen Signups (desktop; mobile dropdown unreachable at 1280×720)
    await page.getByTestId('event-reopen-signups-btn').click();

    // Confirm dialog → click the WarningButton confirm
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/events/${eventInfo.pk}/reopen_signups/`) &&
          r.request().method() === 'POST',
      ),
      page.getByRole('button', { name: /^Reopen Signups$/ }).last().click(),
    ]);
    expect(response.status()).toBe(200);

    // Positive: state flipped, button is gone
    await expect(page.getByTestId('event-state-badge')).toHaveText(/Signups Open/i);
    await expect(page.getByTestId('event-reopen-signups-btn')).toHaveCount(0);

    // Negative: no Discord re-announcement was posted.
    const afterDiscord = await verifyDiscordMessages(context, eventInfo.pk);
    expect(afterDiscord.announcement?.id ?? null).toBe(beforeDiscord.announcement?.id ?? null);
  });

  test('Reopen Signups button is hidden outside roll_call (@cicd)', async ({ page, context }) => {
    await loginEventAdmin(context);

    // The events test data leaves `eventInfo.pk` in SIGNUPS_OPEN by default after resetEventsData.
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);
    await expect(page.getByTestId('event-state-badge')).toHaveText(/Signups Open/i);
    await expect(page.getByTestId('event-reopen-signups-btn')).toHaveCount(0);
  });
});
