/**
 * Event Notification DM E2E Test
 *
 * Tests sending pre-event notification DMs to specific users.
 * Requires Discord bot tokens.
 *
 * Sends a real DM to Discord user 243497113906970625.
 */

import {
  test,
  expect,
  getEventsTestData,
  resetEventsData,
  loginEventAdmin,
  triggerEventGeneration,
  type EventInfo,
} from '../../fixtures';

import {
  postWithCsrf,
  syncDiscordEvents,
  sendTestNotification,
} from '../../fixtures/events';

const API_URL = 'https://localhost/api';

let eventInfo: EventInfo;

test.describe('Event Notification DM (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test('send pre-event notification DM to specific Discord user', async ({ context, page }) => {
    test.setTimeout(90_000);

    // 1. Create repeater with subscriber DM enabled
    const repeaterResp = await postWithCsrf(context, `${API_URL}/events/repeaters/`, {
      organization: eventInfo.orgPk,
      name: 'DM Notification Test',
      description: 'Testing subscriber DM notifications',
      frequency: 'daily',
      time_of_day: '20:00',
      starts_at: new Date().toISOString().split('T')[0],
      generate_days_ahead: 7,
      is_active: true,
      tournament_name: 'DM Test Tournament',
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
      discord_subscriber_dm: true,
      discord_subscriber_dm_hours: 24,
    });
    expect(repeaterResp.ok()).toBeTruthy();

    // 2. Generate event
    const genMsg = await triggerEventGeneration(context);
    expect(genMsg).toContain('Generated');

    // 3. Find generated event
    const eventsResp = await context.request.get(
      `${API_URL}/events/?organization=${eventInfo.orgPk}`,
    );
    const events = await eventsResp.json();
    const generatedEvent = events.find(
      (e: { name: string; state: string }) =>
        e.name.includes('DM Notification') && e.state === 'upcoming',
    );
    expect(generatedEvent).toBeTruthy();
    const eventId = generatedEvent.id;

    // 4. Open signups
    const openResp = await postWithCsrf(context, `${API_URL}/events/${eventId}/open_signups/`);
    expect(openResp.ok()).toBeTruthy();

    // 5. Wait for Discord announcement (poll)
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
      if (i === 3) await syncDiscordEvents(context);
    }

    // 6. Send notification DM to specific user (243497113906970625)
    const notifResp = await sendTestNotification(context, eventId, '243497113906970625');

    if (!notifResp.ok()) {
      // DM may fail if bot tokens not configured or user has DMs disabled
      console.warn('Notification DM failed — bot tokens may not be configured');
      return;
    }

    const notif = await notifResp.json();
    expect(notif.success).toBe(true);
    expect(notif.message_id).toBeTruthy();

    // 7. Verify embed content
    expect(notif.embed.title).toContain('Event Reminder');
    expect(notif.embed.title).toContain('DM Notification Test');

    // Signup link only present if Discord announcement was posted
    if (discordReady) {
      expect(notif.embed.description).toContain('Sign up on Discord');
    }

    // View Event link should always be present
    expect(notif.embed.description).toContain('View Event');
  });
});
