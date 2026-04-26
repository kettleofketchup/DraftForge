/**
 * Event Signup Management E2E Tests
 *
 * Tests the full signup lifecycle:
 *   - Bulk signups (12 players, 10 active + 2 waitlisted)
 *   - Admin approval with MMR
 *   - Demoting to waitlist
 *   - Reinstating a demoted player (misclick recovery)
 *   - Promoting from waitlist
 *   - Final state verification on the event page UI
 *
 * Uses the dedicated Events Test Org (pk=7) with 12 event players (pk=5001-5012).
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getEventsTestData,
  resetEventsData,
  loginEventAdmin,
  type EventInfo,
} from '../../fixtures';

import { postWithCsrf } from '../../fixtures/events';
import { waitForAddUserModal, searchAndAddUser, closeAddUserModal } from '../../helpers/add-user';

const API_URL = 'https://localhost/api';

let eventInfo: EventInfo;

test.describe('Event Signup Management (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test('full signup lifecycle: bulk signup, deny, reinstate, promote from waitlist, approve', async ({
    context,
    page,
  }) => {
    // =========================================================================
    // 1. Create event with max_players=10, auto_approve=false
    // =========================================================================
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'Signup Lifecycle Test',
      description: 'Testing full signup management workflow',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'Lifecycle Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      game_type: 1,
      draft_type: 'shuffle',
      people_per_team: 5,
      number_of_teams: 2,
      max_players: 10,
      auto_approve: false,
      timezone: 'America/New_York',
    });
    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();
    const eventId = event.id;

    // =========================================================================
    // 2. Bulk RSVP 12 players (10 active + 2 waitlisted)
    // =========================================================================
    const playerPks = [5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008, 5009, 5010, 5011, 5012];
    const bulkResp = await context.request.post(`${API_URL}/tests/events/${eventId}/bulk-rsvp/`, {
      data: { user_pks: playerPks },
      headers: { 'Content-Type': 'application/json' },
    });
    expect(bulkResp.ok()).toBeTruthy();
    const bulkData = await bulkResp.json();
    expect(bulkData.count).toBe(12);

    // Verify: 10 active (rsvp) + 2 waitlisted
    const signupsResp = await context.request.get(`${API_URL}/events/signups/?event=${eventId}`);
    const signups = await signupsResp.json();
    const activeSignups = signups.filter((s: { status: string }) => s.status === 'rsvp');
    const waitlistedSignups = signups.filter((s: { status: string }) => s.status === 'waitlisted');
    expect(activeSignups.length).toBe(10);
    expect(waitlistedSignups.length).toBe(2);

    // =========================================================================
    // 3. Approve first 7 players with MMR
    // =========================================================================
    for (let i = 0; i < 7; i++) {
      const approveResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${activeSignups[i].id}/approve/`,
        { mmr: 3000 + i * 200 },
      );
      expect(approveResp.ok()).toBeTruthy();
    }

    // =========================================================================
    // 4. Demote 3 players (signups 7, 8, 9) to waitlist
    // =========================================================================
    for (let i = 7; i < 10; i++) {
      const demoteResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${activeSignups[i].id}/demote/`,
      );
      expect(demoteResp.ok()).toBeTruthy();
    }

    // Verify: 7 approved + 5 waitlisted (2 original + 3 demoted)
    const afterDemoteResp = await context.request.get(`${API_URL}/events/signups/?event=${eventId}`);
    const afterDemote = await afterDemoteResp.json();
    expect(afterDemote.filter((s: { status: string }) => s.status === 'approved').length).toBe(7);
    expect(afterDemote.filter((s: { status: string }) => s.status === 'waitlisted').length).toBe(5);

    // =========================================================================
    // 5. Reinstate 1 demoted player (misclick recovery) — re-approve signup 7
    // =========================================================================
    const reinstateTarget = afterDemote.find(
      (s: { user: number; status: string }) =>
        s.user === activeSignups[7].user && s.status === 'waitlisted',
    );
    expect(reinstateTarget).toBeTruthy();
    const reapproveResp = await postWithCsrf(
      context,
      `${API_URL}/events/signups/${reinstateTarget.id}/approve/`,
      { mmr: 3700 },
    );
    expect(reapproveResp.ok()).toBeTruthy();
    expect((await reapproveResp.json()).status).toBe('approved');

    // =========================================================================
    // 6. Promote 2 from waitlist and approve with MMR
    // =========================================================================
    const afterReinstateResp = await context.request.get(`${API_URL}/events/signups/?event=${eventId}`);
    const currentWaitlist = (await afterReinstateResp.json())
      .filter((s: { status: string }) => s.status === 'waitlisted')
      .sort((a: { waitlist_position: number }, b: { waitlist_position: number }) =>
        (a.waitlist_position ?? 999) - (b.waitlist_position ?? 999),
      );

    for (let i = 0; i < 2 && i < currentWaitlist.length; i++) {
      const promoteResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${currentWaitlist[i].id}/approve/`,
        { mmr: 2500 + i * 300 },
      );
      expect(promoteResp.ok()).toBeTruthy();
      expect((await promoteResp.json()).status).toBe('approved');
    }

    // =========================================================================
    // 7. Verify pre-rollcall state: 10 approved, 2 waitlisted
    // =========================================================================
    const preRollcallResp = await context.request.get(`${API_URL}/events/signups/?event=${eventId}`);
    const preRollcall = await preRollcallResp.json();
    const approvedSignups = preRollcall.filter((s: { status: string }) => s.status === 'approved');
    expect(approvedSignups.length).toBe(10);
    expect(preRollcall.filter((s: { status: string }) => s.status === 'waitlisted').length).toBe(2);

    // =========================================================================
    // 8. Start Roll Call
    // =========================================================================
    const rollcallResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventId}/start_roll_call/`,
    );
    expect(rollcallResp.ok()).toBeTruthy();
    const rollcallEvent = await rollcallResp.json();
    expect(rollcallEvent.state).toBe('roll_call');

    // =========================================================================
    // 9. During roll call: unconfirm 3, then re-confirm 1 (misclick)
    // =========================================================================
    // Confirm first 7
    for (let i = 0; i < 7; i++) {
      const confirmResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${approvedSignups[i].id}/confirm/`,
      );
      expect(confirmResp.ok()).toBeTruthy();
    }

    // Unconfirm 3 of them (simulating roll call no-shows)
    for (let i = 4; i < 7; i++) {
      const unconfirmResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${approvedSignups[i].id}/unconfirm/`,
      );
      expect(unconfirmResp.ok()).toBeTruthy();
    }

    // Re-confirm 1 (misclick recovery — player showed up late)
    const reconfirmResp = await postWithCsrf(
      context,
      `${API_URL}/events/signups/${approvedSignups[4].id}/confirm/`,
    );
    expect(reconfirmResp.ok()).toBeTruthy();
    expect((await reconfirmResp.json()).status).toBe('confirmed');

    // Confirm remaining 3 approved players (indices 7-9)
    for (let i = 7; i < 10; i++) {
      const confirmResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${approvedSignups[i].id}/confirm/`,
      );
      expect(confirmResp.ok()).toBeTruthy();
    }

    // =========================================================================
    // 10. Verify roll call state: 8 confirmed, 2 approved (unconfirmed)
    // =========================================================================
    const rollcallSignupsResp = await context.request.get(`${API_URL}/events/signups/?event=${eventId}`);
    const rollcallSignups = await rollcallSignupsResp.json();
    const confirmed = rollcallSignups.filter((s: { status: string }) => s.status === 'confirmed');
    const stillApproved = rollcallSignups.filter((s: { status: string }) => s.status === 'approved');
    expect(confirmed.length).toBe(8);
    expect(stillApproved.length).toBe(2);

    // =========================================================================
    // 11. Start Tournament
    // =========================================================================
    const startResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventId}/start_tournament/`,
    );
    expect(startResp.ok()).toBeTruthy();
    const startedEvent = await startResp.json();
    expect(startedEvent.state).toBe('in_progress');
    // Tournament should have been created
    expect(startedEvent.tournament).not.toBeNull();

    // =========================================================================
    // 12. Navigate to event page and verify UI
    // =========================================================================
    await visitAndWaitForHydration(page, `/events/${eventId}`);

    // Signups tab should show confirmed + approved players
    await expect(page.getByTestId('event-tab-signups')).toContainText('10');

    // Waitlist tab should show 2
    await expect(page.getByTestId('event-tab-waitlist')).toContainText('2');
  });

  test('staff can admin-add a user during roll_call (@cicd)', async ({ page, context }) => {
    // Force the event into ROLL_CALL via the existing test API.
    const startResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventInfo.pk}/start_roll_call/`,
    );
    expect(startResp.ok()).toBeTruthy();

    // Route is /events/:eventId/:tab? — plural; navigate directly to the signups tab.
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}/signups`);
    await expect(page.getByTestId('event-state-badge')).toHaveText(/Roll Call/i);

    // Open AddUserModal via canonical testid (gate widened to ROLL_CALL in Task 16).
    await page.getByTestId('admin-add-signup-btn').click();
    await waitForAddUserModal(page);

    // Search for a seeded user, click their add button, and capture the admin-signup POST.
    const targetUsername = 'event_player_1';
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/events/${eventInfo.pk}/admin-signup/`) &&
          r.request().method() === 'POST',
      ),
      searchAndAddUser(page, targetUsername),
    ]);
    expect(response.status()).toBe(201);

    // Close the modal so the underlying signup list is unobscured, then assert
    // the newly added user (rendered by nickname in UserEventStrip) appears.
    await closeAddUserModal(page);
    await expect(page.getByText('EventPlayer1').first()).toBeVisible();
  });
});
