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

import type { BrowserContext, Page } from '@playwright/test';
import {
  expect,
  getEventsTestData,
  loginEventAdmin,
  loginEventPlayer,
  loginEventPlayer4,
  patchWithCsrf,
  postWithCsrf,
  resetEventsData,
  test,
  verifyDiscordMessages,
  visitAndWaitForHydration,
  type EventInfo,
} from '../../fixtures';
import { API_URL } from '../../fixtures/base-url';

let eventInfo: EventInfo;

// Tests in this file share a single `eventInfo` and mutate event state
// (signups_open → roll_call → finished). With CI's `fullyParallel: true`
// + `--workers=2`, parallel tests would race on the same event PK and
// flake the "Start Roll Call" button visibility. Force serial execution.
/** Two players RSVP, both end up approved, and the admin lands on roll call. */
async function openRollCallWithTwoApproved(
  context: BrowserContext,
  page: Page,
): Promise<{ id: number; status: string }[]> {
  for (const login of [loginEventPlayer, loginEventPlayer4]) {
    await login(context);
    const resp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventInfo.pk}/signup/`,
      { intent: 'rsvp' },
    );
    expect(resp.ok()).toBeTruthy();
  }

  await loginEventAdmin(context);
  const signupsResp = await context.request.get(
    `${API_URL}/events/signups/?event=${eventInfo.pk}`,
  );
  const signups: { id: number; status: string }[] = await signupsResp.json();
  expect(signups.length).toBeGreaterThanOrEqual(2);
  for (const s of signups) {
    if (s.status === 'rsvp' || s.status === 'pending_approval') {
      const resp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${s.id}/approve/`,
      );
      expect(resp.ok()).toBeTruthy();
    }
  }

  await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);
  await page.getByTestId('event-start-rollcall-btn').click();
  await page
    .getByRole('alertdialog')
    .getByRole('button', { name: /start roll call/i })
    .click();
  await page.waitForURL(/\/rollcall\//);
  return signups;
}

