/**
 * Discord Integration E2E Tests
 *
 * Tests that creating an event with Discord config triggers Discord messages
 * and the Discord tab shows the activity log.
 *
 * Uses the dedicated Events Test Org (pk=7) infrastructure.
 * Requires Discord bot token and test channels to be configured.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getEventsTestData,
  resetEventsData,
  loginEventAdmin,
  loginEventPlayer,
  loginEventPlayer4,
  setApprovedMmr,
  type EventInfo,
} from '../../fixtures';

import { postWithCsrf, syncDiscordEvents } from '../../fixtures/events';

const API_URL = 'https://localhost/api';

let eventInfo: EventInfo;

test.describe('Events - Discord Integration (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test('creating event with Discord config generates Discord posts', async ({ context, page }) => {
    test.setTimeout(90_000);
    // 1. Create event via API with Discord config
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'Discord E2E Test Event',
      description: 'Testing Discord integration end-to-end',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(), // Tomorrow
      tournament_name: 'Discord E2E Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      game_type: 1, // Dota 2
      draft_type: 'shuffle',
      people_per_team: 5,
      number_of_teams: 2,
      max_players: 10,
      auto_approve: true,
      timezone: 'America/New_York',
      // Discord config
      discord_announcement: true,
      discord_announcement_channel_id: '1482767177063858216',
      discord_post_signups: true,
      discord_post_signups_channel_id: '1482767709279096893',
    });

    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();
    const eventId = event.id;

    // 2. Wait for Celery worker to process send_event_announcement
    // Poll the Discord state API until it shows up (max 30s)
    let discordReady = false;
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(2000);
      const discordResp = await context.request.get(`${API_URL}/events/${eventId}/discord/`);
      if (discordResp.ok()) {
        const data = await discordResp.json();
        if (data.signup_message?.has_posted) {
          discordReady = true;
          break;
        }
      }
      // Trigger sync as backup on iteration 5
      if (i === 5) {
        await syncDiscordEvents(context);
      }
    }
    if (!discordReady) {
      // CI may not have Discord bot tokens — skip Discord-specific assertions
      console.warn('Discord announcement not posted (bot tokens may not be configured). Skipping.');
      return;
    }

    // 3. Navigate to the event page
    await visitAndWaitForHydration(page, `/events/${eventId}`);

    // 5. Click the Discord tab
    await page.getByTestId('event-tab-discord').click();

    // 6. Verify Discord state is shown
    // Status cards are always visible above sub-tabs
    await expect(page.getByText('Signup Post').first()).toBeVisible({ timeout: 10000 });

    // Switch to Activity Log sub-tab to see log entries
    await page.getByTestId('discord-subtab-activity').click();

    // At least one log entry should exist
    await expect(page.locator('[data-testid^="discord-log-entry-"]').first()).toBeVisible({ timeout: 10000 });
  });

  test('signup updates Discord post and shows in activity log', async ({ context, page }) => {
    test.setTimeout(90_000);
    // 1. Create event with Discord config as admin
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'Signup Notification Test',
      description: 'Testing signup updates on Discord',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'Signup Notif Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      game_type: 1,
      draft_type: 'shuffle',
      people_per_team: 5,
      number_of_teams: 2,
      max_players: 10,
      auto_approve: true,
      timezone: 'America/New_York',
      discord_announcement: true,
      discord_announcement_channel_id: '1482767177063858216',
      discord_post_signups: true,
      discord_post_signups_channel_id: '1482767709279096893',
      discord_sync_signups: true,
    });
    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();
    const eventId = event.id;

    // 2. Wait for Discord posts
    let discordReady = false;
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(2000);
      const resp = await context.request.get(`${API_URL}/events/${eventId}/discord/`);
      if (resp.ok()) {
        const data = await resp.json();
        if (data.signup_message?.has_posted) {
          discordReady = true;
          break;
        }
      }
      if (i === 5) await syncDiscordEvents(context);
    }
    if (!discordReady) {
      console.warn('Discord announcement not posted. Skipping signup update test.');
      return;
    }

    // 3. Sign up as a player
    await loginEventPlayer(context);
    const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${eventId}/signup/`, { intent: 'rsvp' });
    expect(rsvpResp.ok()).toBeTruthy();

    // 4. Trigger sync to update the Discord signup post
    await loginEventAdmin(context);
    await syncDiscordEvents(context);
    // Give Celery worker time to process
    await page.waitForTimeout(3000);

    // 5. Navigate to event page and check Discord tab
    await visitAndWaitForHydration(page, `/events/${eventId}`);
    await page.getByTestId('event-tab-discord').click();

    // Switch to Activity Log sub-tab
    await page.getByTestId('discord-subtab-activity').click();
    const logEntries = page.locator('[data-testid^="discord-log-entry-"]');
    await expect(logEntries.first()).toBeVisible({ timeout: 10000 });

    // Status card shows signup post as posted
    await expect(page.getByText('Signup Post').first()).toBeVisible();
  });

  test('event with screenshot config fields persists settings', async ({ context, page }) => {
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'Screenshot Config Test',
      description: 'Testing screenshot config fields',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'Screenshot Config Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      game_type: 1,
      draft_type: 'shuffle',
      people_per_team: 5,
      number_of_teams: 2,
      max_players: 10,
      auto_approve: true,
      timezone: 'America/New_York',
      discord_announcement: true,
      discord_announcement_channel_id: '1482767177063858216',
      discord_post_signups: true,
      discord_post_signups_channel_id: '1482767709279096893',
      discord_require_rank_screenshot: true,
      discord_require_battlecup_screenshot: true,
      min_mmr: 3000,
    });

    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();

    // Verify fields persisted
    expect(event.discord_require_rank_screenshot).toBe(true);
    expect(event.discord_require_battlecup_screenshot).toBe(true);
    expect(event.min_mmr).toBe(3000);
  });

  test('approve signup with MMR sets org user MMR via API', async ({ context }) => {
    // Create event with open signups
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'MMR Approval Test',
      description: 'Testing MMR approval',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'MMR Test Tournament',
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

    // Login as player and RSVP
    await loginEventPlayer(context);
    const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${event.id}/signup/`, { intent: 'rsvp' });
    expect(rsvpResp.ok()).toBeTruthy();
    const signup = await rsvpResp.json();

    // Login as admin and approve with MMR
    await loginEventAdmin(context);
    const approveResp = await postWithCsrf(
      context,
      `${API_URL}/events/signups/${signup.id}/approve/`,
      { mmr: 3500 },
    );
    expect(approveResp.ok()).toBeTruthy();
    const approved = await approveResp.json();
    expect(approved.status).toBe('approved');
  });

  test('admin can approve signup with MMR via approval modal UI', async ({ context, page }) => {
    // 1. Create event with auto_approve=false (manual approval required)
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'MMR Approval E2E Test',
      description: 'Testing admin MMR approval workflow',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'MMR Approval Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      game_type: 1, // Dota 2
      draft_type: 'shuffle',
      people_per_team: 5,
      number_of_teams: 2,
      max_players: 10,
      auto_approve: false,
      timezone: 'America/New_York',
    });
    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();

    // 2. Login as player and RSVP
    await loginEventPlayer(context);
    const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${event.id}/signup/`, { intent: 'rsvp' });
    expect(rsvpResp.ok()).toBeTruthy();
    const signup = await rsvpResp.json();

    // Clear event_player_1's prior approved MMR so the test exercises the
    // self-report → range fallback (populate seeds an org-user MMR of 3500
    // by default; 0 makes the serializer's `if org_user.mmr` falsy and
    // surfaces self_report as the default).
    await setApprovedMmr(context, eventInfo.orgPk, 5001, 0);

    // 3. Login as admin and navigate to event
    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/events/${event.id}`);

    // 4. Click Signups tab
    await page.getByTestId('event-tab-signups').click();

    // 5. Verify player is in the signups list
    await expect(page.getByTestId(`event-signup-row-${signup.id}`)).toBeVisible({ timeout: 10000 });

    // 6. Click the Approve button — opens MMR approval modal (Dota 2 event)
    await page.getByTestId(`approve-signup-${signup.id}`).click();

    // 7. Verify modal opened with player name in the dialog title
    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });
    await expect(dialog.getByText('EventPlayer1')).toBeVisible();

    // 8. Verify profile data is displayed (player 1 has Legend 3 medal from populate)
    await expect(dialog.getByText('Legend 3')).toBeVisible();
    await expect(dialog.getByText('3,200')).toBeVisible(); // Self-reported MMR

    // 8b. Verify the new Rank Signals card renders all four signal rows
    await expect(dialog.getByTestId('rank-signals')).toBeVisible();
    await expect(dialog.getByTestId('rank-signals-self-report')).toContainText('3,200');
    await expect(dialog.getByTestId('rank-signals-medal')).toContainText('Legend 3');
    await expect(dialog.getByTestId('rank-signals-medal')).toContainText('3,388');
    await expect(dialog.getByTestId('rank-signals-medal')).toContainText('3,542');
    await expect(dialog.getByTestId('rank-signals-battle-cup')).toContainText('—');
    await expect(dialog.getByTestId('suggested-range-helper')).toContainText(
      '3,388–3,542',
    );
    await expect(dialog.getByTestId('suggested-range-helper')).toContainText(
      'from medal',
    );

    // Positions row must not show a "1" rank number — DotaProfile booleans aren't ranked preferences.
    const positionsRow = dialog.getByTestId('rank-signals-positions');
    await expect(positionsRow).toBeVisible();
    // event_player_1 has pos_1, pos_3, pos_5 — three role icons should render.
    // None of them should display "1" inside (the rank number Badge is suppressed).
    await expect(positionsRow).not.toContainText(/^1\s*1\s*1$/);

    // 8c. The MMR input should pre-fill with self-report (3200) since
    // event_player_1 has no prior approved MMR. Use the new data-testid
    // (mmr-input) instead of the [type=number] CSS locator the prior version
    // of this test used.
    await expect(dialog.getByTestId('mmr-input')).toHaveValue('3200');

    // 9. Check the MMR input exists and has a default value
    const mmrInput = dialog.locator('input[type="number"]');
    await expect(mmrInput).toBeVisible();

    // 10. Clear and set MMR to 3500
    await mmrInput.fill('3500');

    // 11. Click Approve — opens the confirmation alert-dialog (always shown
    // before submission, so admins see a recap + the value being committed).
    await dialog.getByTestId('mmr-modal-approve').click();

    // 12. Confirm in the alert-dialog (role="alertdialog", separate from the
    // main modal's role="dialog").
    const confirmBox = page.locator('[role="alertdialog"]');
    await expect(confirmBox).toBeVisible({ timeout: 5000 });
    await confirmBox.getByTestId('mmr-confirm-approve').click();

    // 13. Verify the modal closed and the signup status changed to approved.
    // The success toast also contains "Approved", so use .first() to pick the
    // signup status badge (Playwright strict mode flags the duplicate match).
    await expect(dialog).not.toBeVisible({ timeout: 10000 });
    await expect(page.getByText('approved').first()).toBeVisible({ timeout: 10000 });
  });

  test('approval modal — self-reported MMR pre-fills input over prior-approved', async ({
    context,
    page,
  }) => {
    // Setup: create a fresh Dota event, RSVP as player 1, then set their
    // OrgUser.mmr=2400 BEFORE the admin opens the approval modal. Player 1
    // also has self_report=3200 from populate, so the autofill must pick the
    // self-report (player just told us a number > admin gates the override).
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'Self-Report Precedence Event',
      description: 'Tests self-reported MMR pre-fills over prior',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'Self-Report MMR Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      timezone: 'America/New_York',
    });
    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();

    await loginEventPlayer(context);
    const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${event.id}/signup/`, { intent: "rsvp" });
    expect(rsvpResp.ok()).toBeTruthy();
    const signup = await rsvpResp.json();

    // Set prior approved MMR before opening modal
    await setApprovedMmr(context, eventInfo.orgPk, 5001, 2400);

    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/events/${event.id}`);
    await page.getByTestId('event-tab-signups').click();
    await expect(page.getByTestId(`event-signup-row-${signup.id}`)).toBeVisible({ timeout: 10000 });
    await page.getByTestId(`approve-signup-${signup.id}`).click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Prior-approved row still surfaces the stored 2,400; per-star medal range
    // shows alongside.
    await expect(dialog.getByTestId('rank-signals-prior-mmr')).toContainText('2,400');
    await expect(dialog.getByTestId('rank-signals-medal')).toContainText('Legend 3');
    await expect(dialog.getByTestId('suggested-range-helper')).toContainText(
      '3,388–3,542',
    );

    // Input pre-fills with self-report (3,200), not prior approved (2,400).
    await expect(dialog.getByTestId('mmr-input')).toHaveValue('3200');

    await dialog.getByTestId('mmr-modal-close').click();
  });

  test('approval modal — battle cup tier path shows BC range, no medal', async ({
    context,
    page,
  }) => {
    // event_player_4 has rank_status="never" + battle_cup_tier=5 from populate.
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'Battle Cup Path Event',
      description: 'Tests battle-cup MMR range surface',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'BC Path Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      timezone: 'America/New_York',
    });
    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();

    await loginEventPlayer4(context);
    const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${event.id}/signup/`, { intent: "rsvp" });
    expect(rsvpResp.ok()).toBeTruthy();
    const signup = await rsvpResp.json();

    // Clear event_player_4's prior approved MMR so the test exercises the
    // battle-cup midpoint fallback rather than the populate-seeded prior.
    await setApprovedMmr(context, eventInfo.orgPk, 5004, 0);

    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/events/${event.id}`);
    await page.getByTestId('event-tab-signups').click();
    await expect(page.getByTestId(`event-signup-row-${signup.id}`)).toBeVisible({ timeout: 10000 });
    await page.getByTestId(`approve-signup-${signup.id}`).click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Medal row is em-dash (no medal), BC row shows Tier 5.
    await expect(dialog.getByTestId('rank-signals-medal')).toContainText('—');
    await expect(dialog.getByTestId('rank-signals-battle-cup')).toContainText('Tier 5');

    // Helper text reflects BC range 3,000–4,000 with source label.
    await expect(dialog.getByTestId('suggested-range-helper')).toContainText(
      '3,000–4,000',
    );
    await expect(dialog.getByTestId('suggested-range-helper')).toContainText(
      'from battle cup',
    );

    // Input pre-fills with BC midpoint (3,500) since no prior + no self-report.
    await expect(dialog.getByTestId('mmr-input')).toHaveValue('3500');

    await dialog.getByTestId('mmr-modal-close').click();
  });

  test('approval modal — large change vs prior surfaces warning + alert-dialog confirm', async ({
    context,
    page,
  }) => {
    // Player 1 self-reports 3,200; we set prior approved = 2,400. Autofill
    // lands on the self-report (3,200) → that's already a 33% jump from the
    // prior, so the in-modal delta strip switches to amber + warning copy.
    // Clicking Approve opens an alert-dialog with the "Confirm large MMR
    // change" / "Approve anyway" copy. Cancelling does NOT submit; confirming
    // does.
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'Large Change Confirm Event',
      description: 'Tests 20% large-change confirm dialog',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'Large Change Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      timezone: 'America/New_York',
    });
    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();

    await loginEventPlayer(context);
    const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${event.id}/signup/`, { intent: "rsvp" });
    expect(rsvpResp.ok()).toBeTruthy();
    const signup = await rsvpResp.json();

    // 33% delta scenario: prior 2,400 vs autofill 3,200 (self-report).
    await setApprovedMmr(context, eventInfo.orgPk, 5001, 2400);

    await loginEventAdmin(context);
    await visitAndWaitForHydration(page, `/events/${event.id}`);
    await page.getByTestId('event-tab-signups').click();
    await expect(page.getByTestId(`event-signup-row-${signup.id}`)).toBeVisible({ timeout: 10000 });
    await page.getByTestId(`approve-signup-${signup.id}`).click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible({ timeout: 5000 });
    const mmrInput = dialog.getByTestId('mmr-input');

    // Autofill = 3,200 (self-report wins over prior).
    await expect(mmrInput).toHaveValue('3200');

    // Delta strip is visible at modal open with prior → autofill diff.
    await expect(dialog.getByTestId('mmr-delta')).toBeVisible();
    await expect(dialog.getByTestId('mmr-delta-text')).toContainText('2,400 → 3,200');
    await expect(dialog.getByTestId('mmr-delta-text')).toContainText('33%');

    // Click Approve → alert-dialog (separate role) confirms with warning copy.
    await dialog.getByTestId('mmr-modal-approve').click();
    const confirmBox = page.locator('[role="alertdialog"]');
    await expect(confirmBox).toBeVisible({ timeout: 5000 });
    await expect(confirmBox).toContainText('Confirm large MMR change');
    await expect(confirmBox).toContainText('3,200 MMR');
    await expect(confirmBox).toContainText('2,400');
    await expect(confirmBox).toContainText('+800');
    await expect(confirmBox).toContainText('33%');

    // Cancel: alert-dialog closes, main modal stays, no approval submitted.
    await confirmBox.getByTestId('mmr-confirm-cancel').click();
    await expect(confirmBox).not.toBeVisible({ timeout: 5000 });
    await expect(dialog).toBeVisible();

    // Type a within-threshold value (3,000 → +25% which is still over, so
    // pick 2,800 → ~17%). Delta strip switches to neutral, no warning copy.
    await mmrInput.fill('2800');
    await expect(dialog.getByTestId('mmr-delta-text')).toContainText('17%');

    // Approving the small-change value: alert-dialog uses the default
    // (non-warning) variant.
    await dialog.getByTestId('mmr-modal-approve').click();
    await expect(confirmBox).toBeVisible({ timeout: 5000 });
    await expect(confirmBox).toContainText('Confirm approval');
    await expect(confirmBox).not.toContainText('Confirm large MMR change');

    // Confirm — submission proceeds and main modal closes.
    await confirmBox.getByTestId('mmr-confirm-approve').click();
    await expect(dialog).not.toBeVisible({ timeout: 10000 });
  });

  test('PlayerModal edit on event page persists org-scoped change without orgUserPk error', async ({
    context,
    page,
  }) => {
    // Ensures the fix at PlayerModal.tsx for the bug
    // "Org scope requires user.orgUserPk" — admin opens a signup user's
    // PlayerModal, clicks Edit, saves, and the PATCH must succeed.
    //
    // Uses the site superuser (pk=1001) for this test because PlayerModal's
    // edit button is only rendered when currentUser.is_staff or is_superuser.
    // EventAdmin (pk=5000) is an org admin without site-level staff status.
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'Player Modal Edit Event',
      description: 'Tests org-scoped edit from PlayerModal',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'PM Edit Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      timezone: 'America/New_York',
    });
    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();

    await loginEventPlayer(context);
    const rsvpResp = await postWithCsrf(context, `${API_URL}/events/${event.id}/signup/`, { intent: "rsvp" });
    expect(rsvpResp.ok()).toBeTruthy();
    const signup = await rsvpResp.json();

    // Login as the site superuser (is_superuser=True) so PlayerModal shows
    // the edit button (canEdit = is_staff || is_superuser).
    const loginResp = await context.request.post(`${API_URL}/tests/login-as/`, {
      data: { user_pk: 1001 },
      headers: { 'Content-Type': 'application/json' },
    });
    expect(loginResp.ok()).toBeTruthy();

    // Wait for org users to load — this populates UserCacheStore.entities[5001].orgData[7]
    // which our PlayerModal fix uses to look up orgUserPk for the org-scoped PATCH.
    const orgUsersLoaded = page.waitForResponse(
      (resp) => resp.request().method() === 'GET' && /\/organizations\/\d+\/users\//.test(resp.url()),
      { timeout: 15000 },
    );
    await visitAndWaitForHydration(page, `/events/${event.id}`);
    await orgUsersLoaded;

    await page.getByTestId('event-tab-signups').click();
    const signupRow = page.getByTestId(`event-signup-row-${signup.id}`);
    await expect(signupRow).toBeVisible({ timeout: 10000 });

    // Open the PlayerModal by clicking the user name in the signup row.
    await signupRow.getByText('EventPlayer1').click();

    // Click the edit-user pencil button inside PlayerModal.
    await page.getByTestId('edit-user-btn').click();

    // The edit modal opens — change the nickname and save.
    const editDialog = page.getByTestId('edit-user-modal');
    await expect(editDialog).toBeVisible({ timeout: 5000 });
    const nicknameInput = editDialog.getByTestId('edit-user-nickname');
    await nicknameInput.fill('EventPlayer1-edited');

    // Click Save Changes — with the orgUserPk fix, dispatchPatch receives a
    // User instance that has orgUserPk populated from the cache, so the org-
    // scoped PATCH succeeds. Without the fix, dispatchPatch throws
    // "Org scope requires user.orgUserPk" and a toast.error is shown.
    await editDialog.getByRole('button', { name: 'Save Changes' }).click();

    // The dialog should close on success.
    await expect(editDialog).not.toBeVisible({ timeout: 10000 });

    // No error toast about orgUserPk — the save succeeded.
    await expect(page.getByText('Org scope requires user.orgUserPk')).not.toBeVisible();
  });

  test('Discord tab shows empty state for fresh event', async ({ context, page }) => {
    // Create a fresh event — DiscordEvent auto-created since org has discord_server_id
    const createResp = await postWithCsrf(context, `${API_URL}/events/?open_signups=true`, {
      organization: eventInfo.orgPk,
      name: 'No Discord Config Event',
      description: 'Event without Discord integration',
      scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      tournament_name: 'No Discord Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      game_type: 1,
      draft_type: 'shuffle',
      people_per_team: 5,
      number_of_teams: 2,
      timezone: 'America/New_York',
    });
    expect(createResp.ok()).toBeTruthy();
    const event = await createResp.json();

    await visitAndWaitForHydration(page, `/events/${event.id}`);
    await page.getByTestId('event-tab-discord').click();
    // Discord tab should load with task schedule (DiscordEvent auto-created since org has discord_server_id)
    await expect(page.getByTestId('discord-subtab-schedule')).toBeVisible({ timeout: 5000 });
  });
});
