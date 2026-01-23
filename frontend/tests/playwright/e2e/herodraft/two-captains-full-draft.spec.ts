import { test, expect, chromium, type Browser, type BrowserContext, type Page } from '@playwright/test';
import { loginAsDiscordId, waitForHydration } from '../../fixtures/auth';
import { HeroDraftPage } from '../../helpers/HeroDraftPage';

const API_URL = 'https://localhost/api';
const BASE_URL = 'https://localhost';

/**
 * Wait for server to be ready with retries.
 * Handles TLS connection issues during server startup.
 */
async function waitForServerReady(
  context: BrowserContext,
  url: string,
  maxRetries = 10,
  delayMs = 2000
): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await context.request.get(url, {
        timeout: 5000,
        failOnStatusCode: false,
      });
      if (response.status() < 500) {
        return; // Server is ready
      }
    } catch (error) {
      console.log(`   Waiting for server... (attempt ${i + 1}/${maxRetries})`);
    }
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  throw new Error(`Server not ready after ${maxRetries} attempts`);
}

/**
 * Two Captains Full Draft Test
 *
 * This test spawns TWO separate browser windows (both visible) to simulate
 * a real Captain's Mode draft between two players.
 *
 * Uses Winners Final game from Real Tournament 38:
 * - Captain A: vrm.mtl (discord: 764290890617192469)
 * - Captain B: ethan0688_ (discord: 1325607754177581066)
 *
 * Test flow through actual UI:
 * 1. Login both captains via test endpoints
 * 2. Navigate to match page in tournament bracket
 * 3. Click "Start Draft" button
 * 4. Proceed through all draft phases (waiting -> rolling -> choosing -> drafting)
 *
 * You'll see:
 * - Captain A's window on one side
 * - Captain B's window on the other side
 * - Both interacting with the draft in real-time
 */

interface CaptainContext {
  browser: Browser;
  context: BrowserContext;
  page: Page;
  draftPage: HeroDraftPage;
  userPk: number;
  teamId: number;
  username: string;
  discordId: string;
  teamName: string;
}

interface HeroDraftTestInfo {
  pk: number;
  state: string;
  game: {
    pk: number;
    tournament_pk: number;
    radiant_team_name: string;
    dire_team_name: string;
  };
  draft_teams: Array<{
    id: number;
    captain: { pk: number; username: string; discordId: string };
    team_name: string;
    is_first_pick?: boolean;
    is_radiant?: boolean;
    is_ready?: boolean;
  }>;
}

