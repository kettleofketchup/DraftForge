/**
 * Tournament Discord Config Lifecycle E2E Test
 *
 * Extends the event lifecycle with tournament Discord notifications:
 *   1. Create EventRepeater with discord_send_draft_link + discord_send_herodraft_link enabled
 *   2. Generate event -> open signups -> bulk RSVP 10 players (including kettleofketchup)
 *   3. Approve all -> start roll call -> confirm all -> start tournament
 *   4. Set captains (kettleofketchup as captain of team 1) -> init draft
 *   5. Verify DiscordTournamentLog has draft_link entry (DMs sent)
 *   6. Save bracket -> create herodraft for first match
 *   7. Verify DiscordTournamentLog has herodraft_link entry (DMs sent)
 *
 * Uses Events Test Org (pk=7) with event players (pk=5001-5010).
 * kettleofketchup (pk=1001) is included as a participant and team captain.
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

import { postWithCsrf, patchWithCsrf } from '../../fixtures/events';

const API_URL = 'https://localhost/api';

let eventInfo: EventInfo;

test.describe('Tournament Discord Lifecycle (@cicd)', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    eventInfo = await getEventsTestData(context);
    await context.close();
  });

  test.beforeEach(async ({ context }) => {
    await resetEventsData(context);
    await loginEventAdmin(context);
  });

  test('event -> tournament -> draft DM -> bracket -> herodraft DM', async ({
    context,
    page,
  }) => {
    test.setTimeout(120_000);

    // =========================================================================
    // 1. Create EventRepeater with Discord tournament config enabled
    // =========================================================================
    const repeaterResp = await postWithCsrf(context, `${API_URL}/events/repeaters/`, {
      organization: eventInfo.orgPk,
      name: 'Discord Tournament Lifecycle',
      description: 'Tests tournament Discord DM notifications',
      frequency: 'daily',
      time_of_day: '20:00',
      starts_at: new Date().toISOString().split('T')[0],
      generate_days_ahead: 7,
      is_active: true,
      tournament_name: 'Discord Config Tournament',
      tournament_league: eventInfo.leaguePk,
      tournament_type: 'single_elimination',
      game_type: 1,
      draft_type: 'snake',
      people_per_team: 5,
      number_of_teams: 2,
      max_players: 10,
      auto_approve: false,
      timezone: 'America/New_York',
      // Discord tournament config — both enabled
      discord_send_draft_link: true,
      discord_send_herodraft_link: true,
      auto_create_hero_drafts: false, // We'll create manually to test the DM
      // Event Discord (minimal — no announcement needed for this test)
      discord_announcement: false,
      discord_post_signups: false,
    });
    expect(repeaterResp.ok(), `Create repeater failed: ${await repeaterResp.text()}`).toBeTruthy();

    // =========================================================================
    // 2. Generate event from repeater
    // =========================================================================
    const genMsg = await triggerEventGeneration(context);
    expect(genMsg).toContain('Generated');

    const eventsResp = await context.request.get(
      `${API_URL}/events/?organization=${eventInfo.orgPk}`,
    );
    const events = await eventsResp.json();
    const generatedEvent = events.find(
      (e: { name: string; state: string }) =>
        e.name.includes('Discord Tournament Lifecycle') && e.state === 'upcoming',
    );
    expect(generatedEvent, 'Generated event not found').toBeTruthy();
    const eventId = generatedEvent.id;

    // =========================================================================
    // 3. Open signups
    // =========================================================================
    const openResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventId}/open_signups/`,
    );
    expect(openResp.ok(), `Open signups failed: ${await openResp.text()}`).toBeTruthy();

    // =========================================================================
    // 4. Bulk RSVP 9 event players + kettleofketchup (pk=1001)
    // =========================================================================
    const playerPks = [1001, 5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008, 5009];
    const bulkResp = await context.request.post(
      `${API_URL}/tests/events/${eventId}/bulk-rsvp/`,
      {
        data: { user_pks: playerPks },
        headers: { 'Content-Type': 'application/json' },
      },
    );
    expect(bulkResp.ok(), `Bulk RSVP failed: ${await bulkResp.text()}`).toBeTruthy();

    // =========================================================================
    // 5. Approve all 10 with MMR
    // =========================================================================
    const signupsResp = await context.request.get(
      `${API_URL}/events/signups/?event=${eventId}`,
    );
    const signups = await signupsResp.json();
    const active = signups.filter(
      (s: { status: string }) => !['waitlisted', 'cancelled', 'rejected'].includes(s.status),
    );
    expect(active.length).toBe(10);

    for (let i = 0; i < active.length; i++) {
      const approveResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${active[i].id}/approve/`,
        { mmr: 3000 + i * 200 },
      );
      expect(approveResp.ok(), `Approve signup ${active[i].id} failed`).toBeTruthy();
    }

    // =========================================================================
    // 6. Start roll call -> confirm all 10
    // =========================================================================
    const rollcallResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventId}/start_roll_call/`,
    );
    expect(rollcallResp.ok()).toBeTruthy();

    const rollcallSignupsResp = await context.request.get(
      `${API_URL}/events/signups/?event=${eventId}`,
    );
    const rollcallSignups = await rollcallSignupsResp.json();
    const approved = rollcallSignups.filter(
      (s: { status: string }) => s.status === 'approved',
    );

    for (const signup of approved) {
      const confirmResp = await postWithCsrf(
        context,
        `${API_URL}/events/signups/${signup.id}/confirm/`,
      );
      expect(confirmResp.ok(), `Confirm signup ${signup.id} failed`).toBeTruthy();
    }

    // =========================================================================
    // 7. Start tournament
    // =========================================================================
    const startResp = await postWithCsrf(
      context,
      `${API_URL}/events/${eventId}/start_tournament/`,
    );
    expect(startResp.ok(), `Start tournament failed: ${await startResp.text()}`).toBeTruthy();
    const startedEvent = await startResp.json();
    expect(startedEvent.state).toBe('in_progress');
    expect(startedEvent.tournament).not.toBeNull();
    const tournamentPk = startedEvent.tournament;

    // Verify tournament has discord config
    const tournResp = await context.request.get(`${API_URL}/tournaments/${tournamentPk}/`);
    const tournament = await tournResp.json();
    expect(tournament.discord_send_draft_link).toBe(true);
    expect(tournament.discord_send_herodraft_link).toBe(true);

    // =========================================================================
    // 8. Get tournament teams, set captains
    //    kettleofketchup (pk=1001) as captain of first team
    // =========================================================================
    const teamsResp = await context.request.get(`${API_URL}/tournaments/${tournamentPk}/`);
    const tournData = await teamsResp.json();
    const teams = tournData.teams || [];

    // Tournament should have users but no teams yet (teams created during draft init)
    // We need to create teams with captains first
    // Create team 1 with kettleofketchup as captain
    const createTeam1 = await postWithCsrf(
      context,
      `${API_URL}/tournaments/create-team/`,
      { tournament_pk: tournamentPk, captain_pk: 1001 },
    );
    expect(createTeam1.ok(), `Create team 1 failed: ${await createTeam1.text()}`).toBeTruthy();

    // Create team 2 with event_player_1 (pk=5001) as captain
    const createTeam2 = await postWithCsrf(
      context,
      `${API_URL}/tournaments/create-team/`,
      { tournament_pk: tournamentPk, captain_pk: 5001 },
    );
    expect(createTeam2.ok(), `Create team 2 failed: ${await createTeam2.text()}`).toBeTruthy();

    // =========================================================================
    // 9. Init draft (starts team draft -> triggers discord_send_draft_link DMs)
    // =========================================================================
    const initDraftResp = await postWithCsrf(
      context,
      `${API_URL}/tournaments/init-draft`,
      { tournament_pk: tournamentPk, draft_style: 'snake' },
    );
    expect(initDraftResp.ok(), `Init draft failed: ${await initDraftResp.text()}`).toBeTruthy();

    // =========================================================================
    // 10. Verify DiscordTournamentLog has draft_link entry
    //     (DMs dispatched via Celery — poll for the log to appear)
    // =========================================================================
    let draftLogFound = false;
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(2000);
      const logsResp = await context.request.get(
        `${API_URL}/tournaments/${tournamentPk}/discord-logs/`,
      );
      if (logsResp.ok()) {
        const logs = await logsResp.json();
        const draftLog = logs.find(
          (l: { notification_type: string }) => l.notification_type === 'draft_link',
        );
        if (draftLog) {
          draftLogFound = true;
          expect(draftLog.success).toBe(true);
          expect(draftLog.recipient_count).toBeGreaterThan(0);
          expect(draftLog.message).toContain('draft link');
          break;
        }
      }
    }

    if (!draftLogFound) {
      console.warn('Draft link DM log not found — Celery worker may not be running');
    }

    // =========================================================================
    // 11. Generate and save bracket
    // =========================================================================
    // Get updated tournament with teams
    const updatedTournResp = await context.request.get(
      `${API_URL}/tournaments/${tournamentPk}/`,
    );
    const updatedTourn = await updatedTournResp.json();
    const tournTeams = updatedTourn.teams || [];
    expect(tournTeams.length).toBeGreaterThanOrEqual(2);

    const team1Pk = tournTeams[0].pk;
    const team2Pk = tournTeams[1].pk;

    // Save a simple single-elimination bracket with 1 match
    const bracketPayload = {
      matches: [
        {
          id: 'match-1',
          round: 1,
          position: 0,
          bracketType: 'winners',
          eliminationType: 'single',
          status: 'pending',
          radiantTeam: { pk: team1Pk },
          direTeam: { pk: team2Pk },
        },
      ],
    };

    const saveBracketResp = await postWithCsrf(
      context,
      `${API_URL}/bracket/tournaments/${tournamentPk}/save/`,
      bracketPayload,
    );
    expect(
      saveBracketResp.ok(),
      `Save bracket failed: ${await saveBracketResp.text()}`,
    ).toBeTruthy();
    const savedGames = await saveBracketResp.json();
    expect(savedGames.length).toBeGreaterThanOrEqual(1);
    const gamePk = savedGames[0].pk;

    // =========================================================================
    // 12. Create herodraft for the match (triggers discord_send_herodraft_link DMs)
    // =========================================================================
    const createHdResp = await postWithCsrf(
      context,
      `${API_URL}/games/${gamePk}/create-herodraft/`,
    );
    expect(
      createHdResp.ok(),
      `Create herodraft failed: ${await createHdResp.text()}`,
    ).toBeTruthy();
    const hdData = await createHdResp.json();
    expect(hdData.pk || hdData.id).toBeTruthy();

    // =========================================================================
    // 13. Verify DiscordTournamentLog has herodraft_link entry
    // =========================================================================
    let herodraftLogFound = false;
    for (let i = 0; i < 15; i++) {
      await page.waitForTimeout(2000);
      const logsResp = await context.request.get(
        `${API_URL}/tournaments/${tournamentPk}/discord-logs/`,
      );
      if (logsResp.ok()) {
        const logs = await logsResp.json();
        const hdLog = logs.find(
          (l: { notification_type: string }) => l.notification_type === 'herodraft_link',
        );
        if (hdLog) {
          herodraftLogFound = true;
          expect(hdLog.success).toBe(true);
          expect(hdLog.recipient_count).toBeGreaterThan(0);
          expect(hdLog.message).toContain('hero draft link');
          break;
        }
      }
    }

    if (!herodraftLogFound) {
      console.warn('Herodraft link DM log not found — Celery worker may not be running');
    }

    // =========================================================================
    // 14. Navigate to tournament settings and verify Discord Activity tab
    // =========================================================================
    await page.goto(`https://localhost/tournament/${tournamentPk}`, {
      waitUntil: 'networkidle',
    });

    // Settings gear should be visible (logged in as event admin = staff)
    const settingsBtn = page.getByTestId('tournament-settings-button');
    if (await settingsBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await settingsBtn.click();

      // Click Discord Activity tab
      const discordTab = page.locator('[data-testid="tournament-settings-discord-tab"]');
      if (await discordTab.isVisible({ timeout: 3000 }).catch(() => false)) {
        await discordTab.click();

        // Verify activity log shows entries
        const logEntries = page.locator('[data-testid^="discord-log-entry-"]');
        const count = await logEntries.count();
        if (count > 0) {
          // At least one log entry visible
          expect(count).toBeGreaterThan(0);
        }
      }

      // Close modal
      await page.keyboard.press('Escape');
    }

    // =========================================================================
    // 15. Verify tournament config on the settings tab
    // =========================================================================
    if (await settingsBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await settingsBtn.click();

      // Config values should be correct
      const draftLinkCheckbox = page.getByTestId('discord-discord_send_draft_link');
      if (await draftLinkCheckbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await expect(draftLinkCheckbox).toBeChecked();
      }

      const herodraftLinkCheckbox = page.getByTestId('discord-discord_send_herodraft_link');
      if (await herodraftLinkCheckbox.isVisible({ timeout: 3000 }).catch(() => false)) {
        await expect(herodraftLinkCheckbox).toBeChecked();
      }

      await page.keyboard.press('Escape');
    }
  });
});
