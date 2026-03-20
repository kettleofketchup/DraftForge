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
    expect(discordReady).toBeTruthy();

    // 3. Navigate to the event page
    await visitAndWaitForHydration(page, `/events/${eventId}`);

    // 5. Click the Discord tab
    await page.getByTestId('event-tab-discord').click();

    // 6. Verify Discord state is shown
    // Should see status cards
    await expect(page.getByText('Signup Post')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Announcement')).toBeVisible();

    // Should see activity log entries
    await expect(page.getByText('Activity Log')).toBeVisible();

    // At least one log entry should exist (signup_created or similar)
    await expect(page.locator('[class*="border-l-2"]').first()).toBeVisible({ timeout: 10000 });
  });

  test('Discord tab shows "not configured" when no Discord config', async ({ context, page }) => {
    // Navigate to the existing E2E Signup Event (which has no Discord config)
    await visitAndWaitForHydration(page, `/events/${eventInfo.pk}`);

    // Click Discord tab
    await page.getByTestId('event-tab-discord').click();

    // Should show "not configured" message
    await expect(page.getByText('No Discord integration configured')).toBeVisible({ timeout: 5000 });
  });
});