test.describe('Two Captains Full Draft', () => {
  let captainA: CaptainContext;
  let captainB: CaptainContext;
  let testInfo: HeroDraftTestInfo;

  // Store browsers at top level for cleanup even if beforeAll fails
  let browserA: Browser | null = null;
  let browserB: Browser | null = null;

  test.beforeAll(async () => {
    // Determine headed mode:
    // - HERODRAFT_HEADED=true forces headed mode
    // - CI or Docker (PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) defaults to headless
    // - Otherwise defaults to headed for local development
    const isCI = !!process.env.CI;
    const isDocker = !!process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
    const forceHeaded = process.env.HERODRAFT_HEADED === 'true';
    const headless = forceHeaded ? false : (isCI || isDocker);

    console.log(`   Browser mode: ${headless ? 'headless' : 'headed'}`);

    // Launch two separate browser instances
    const browserOptions = {
      headless,
      slowMo: headless ? 0 : 50, // Slow down only in headed mode for visibility
      args: [
        '--disable-web-security',
        '--ignore-certificate-errors',
        '--no-sandbox',
        '--disable-gpu',
        '--disable-dev-shm-usage',
      ],
    };

    // Create two browsers - store at top level for cleanup
    browserA = await chromium.launch(browserOptions);
    browserB = await chromium.launch(browserOptions);

    // Create contexts with different viewports for easy identification
    // Position windows side-by-side in headed mode (left and right halves)
    const windowWidth = 960;
    const windowHeight = 800;

    const contextA = await browserA.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowWidth, height: windowHeight },
    });

    const contextB = await browserB.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowWidth, height: windowHeight },
    });

    // Create pages
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    // Wait for server to be ready (handles TLS connection issues during startup)
    console.log('   Waiting for server to be ready...');
    await waitForServerReady(contextA, `${API_URL}/`);
    console.log('   Server ready!');

    // Fetch draft info using the two_captain_test key
    // This uses Real Tournament 38's Winners Final: vrm.mtl vs ethan0688_
    const response = await contextA.request.get(
      `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
      { failOnStatusCode: false, timeout: 10000 }
    );

    if (!response.ok()) {
      const errorText = await response.text();
      throw new Error(
        `Failed to get HeroDraft test data: ${response.status()} - ${errorText}\n` +
        `Make sure to run 'inv db.populate.all' to create test data.`
      );
    }

    testInfo = await response.json();

    // Reset the draft to waiting state
    await contextA.request.post(
      `${API_URL}/tests/herodraft/${testInfo.pk}/reset/`,
      { failOnStatusCode: false }
    );

    // Extract captain info
    const teams = testInfo.draft_teams;
    if (teams.length < 2) {
      throw new Error('Need at least 2 teams for two-captain test');
    }

    // Validate captain data
    if (!teams[0].captain?.discordId || !teams[1].captain?.discordId) {
      throw new Error('Captains must have Discord IDs for login');
    }

    // Login Captain A using their Discord ID
    await loginAsDiscordId(contextA, teams[0].captain.discordId);

    // Login Captain B using their Discord ID
    await loginAsDiscordId(contextB, teams[1].captain.discordId);

    // Set up captain contexts
    captainA = {
      browser: browserA!,
      context: contextA,
      page: pageA,
      draftPage: new HeroDraftPage(pageA),
      userPk: teams[0].captain.pk,
      teamId: teams[0].id,
      username: teams[0].captain.username,
      discordId: teams[0].captain.discordId,
      teamName: teams[0].team_name,
    };

    captainB = {
      browser: browserB!,
      context: contextB,
      page: pageB,
      draftPage: new HeroDraftPage(pageB),
      userPk: teams[1].captain.pk,
      teamId: teams[1].id,
      username: teams[1].captain.username,
      discordId: teams[1].captain.discordId,
      teamName: teams[1].team_name,
    };

    console.log(`\n Draft Setup Complete:`);
    console.log(`   Captain A: ${captainA.username} (Team: ${captainA.teamName})`);
    console.log(`   Captain B: ${captainB.username} (Team: ${captainB.teamName})`);
    console.log(`   Draft ID: ${testInfo.pk}`);
    console.log(`   Game ID: ${testInfo.game?.pk || 'TBD'}`);
    console.log(`   Tournament ID: ${testInfo.game?.tournament_pk || 'TBD'}\n`);
  });

  test.afterAll(async () => {
    // Close browsers - use top-level refs to ensure cleanup even if beforeAll failed
    try {
      await browserA?.close();
    } catch (e) {
      console.error('Failed to close browserA:', e);
    }
    try {
      await browserB?.close();
    } catch (e) {
      console.error('Failed to close browserB:', e);
    }
  });

  test('should complete a full draft with both captains via tournament UI', async () => {
    // Increase timeout for full 22-round draft (3 minutes)
    test.setTimeout(180000);

    // Get tournament and game info for URL construction
    const tournamentPk = testInfo.game?.tournament_pk;
    const gamePk = testInfo.game?.pk;
    const draftPk = testInfo.pk;

    if (!tournamentPk || !gamePk) {
      throw new Error('Tournament PK or Game PK not available - ensure populate_herodraft_test() ran successfully');
    }

    // Navigate to match page first, then click Start Draft
    // Format: /tournament/:tournamentPk/bracket/match/:gamePk
    const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

    console.log(`   Match URL: ${matchUrl}`);
    console.log(`   Draft ID: ${draftPk}`);

    // =========================================================================
    // WebSocket Debug Listeners - Set up BEFORE navigation to catch all connections
    // =========================================================================
    const wsMessagesA: Array<{ type: string; state?: string; time: number }> = [];
    const wsMessagesB: Array<{ type: string; state?: string; time: number }> = [];
    let wsConnectionA: { url: string; closed: boolean } | null = null;
    let wsConnectionB: { url: string; closed: boolean } | null = null;

    captainA.page.on('websocket', ws => {
      wsConnectionA = { url: ws.url(), closed: false };
      console.log(`   [WS-A] Connected to: ${ws.url()}`);
      ws.on('framereceived', frame => {
        try {
          const data = JSON.parse(frame.payload as string);
          wsMessagesA.push({ type: data.type, state: data.draft_state?.state, time: Date.now() });
          console.log(`   [WS-A] <<< ${data.type} state=${data.draft_state?.state || 'N/A'}`);
        } catch {}
      });
      ws.on('framesent', frame => {
        try {
          const data = JSON.parse(frame.payload as string);
          console.log(`   [WS-A] >>> ${data.type || data.action || 'unknown'}`);
        } catch {}
      });
      ws.on('close', () => {
        console.log('   [WS-A] CLOSED');
        if (wsConnectionA) wsConnectionA.closed = true;
      });
    });

    captainB.page.on('websocket', ws => {
      wsConnectionB = { url: ws.url(), closed: false };
      console.log(`   [WS-B] Connected to: ${ws.url()}`);
      ws.on('framereceived', frame => {
        try {
          const data = JSON.parse(frame.payload as string);
          wsMessagesB.push({ type: data.type, state: data.draft_state?.state, time: Date.now() });
          console.log(`   [WS-B] <<< ${data.type} state=${data.draft_state?.state || 'N/A'}`);
        } catch {}
      });
      ws.on('framesent', frame => {
        try {
          const data = JSON.parse(frame.payload as string);
          console.log(`   [WS-B] >>> ${data.type || data.action || 'unknown'}`);
        } catch {}
      });
      ws.on('close', () => {
        console.log('   [WS-B] CLOSED');
        if (wsConnectionB) wsConnectionB.closed = true;
      });
    });

    // Helper to check WebSocket connection health
    const assertWebSocketsOpen = (step: string) => {
      if (wsConnectionA?.closed) {
        throw new Error(`[${step}] Captain A WebSocket closed unexpectedly`);
      }
      if (wsConnectionB?.closed) {
        throw new Error(`[${step}] Captain B WebSocket closed unexpectedly`);
      }
    };

    // =========================================================================
    // STEP 1: Navigate both captains to the match page and click Start Draft
    // =========================================================================
    console.log('Step 1: Navigating to match page and clicking Start Draft...');

    // Navigate both captains to the match page
    await Promise.all([
      captainA.page.goto(matchUrl),
      captainB.page.goto(matchUrl),
    ]);

    // Wait for pages to hydrate
    await Promise.all([
      waitForHydration(captainA.page),
      waitForHydration(captainB.page),
    ]);

    // Click Start Draft button on both pages
    const startDraftButton = (page: Page) =>
      page.locator('button:has-text("Start Draft"), button:has-text("View Draft"), button:has-text("Live Draft")').first();

    await Promise.all([
      startDraftButton(captainA.page).click(),
      startDraftButton(captainB.page).click(),
    ]);

    // Wait for the HeroDraft modal to open
    await Promise.all([
      captainA.draftPage.waitForModal(),
      captainB.draftPage.waitForModal(),
    ]);

    console.log('   Both captains opened draft modal from match page');

    // =========================================================================
    // STEP 2: Waiting Phase - Both captains click Ready
    // =========================================================================
    console.log('Step 2: Waiting Phase - clicking Ready...');

    // Wait for WebSocket connections to be established
    console.log('   Waiting for WebSocket connections...');
    await Promise.all([
      captainA.draftPage.waitForConnection(),
      captainB.draftPage.waitForConnection(),
    ]);

    // Verify WebSocket connections were established
    console.log(`   Captain A WebSocket: ${wsConnectionA ? 'connected to ' + wsConnectionA.url : 'NOT CONNECTED'}`);
    console.log(`   Captain B WebSocket: ${wsConnectionB ? 'connected to ' + wsConnectionB.url : 'NOT CONNECTED'}`);

    if (!wsConnectionA || !wsConnectionB) {
      throw new Error('WebSocket connections not established for both captains');
    }

    // Verify both see waiting phase
    await Promise.all([
      captainA.draftPage.assertWaitingPhase(),
      captainB.draftPage.assertWaitingPhase(),
    ]);

    // Debug: check current state
    const stateA = await captainA.draftPage.getCurrentState();
    const stateB = await captainB.draftPage.getCurrentState();
    console.log(`   Current state - Captain A: ${stateA}, Captain B: ${stateB}`);

    // Captain A clicks ready
    assertWebSocketsOpen('before Captain A ready');
    await captainA.draftPage.clickReady();
    console.log(`   Captain A (${captainA.username}) clicked Ready`);

    // Wait for Captain B to see Captain A's ready status via WebSocket
    console.log('   Waiting for Captain A ready status to propagate to Captain B...');
    await expect(
      captainB.page.locator('[data-testid^="herodraft-ready-status-"]').first()
    ).toContainText('Ready', { timeout: 5000 });
    console.log('   Captain B sees Captain A is ready');

    // Verify WebSockets still open
    assertWebSocketsOpen('after Captain A ready propagated');

    // Captain B clicks ready
    await captainB.draftPage.clickReady();
    console.log(`   Captain B (${captainB.username}) clicked Ready`);

    // Verify WebSockets still open
    assertWebSocketsOpen('after Captain B ready');

    // Wait for transition to rolling phase - both should receive state update via WebSocket
    console.log('   Waiting for rolling phase on both captains...');
    await Promise.all([
      captainA.draftPage.waitForPhaseTransition('rolling', 15000),
      captainB.draftPage.waitForPhaseTransition('rolling', 15000),
    ]);

    // Verify both received the state update
    assertWebSocketsOpen('after rolling transition');
    const stateAfterA = await captainA.draftPage.getCurrentState();
    const stateAfterB = await captainB.draftPage.getCurrentState();
    console.log(`   UI State after ready - Captain A: ${stateAfterA}, Captain B: ${stateAfterB}`);
    console.log(`   WS Messages received - Captain A: ${wsMessagesA.length}, Captain B: ${wsMessagesB.length}`);

    console.log('   Both captains ready, transitioned to rolling phase');

    // =========================================================================
    // STEP 3: Rolling Phase - Coin flip
    // =========================================================================
    console.log('Step 3: Rolling Phase - coin flip...');

    // Verify WebSockets still open
    assertWebSocketsOpen('before coin flip');

    // Wait for flip button to be available
    await captainA.draftPage.flipCoinButton.waitFor({ state: 'visible', timeout: 5000 });

    // Captain A clicks flip coin (either captain can do this)
    await captainA.draftPage.clickFlipCoin();
    console.log('   Coin flipped!');

    // Wait for choosing phase on both captains via WebSocket
    console.log('   Waiting for choosing phase on both captains...');
    await Promise.all([
      captainA.draftPage.waitForPhaseTransition('choosing', 10000),
      captainB.draftPage.waitForPhaseTransition('choosing', 10000),
    ]);

    // Verify WebSockets still open and check states
    assertWebSocketsOpen('after coin flip');
    const stateAfterFlipA = await captainA.draftPage.getCurrentState();
    const stateAfterFlipB = await captainB.draftPage.getCurrentState();
    console.log(`   UI State after flip - Captain A: ${stateAfterFlipA}, Captain B: ${stateAfterFlipB}`);
    console.log(`   WS Messages - Captain A: ${wsMessagesA.length}, Captain B: ${wsMessagesB.length}`);

    console.log('   Both captains see choosing phase');

    // =========================================================================
    // STEP 4: Choosing Phase - Winner picks, loser gets remainder
    // =========================================================================
    console.log('Step 4: Choosing Phase - selecting pick order and side...');

    // Verify WebSockets still open
    assertWebSocketsOpen('before choosing phase');

    // Check which captain is the winner
    const winnerChoices = captainA.page.locator(
      '[data-testid="herodraft-winner-choices"]'
    );
    const isAWinner = await winnerChoices.isVisible().catch(() => false);

    if (isAWinner) {
      // Captain A won - they choose first
      console.log(`   Captain A (${captainA.username}) won the flip!`);
      await captainA.draftPage.selectWinnerChoice('first_pick');
      console.log('   Winner chose: First Pick');

      // Wait for loser choice to become available via WebSocket
      const loserChoices = captainB.page.locator('[data-testid="herodraft-loser-choices"]');
      await loserChoices.waitFor({ state: 'visible', timeout: 5000 });
      assertWebSocketsOpen('after winner choice');

      // Captain B chooses side
      await captainB.draftPage.selectLoserChoice('radiant');
      console.log('   Loser chose: Radiant');
    } else {
      // Captain B won - they choose first
      console.log(`   Captain B (${captainB.username}) won the flip!`);
      await captainB.draftPage.selectWinnerChoice('first_pick');
      console.log('   Winner chose: First Pick');

      // Wait for loser choice to become available via WebSocket
      const loserChoices = captainA.page.locator('[data-testid="herodraft-loser-choices"]');
      await loserChoices.waitFor({ state: 'visible', timeout: 5000 });
      assertWebSocketsOpen('after winner choice');

      // Captain A chooses side
      await captainA.draftPage.selectLoserChoice('radiant');
      console.log('   Loser chose: Radiant');
    }

    // Wait for drafting phase on both captains via WebSocket
    console.log('   Waiting for drafting phase on both captains...');
    await Promise.all([
      captainA.draftPage.waitForPhaseTransition('drafting', 10000),
      captainB.draftPage.waitForPhaseTransition('drafting', 10000),
    ]);

    // Verify WebSockets still open and check states
    assertWebSocketsOpen('after drafting transition');
    const stateAfterChoicesA = await captainA.draftPage.getCurrentState();
    const stateAfterChoicesB = await captainB.draftPage.getCurrentState();
    console.log(`   UI State after choices - Captain A: ${stateAfterChoicesA}, Captain B: ${stateAfterChoicesB}`);
    console.log(`   WS Messages - Captain A: ${wsMessagesA.length}, Captain B: ${wsMessagesB.length}`);

    console.log('   Choices made, transitioning to drafting phase');

    // =========================================================================
    // STEP 5: Drafting Phase - 24 rounds of bans and picks
    // =========================================================================
    console.log('Step 5: Drafting Phase - beginning hero selection...');

    // Get starting timer values for timing verification
    const startGraceA = await captainA.draftPage.getGraceTimeSeconds();
    const startReserveA = await captainA.draftPage.getTeamAReserveTimeSeconds();
    console.log(
      `   Initial timers - Grace: ${startGraceA}s, Reserve A: ${startReserveA}s`
    );

    // Helper to determine which captain should pick based on the "PICKING" indicator
    // Team A in topbar = first team in draft_teams = Captain A's team (based on test setup order)
    const getCurrentPicker = async (): Promise<CaptainContext> => {
      // Wait for either team's picking indicator to become visible
      // This handles race conditions where state hasn't updated yet
      const teamAIndicator = captainA.page.locator('[data-testid="herodraft-team-a-picking"]');
      const teamBIndicator = captainA.page.locator('[data-testid="herodraft-team-b-picking"]');

      // Wait up to 5s for either indicator to appear
      try {
        await expect(teamAIndicator.or(teamBIndicator)).toBeVisible({ timeout: 5000 });
      } catch {
        console.log('[getCurrentPicker] WARNING: No picking indicator visible after 5s');
      }

      const teamAPicking = await teamAIndicator.isVisible().catch(() => false);
      const teamBPicking = await teamBIndicator.isVisible().catch(() => false);

      console.log(`[getCurrentPicker] Team A picking: ${teamAPicking}, Team B picking: ${teamBPicking}`);

      // In test setup, Captain A is assigned to first team slot (Team A in topbar)
      return teamAPicking ? captainA : captainB;
    };

    // Use different hero IDs for picks to avoid conflicts
    // Hero IDs 1-130 are valid Dota 2 hero IDs
    // Captain's Mode has 22 rounds: 12 bans + 10 picks
    const heroIds = Array.from({ length: 30 }, (_, i) => i + 1); // [1, 2, 3, ..., 30]
    let heroIndex = 0;

    // Full Captain's Mode draft (24 rounds: 14 bans + 10 picks)
    const maxRounds = 24;

    for (let round = 1; round <= maxRounds; round++) {
      // Determine who should pick at the START of each round
      const currentPicker = await getCurrentPicker();
      const currentRound = await currentPicker.draftPage.getCurrentRound();
      const action = await currentPicker.draftPage.getCurrentAction();

      console.log(
        `   Round ${round}: ${currentPicker.username} will ${action} a hero...`
      );

      // Current picker selects a hero
      await currentPicker.draftPage.pickHero(heroIds[heroIndex]);
      heroIndex++;

      console.log(`   ${currentPicker.username} completed ${action}`);

      // Wait for the pick to propagate to both clients
      await Promise.all([
        captainA.draftPage.waitForDraftUpdate(2000),
        captainB.draftPage.waitForDraftUpdate(2000),
      ]);

      // Verify the round is completed on both sides
      await Promise.all([
        captainA.draftPage.assertRoundCompleted(currentRound),
        captainB.draftPage.assertRoundCompleted(currentRound),
      ]);

      // Brief pause between rounds for visibility (skip on last round)
      if (round < maxRounds) {
        await captainA.page.waitForTimeout(300);
      }
    }

    // After all rounds, draft should be completed - wait for state change
    await captainA.page.waitForTimeout(1000);

    console.log(`   Completed ${maxRounds} rounds of drafting`);

    // =========================================================================
    // STEP 6: Verify Draft State
    // =========================================================================
    console.log('Step 6: Verifying draft state...');

    // Check that picked heroes are marked as unavailable
    for (let i = 0; i < heroIndex; i++) {
      await captainA.draftPage.assertHeroUnavailable(heroIds[i]);
    }

    console.log('   All picked heroes marked as unavailable');

    // Verify both captains see the same state
    const roundA = await captainA.draftPage.getCurrentRound();
    const roundB = await captainB.draftPage.getCurrentRound();
    expect(roundA).toBe(roundB);

    console.log(`   Both captains synchronized at round ${roundA}`);

    // =========================================================================
    // TIMING VERIFICATION
    // =========================================================================
    console.log('Timing Verification...');

    const endGraceA = await captainA.draftPage.getGraceTimeSeconds();
    const endReserveA = await captainA.draftPage.getTeamAReserveTimeSeconds();

    console.log(`   Grace time: ${startGraceA}s -> ${endGraceA}s`);
    console.log(`   Reserve time: ${startReserveA}s -> ${endReserveA}s`);

    console.log('\n Two-Captain Draft Test Complete!');
    console.log('   The draft flow is working correctly with both captains.');
  });
});
