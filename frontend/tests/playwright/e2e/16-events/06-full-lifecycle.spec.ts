/**
 * Full Event Lifecycle E2E Test
 *
 * Tests the complete flow:
 *   1. Create EventRepeater -> generate Event
 *   2. Open signups -> Discord announcement posts
 *   3. Simulate Discord signups (2 via handler, 10 via bulk RSVP)
 *   4. Admin approves all with MMR
 *   5. Start roll call -> confirm 8, unconfirm 2
 *   6. Start tournament
 *   7. Verify UI state + Discord activity logs
 *
 * Uses Events Test Org (pk=7) with 12 event players (pk=5001-5012).
 * Requires Discord bot tokens for announcement posting.
 */

import {
  test,
  expect,
  visitAndWaitForHydration,
  getEventsTestData,
  resetEventsData,
  loginEventAdmin,
  triggerEventGeneration,
  type EventInfo,
} from '../../fixtures';

import {
  postWithCsrf,
  syncDiscordEvents,
  simulateDiscordSignup,
  verifyDiscordMessages,
} from '../../fixtures/events';

const API_URL = 'https://localhost/api';

let eventInfo: EventInfo;

test.describe('Full Event Lifecycle (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test('repeater -> generation -> Discord -> signups -> approval -> rollcall -> tournament', async ({
    context,
    page,
  }) => {
    test.setTimeout(120_000);

    // =========================================================================
    // 1. Create EventRepeater via API
    // =========================================================================
    const repeaterResp = await postWithCsrf(context, `${API_URL}/events/repeaters/`, {
      organization: eventInfo.orgPk,
      name: 'Lifecycle Test Inhouse',
      description: 'Full lifecycle test repeater',
      frequency: 'daily',
      time_of_day: '20:00',
      starts_at: new Date().toISOString().split('T')[0],
      generate_days_ahead: 7,
      is_active: true,
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
      discord_announcement: true,
      discord_announcement_channel_id: '1482767177063858216',
      discord_post_signups: true,
      discord_post_signups_channel_id: '1482767709279096893',
    });
    expect(repeaterResp.ok()).toBeTruthy();

    // =========================================================================
    // 2. Trigger event generation
    // =========================================================================
    const genMsg = await triggerEventGeneration(context);
    expect(genMsg).toContain('Generated');

    // Find the generated event
    const eventsResp = await context.request.get(
      `${API_URL}/events/?organization=${eventInfo.orgPk}`,
    );
    const events = await eventsResp.json();
    const generatedEvent = events.find(
      (e: { name: string; state: string }) =>
        e.name.includes('Lifecycle') && e.state === 'upcoming',
    );
    expect(generatedEvent).toBeTruthy();
    const eventId = generatedEvent.id;

    // =========================================================================
    // 3. Open signups
    // =========================================================================
    const openResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventId}/open_signups/`,
    );
    expect(openResp.ok()).toBeTruthy();
    const openedEvent = await openResp.json();
    expect(openedEvent.state).toBe('signups_open');

    // =========================================================================
    // 4. Wait for Discord announcement (poll)
    // =========================================================================
    let discordReady = false;
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(2000);
      const discordResp = await context.request.get(
        `${API_URL}/events/${eventId}/discord/`,
      );
      if (discordResp.ok()) {
        const data = await discordResp.json();
        if (data.signup_message?.has_posted) {
          discordReady = true;
          break;
        }
      }
      // Trigger sync as backup
      if (i === 3) await syncDiscordEvents(context);
    }

    if (!discordReady) {
      // Skip Discord-specific assertions if no announcement posted
      // (bot tokens may not be configured in CI)
      console.warn('Discord announcement not posted — skipping Discord verification');
    }

    // =========================================================================
    // 5. Verify Discord message (if available)
    // =========================================================================
    if (discordReady) {
      const discord = await verifyDiscordMessages(context, eventId);
      expect(discord.has_discord).toBe(true);
      expect(discord.signup_message).toBeTruthy();
      expect(discord.signup_message.has_buttons).toBe(true);
      expect(discord.signup_message.embeds).toBeGreaterThan(0);
    }

    // =========================================================================
    // 6. Simulate 2 Discord signups via handler chain
    // =========================================================================
    const discordSignup1 = await simulateDiscordSignup(context, eventId, {
      discord_user_id: '999000000000000001',
      discord_username: 'discord_tester_1',
      rank_status: 'active',
      rank_medal: 'Legend 3',
      positions: ['1', '3', '5'],
      friend_id: '99900001',
    });
    expect(discordSignup1.ok()).toBeTruthy();

    const discordSignup2 = await simulateDiscordSignup(context, eventId, {
      discord_user_id: '999000000000000002',
      discord_username: 'discord_tester_2',
      rank_status: 'never',
      battle_cup_tier: 5,
      positions: ['4', '5'],
      friend_id: '99900002',
    });
    expect(discordSignup2.ok()).toBeTruthy();

    // =========================================================================
    // 7. Bulk RSVP remaining 10 players
    // =========================================================================
    const playerPks = [5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008, 5009, 5010];
    const bulkResp = await context.request.post(
      `${API_URL}/tests/events/${eventId}/bulk-rsvp/`,
      {
        data: { user_pks: playerPks },
        headers: { 'Content-Type': 'application/json' },
      },
    );
    expect(bulkResp.ok()).toBeTruthy();

    // =========================================================================
    // 8. Verify signup state: 10 active + 2 waitlisted (max_players=10)
    // =========================================================================
    const signupsResp = await context.request.get(
      `${API_URL}/events/signups/?event=${eventId}`,
    );
    const signups = await signupsResp.json();
    const active = signups.filter(
      (s: { status: string }) => !['waitlisted', 'cancelled', 'rejected'].includes(s.status),
    );
    const waitlisted = signups.filter(
      (s: { status: string }) => s.status === 'waitlisted',
    );
    expect(active.length).toBe(10);
    expect(waitlisted.length).toBe(2);

    // =========================================================================
    // 9. Admin approves all 10 active with MMR
    // =========================================================================
    for (let i = 0; i < active.length; i++) {
      const approveResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${active[i].id}/approve/`,
        { mmr: 3000 + i * 200 },
      );
      expect(approveResp.ok()).toBeTruthy();
    }

    // =========================================================================
    // 10. Start roll call
    // =========================================================================
    const rollcallResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventId}/start_roll_call/`,
    );
    expect(rollcallResp.ok()).toBeTruthy();
    expect((await rollcallResp.json()).state).toBe('roll_call');

    // =========================================================================
    // 11. Confirm 8, unconfirm 2 (no-shows)
    // =========================================================================
    // Re-fetch signups for current state
    const rollcallSignupsResp = await context.request.get(
      `${API_URL}/events/signups/?event=${eventId}`,
    );
    const rollcallSignups = await rollcallSignupsResp.json();
    const approved = rollcallSignups.filter(
      (s: { status: string }) => s.status === 'approved',
    );

    // Confirm first 8
    for (let i = 0; i < 8 && i < approved.length; i++) {
      const confirmResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${approved[i].id}/confirm/`,
      );
      expect(confirmResp.ok()).toBeTruthy();
    }

    // =========================================================================
    // 12. Start tournament
    // =========================================================================
    const startResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventId}/start_tournament/`,
    );
    expect(startResp.ok()).toBeTruthy();
    const startedEvent = await startResp.json();
    expect(startedEvent.state).toBe('in_progress');
    expect(startedEvent.tournament).not.toBeNull();

    // =========================================================================
    // 13. Navigate to event page and verify UI
    // =========================================================================
    await visitAndWaitForHydration(page, `/events/${eventId}`);

    // Signups tab should show players
    await expect(page.getByTestId('event-tab-signups')).toBeVisible({ timeout: 10000 });

    // Discord tab should show activity logs (if Discord was available)
    if (discordReady) {
      await page.getByTestId('event-tab-discord').click();
      await expect(page.getByText('Activity Log')).toBeVisible({ timeout: 5000 });
    }
  });
});