test.describe.serial('Roll Call Flow (@cicd)', () => {
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
    const rsvpResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventInfo.pk}/signup/`,
      { intent: 'rsvp' },
    );
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
      const approveResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${signup.id}/approve/`,
      );
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
    const confirmBtn = confirmDialog.getByRole('button', {
      name: /start roll call/i,
    });
    await confirmBtn.click();

    // Step 5: Should navigate to roll call page
    await page.waitForURL(/\/rollcall\//);
    await expect(page.getByTestId('rollcall-heading')).toBeVisible();

    // Step 6: Should see the approved player in "Awaiting Confirmation" section
    await expect(page.getByTestId('rollcall-awaiting-section')).toBeVisible();
  });

  test('removing a confirmed player opens a confirmation dialog', async ({
    context,
    page,
  }) => {
    await loginEventPlayer(context);
    const rsvpResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventInfo.pk}/signup/`,
      { intent: 'rsvp' },
    );
    expect(rsvpResp.ok()).toBeTruthy();

    await loginEventAdmin(context);
    const signupsResp = await context.request.get(
      `${API_URL}/events/signups/?event=${eventInfo.pk}`,
    );
    const signups = await signupsResp.json();
    const signup = signups[0];
    if (signup.status === 'rsvp' || signup.status === 'pending_approval') {
      const approveResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${signup.id}/approve/`,
      );
      expect(approveResp.ok()).toBeTruthy();
    }
    const confirmResp = await postWithCsrf(
      context,
      `${API_URL}/events/signups/${signup.id}/confirm/`,
    );
    expect(confirmResp.ok()).toBeTruthy();

    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);
    await page.getByTestId('event-start-rollcall-btn').click();
    const startConfirm = page.getByRole('alertdialog');
    await startConfirm
      .getByRole('button', { name: /start roll call/i })
      .click();
    await page.waitForURL(/\/rollcall\//);

    // Confirmed player has the new Remove (cancel) button — verify dialog opens.
    const removeBtn = page.getByTestId(`rollcall-cancel-btn-${signup.id}`);
    await expect(removeBtn).toBeVisible();
    await removeBtn.click();
    await expect(page.getByTestId('rollcall-cancel-summary')).toBeVisible();

    // Cancel preserves the confirmed state — no API call should fire.
    await page.getByTestId('rollcall-cancel-dialog-cancel').click();
    await expect(page.getByTestId('rollcall-cancel-summary')).toHaveCount(0);
    await expect(
      page.getByTestId(`rollcall-cancel-btn-${signup.id}`),
    ).toBeVisible();
  });

  test('admin can run roll call from the keyboard', async ({
    context,
    page,
  }) => {
    const signups = await openRollCallWithTwoApproved(context, page);
    await expect(page.getByTestId('rollcall-keyboard-legend')).toBeVisible();

    const awaiting = page
      .getByTestId('rollcall-awaiting-section')
      .locator('xpath=..')
      .locator('[data-rollcall-row]');
    await expect(awaiting).toHaveCount(signups.length);
    const firstId = await awaiting.nth(0).getAttribute('data-rollcall-row');
    const secondId = await awaiting.nth(1).getAttribute('data-rollcall-row');
    const row = (id: string | null) => page.getByTestId(`rollcall-row-${id}`);

    // The cursor starts on the first awaiting player and moves with the arrows.
    await expect(row(firstId)).toHaveAttribute('data-focused', 'true');
    await page.keyboard.press('ArrowDown');
    await expect(row(secondId)).toHaveAttribute('data-focused', 'true');
    await page.keyboard.press('k');
    await expect(row(firstId)).toHaveAttribute('data-focused', 'true');

    // 1 opens Confirm attendance; Enter accepts it and the cursor advances.
    await page.keyboard.press('1');
    await expect(page.getByTestId('rollcall-confirm-summary')).toBeVisible();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('rollcall-confirm-summary')).toHaveCount(0);
    await expect(row(secondId)).toHaveAttribute('data-focused', 'true');
    await expect(
      page.getByTestId(`rollcall-cancel-btn-${firstId}`),
    ).toBeVisible();

    // 2 opens Remove; Backspace backs out without changing anything.
    await page.keyboard.press('2');
    await expect(page.getByTestId('rollcall-reject-summary')).toBeVisible();
    await page.keyboard.press('Backspace');
    await expect(page.getByTestId('rollcall-reject-summary')).toHaveCount(0);
    await expect(row(secondId)).toHaveAttribute('data-focused', 'true');

    // S opens Start Tournament (this event has no minimum).
    await page.keyboard.press('1');
    await page.keyboard.press('Enter');
    await expect(
      page.getByTestId(`rollcall-cancel-btn-${secondId}`),
    ).toBeVisible();
    await expect(page.getByTestId('rollcall-start-btn')).toBeEnabled();
    await page.keyboard.press('s');
    await expect(
      page.getByTestId('rollcall-start-dialog-confirm'),
    ).toBeVisible();
    await page.keyboard.press('Backspace');
    await expect(page.getByTestId('rollcall-start-dialog-confirm')).toHaveCount(
      0,
    );
  });

  test('approved players join the roster only after confirming when the flag is on', async ({
    context,
    page,
  }) => {
    const playerPk = 5001;

    async function rosterPks(): Promise<number[]> {
      const eventResp = await context.request.get(
        `${API_URL}/events/${eventInfo.pk}/`,
      );
      const tournamentPk = (await eventResp.json()).tournament as number | null;
      if (tournamentPk == null) return [];
      const tournResp = await context.request.get(
        `${API_URL}/tournaments/${tournamentPk}/`,
      );
      expect(tournResp.ok()).toBeTruthy();
      return (
        (await tournResp.json()).users as Array<number | { pk: number }>
      ).map((u) => (typeof u === 'number' ? u : u.pk));
    }

    try {
      // Step 1: Admin turns the roster rule on in Edit Event.
      await loginEventAdmin(context);
      await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);
      await page.getByTestId('event-edit-btn').click();
      const modal = page.getByTestId('edit-event-modal');
      await modal.getByRole('tab', { name: /ready check/i }).click();
      await modal.getByTestId('ready-check-toggle').click();
      await modal.getByTestId('form-dialog-submit').click();
      await expect(modal).not.toBeVisible({ timeout: 10000 });
      await expect(page.getByText('Confirm to join roster')).toBeVisible();

      // Step 2: Player signs up and is approved.
      await loginEventPlayer(context);
      const rsvpResp = await postWithCsrf(
        context,
        `${API_URL}/events/${eventInfo.pk}/signup/`,
        {
          intent: 'rsvp',
        },
      );
      expect(rsvpResp.ok()).toBeTruthy();
      await loginEventAdmin(context);
      const signups = await (
        await context.request.get(
          `${API_URL}/events/signups/?event=${eventInfo.pk}`,
        )
      ).json();
      const signup = signups.find((s: { user: number }) => s.user === playerPk);
      if (signup.status === 'rsvp' || signup.status === 'pending_approval') {
        const approveResp = await postWithCsrf(
          context,
          `${API_URL}/events/signups/${signup.id}/approve/`,
        );
        expect(approveResp.ok()).toBeTruthy();
      }

      // Step 3: Approved but unconfirmed, so not on the roster.
      expect(await rosterPks()).not.toContain(playerPk);

      // Step 4: Start roll call and confirm; now on the roster.
      const startResp = await postWithCsrf(
        context,
        `${API_URL}/events/${eventInfo.pk}/start_roll_call/`,
      );
      expect(startResp.ok()).toBeTruthy();
      const confirmResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${signup.id}/confirm/`,
      );
      expect(confirmResp.ok()).toBeTruthy();
      expect(await rosterPks()).toContain(playerPk);
    } finally {
      // The events reset does not restore signup rules; later specs expect the seeded off.
      await loginEventAdmin(context);
      await patchWithCsrf(context, `${API_URL}/events/${eventInfo.pk}/`, {
        roll_call_enabled: false,
      });
    }
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
    const resp = await postWithCsrf(
      context,
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

  test('staff can reopen signups from roll_call (@cicd)', async ({
    page,
    context,
  }) => {
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
    await expect(page.getByTestId('event-state-badge')).toHaveText(
      /Roll Call/i,
    );

    // Click Reopen Signups (desktop; mobile dropdown unreachable at 1280×720)
    await page.getByTestId('event-reopen-signups-btn').click();

    // Confirm dialog → click the WarningButton confirm
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/events/${eventInfo.pk}/reopen_signups/`) &&
          r.request().method() === 'POST',
      ),
      page
        .getByRole('button', { name: /^Reopen Signups$/ })
        .last()
        .click(),
    ]);
    expect(response.status()).toBe(200);

    // Positive: state flipped, button is gone
    await expect(page.getByTestId('event-state-badge')).toHaveText(
      /Signups Open/i,
    );
    await expect(page.getByTestId('event-reopen-signups-btn')).toHaveCount(0);

    // Negative: no Discord re-announcement was posted.
    const afterDiscord = await verifyDiscordMessages(context, eventInfo.pk);
    expect(afterDiscord.announcement?.id ?? null).toBe(
      beforeDiscord.announcement?.id ?? null,
    );
  });

  test('Reopen Signups button is hidden outside roll_call (@cicd)', async ({
    page,
    context,
  }) => {
    await loginEventAdmin(context);

    // The events test data leaves `eventInfo.pk` in SIGNUPS_OPEN by default after resetEventsData.
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);
    await expect(page.getByTestId('event-state-badge')).toHaveText(
      /Signups Open/i,
    );
    await expect(page.getByTestId('event-reopen-signups-btn')).toHaveCount(0);
  });
});
