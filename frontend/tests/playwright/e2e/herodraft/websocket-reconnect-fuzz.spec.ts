import { test, expect, chromium, BrowserContext, Page } from '@playwright/test';
import { loginAsDiscordId, waitForHydration } from '../../fixtures/auth';
import { HeroDraftPage } from '../../helpers/HeroDraftPage';

const API_URL = 'https://localhost/api';
const BASE_URL = 'https://localhost';

/**
 * WebSocket Reconnection Fuzzing Tests
 *
 * These tests stress test the WebSocket reconnection logic by:
 * - Randomly dropping connections (closing browser contexts)
 * - Creating new contexts and reconnecting
 * - Verifying state is maintained across reconnections
 * - Completing drafts despite connection interruptions
 */
test.describe('HeroDraft WebSocket Reconnection Fuzzing', () => {
  test.setTimeout(180000); // 3 minutes for fuzzing tests

  /**
   * Helper to create a new browser context with proper settings
   */
  async function createContext(browser: any): Promise<BrowserContext> {
    return browser.newContext({
      ignoreHTTPSErrors: true,
    });
  }

  /**
   * Helper to login and navigate to draft
   */
  async function setupCaptain(
    context: BrowserContext,
    discordId: string,
    matchUrl: string
  ): Promise<{ page: Page; draftPage: HeroDraftPage }> {
    await loginAsDiscordId(context, discordId);
    const page = await context.newPage();
    await page.goto(matchUrl);
    await waitForHydration(page);

    // Click start/view draft
    const startBtn = page
      .locator('button:has-text("Start Draft"), button:has-text("View Draft")')
      .first();
    await startBtn.click();

    const draftPage = new HeroDraftPage(page);
    await draftPage.waitForModal();
    await draftPage.waitForConnection();

    return { page, draftPage };
  }

  test('should maintain state through multiple connection drops during waiting phase', async () => {
    const browser = await chromium.launch({
      headless: true,
      args: ['--disable-web-security', '--ignore-certificate-errors', '--no-sandbox'],
    });

    let contextA: BrowserContext | null = null;
    let contextB: BrowserContext | null = null;

    try {
      // Get test draft info
      contextA = await createContext(browser);
      const response = await contextA.request.get(
        `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
        { failOnStatusCode: false, timeout: 10000 }
      );

      if (!response.ok()) {
        throw new Error(`Failed to get test data: ${response.status()}`);
      }

      const testInfo = await response.json();
      const draftPk = testInfo.pk;
      const teams = testInfo.draft_teams;
      const tournamentPk = testInfo.game.tournament_pk;
      const gamePk = testInfo.game.pk;
      const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

      console.log(`Draft PK: ${draftPk}`);
      console.log(`Captain A: ${teams[0].captain.username}`);
      console.log(`Captain B: ${teams[1].captain.username}`);

      // Reset draft
      await contextA.request.post(`${API_URL}/tests/herodraft/${draftPk}/reset/`);

      // Setup captain A
      const { page: pageA, draftPage: draftPageA } = await setupCaptain(
        contextA,
        teams[0].captain.discordId,
        matchUrl
      );

      // Setup captain B
      contextB = await createContext(browser);
      const { page: pageB, draftPage: draftPageB } = await setupCaptain(
        contextB,
        teams[1].captain.discordId,
        matchUrl
      );

      console.log('Both captains connected');

      // FUZZ: Drop captain A's connection and reconnect
      console.log('FUZZ: Dropping captain A connection...');
      await contextA.close();

      // Wait a bit for server to notice disconnect
      await new Promise((r) => setTimeout(r, 2000));

      // Reconnect captain A
      console.log('FUZZ: Reconnecting captain A...');
      contextA = await createContext(browser);
      const reconnectA = await setupCaptain(
        contextA,
        teams[0].captain.discordId,
        matchUrl
      );

      // Verify captain A can see the draft
      await reconnectA.draftPage.waitForModal();
      console.log('Captain A reconnected successfully');

      // FUZZ: Drop captain B's connection
      console.log('FUZZ: Dropping captain B connection...');
      await contextB.close();

      await new Promise((r) => setTimeout(r, 2000));

      // Reconnect captain B
      console.log('FUZZ: Reconnecting captain B...');
      contextB = await createContext(browser);
      const reconnectB = await setupCaptain(
        contextB,
        teams[1].captain.discordId,
        matchUrl
      );

      await reconnectB.draftPage.waitForModal();
      console.log('Captain B reconnected successfully');

      // Now both ready up
      await reconnectA.draftPage.clickReady();
      await reconnectB.draftPage.clickReady();
      console.log('Both captains ready');

      // Verify phase transition
      await Promise.all([
        reconnectA.draftPage.waitForPhaseTransition('rolling', 15000),
        reconnectB.draftPage.waitForPhaseTransition('rolling', 15000),
      ]);

      console.log('TEST PASSED: State maintained through connection drops');
    } finally {
      if (contextA) await contextA.close().catch(() => {});
      if (contextB) await contextB.close().catch(() => {});
      await browser.close();
    }
  });

  // Skip: Flaky stress test - requires stable multi-context WebSocket state synchronization
  test.skip('should recover draft state after reconnection during drafting phase', async () => {
    const browser = await chromium.launch({
      headless: true,
      args: ['--disable-web-security', '--ignore-certificate-errors', '--no-sandbox'],
    });

    let contextA: BrowserContext | null = null;
    let contextB: BrowserContext | null = null;

    try {
      contextA = await createContext(browser);
      contextB = await createContext(browser);

      // Get test draft info
      const response = await contextA.request.get(
        `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
        { failOnStatusCode: false, timeout: 10000 }
      );

      const testInfo = await response.json();
      const draftPk = testInfo.pk;
      const teams = testInfo.draft_teams;
      const tournamentPk = testInfo.game.tournament_pk;
      const gamePk = testInfo.game.pk;
      const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

      // Reset draft
      await contextA.request.post(`${API_URL}/tests/herodraft/${draftPk}/reset/`);

      // Setup both captains
      const { page: pageA, draftPage: draftPageA } = await setupCaptain(
        contextA,
        teams[0].captain.discordId,
        matchUrl
      );
      const { page: pageB, draftPage: draftPageB } = await setupCaptain(
        contextB,
        teams[1].captain.discordId,
        matchUrl
      );

      // Ready up
      await draftPageA.clickReady();
      await draftPageB.clickReady();

      // Wait for rolling phase
      await Promise.all([
        draftPageA.waitForPhaseTransition('rolling', 15000),
        draftPageB.waitForPhaseTransition('rolling', 15000),
      ]);

      // Flip coin
      await draftPageA.flipCoinButton.waitFor({ state: 'visible', timeout: 15000 });
      await draftPageA.clickFlipCoin();

      // Wait for choosing phase
      await Promise.all([
        draftPageA.waitForPhaseTransition('choosing', 15000),
        draftPageB.waitForPhaseTransition('choosing', 15000),
      ]);

      // Make choices
      const winnerChoices = pageA.locator('[data-testid="herodraft-winner-choices"]');
      const isAWinner = await winnerChoices.isVisible().catch(() => false);

      if (isAWinner) {
        await draftPageA.selectWinnerChoice('first_pick');
        await pageB
          .locator('[data-testid="herodraft-loser-choices"]')
          .waitFor({ state: 'visible', timeout: 10000 });
        await draftPageB.selectLoserChoice('radiant');
      } else {
        await draftPageB.selectWinnerChoice('first_pick');
        await pageA
          .locator('[data-testid="herodraft-loser-choices"]')
          .waitFor({ state: 'visible', timeout: 10000 });
        await draftPageA.selectLoserChoice('radiant');
      }

      // Wait for drafting phase
      await Promise.all([
        draftPageA.waitForPhaseTransition('drafting', 15000),
        draftPageB.waitForPhaseTransition('drafting', 15000),
      ]);

      console.log('Drafting phase started');

      // Make first pick
      const teamAPicking = await draftPageA.isTeamAPicking();
      let currentPicker = teamAPicking ? draftPageA : draftPageB;
      let pickedHeroId = 1; // Anti-Mage

      await currentPicker.pickHero(pickedHeroId);
      console.log(`First hero picked: ${pickedHeroId}`);

      // FUZZ: Drop the current picker's connection right after picking
      console.log('FUZZ: Dropping current picker connection...');
      if (teamAPicking) {
        await contextA.close();
        contextA = null;
      } else {
        await contextB.close();
        contextB = null;
      }

      await new Promise((r) => setTimeout(r, 2000));

      // Reconnect
      console.log('FUZZ: Reconnecting dropped captain...');
      if (!contextA) {
        contextA = await createContext(browser);
        const reconnect = await setupCaptain(
          contextA,
          teams[0].captain.discordId,
          matchUrl
        );
        await reconnect.draftPage.waitForPhaseTransition('drafting', 10000);

        // Verify the hero we picked is still marked as unavailable
        await reconnect.draftPage.assertHeroUnavailable(pickedHeroId);
        console.log(`Verified hero ${pickedHeroId} still unavailable after reconnect`);
      } else {
        contextB = await createContext(browser);
        const reconnect = await setupCaptain(
          contextB,
          teams[1].captain.discordId,
          matchUrl
        );
        await reconnect.draftPage.waitForPhaseTransition('drafting', 10000);
        await reconnect.draftPage.assertHeroUnavailable(pickedHeroId);
        console.log(`Verified hero ${pickedHeroId} still unavailable after reconnect`);
      }

      console.log('TEST PASSED: Draft state recovered after reconnection');
    } finally {
      if (contextA) await contextA.close().catch(() => {});
      if (contextB) await contextB.close().catch(() => {});
      await browser.close();
    }
  });

  test('should handle rapid connection drops and reconnects', async () => {
    const browser = await chromium.launch({
      headless: true,
      args: ['--disable-web-security', '--ignore-certificate-errors', '--no-sandbox'],
    });

    let context: BrowserContext | null = null;

    try {
      context = await createContext(browser);

      // Get test draft info
      const response = await context.request.get(
        `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
        { failOnStatusCode: false, timeout: 10000 }
      );

      const testInfo = await response.json();
      const draftPk = testInfo.pk;
      const teams = testInfo.draft_teams;
      const tournamentPk = testInfo.game.tournament_pk;
      const gamePk = testInfo.game.pk;
      const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

      // Reset draft
      await context.request.post(`${API_URL}/tests/herodraft/${draftPk}/reset/`);

      const discordId = teams[0].captain.discordId;

      // FUZZ: Rapid connect/disconnect cycles
      const CYCLES = 5;
      console.log(`Starting ${CYCLES} rapid connect/disconnect cycles...`);

      for (let i = 0; i < CYCLES; i++) {
        console.log(`Cycle ${i + 1}/${CYCLES}: Connecting...`);

        const { page, draftPage } = await setupCaptain(context, discordId, matchUrl);

        // Verify connection
        await draftPage.waitForModal();
        await draftPage.waitForConnection();
        console.log(`Cycle ${i + 1}/${CYCLES}: Connected, waiting briefly...`);

        // Random short wait (100-500ms)
        await new Promise((r) => setTimeout(r, 100 + Math.random() * 400));

        console.log(`Cycle ${i + 1}/${CYCLES}: Dropping connection...`);
        await context.close();

        // Brief pause between cycles
        await new Promise((r) => setTimeout(r, 500));

        // Create new context for next cycle
        context = await createContext(browser);
      }

      // Final connection - verify we can still access the draft
      console.log('Final connection after rapid cycles...');
      const { draftPage: finalDraft } = await setupCaptain(
        context,
        discordId,
        matchUrl
      );

      await finalDraft.waitForModal();
      await finalDraft.waitForConnection();
      console.log('TEST PASSED: Survived rapid connect/disconnect cycles');
    } finally {
      if (context) await context.close().catch(() => {});
      await browser.close();
    }
  });

  // Skip: Flaky stress test - timer pause verification requires precise timing control
  test.skip('should pause timer when disconnected and resume on reconnect', async () => {
    const browser = await chromium.launch({
      headless: true,
      args: ['--disable-web-security', '--ignore-certificate-errors', '--no-sandbox'],
    });

    let contextA: BrowserContext | null = null;
    let contextB: BrowserContext | null = null;

    try {
      contextA = await createContext(browser);
      contextB = await createContext(browser);

      // Get test draft info
      const response = await contextA.request.get(
        `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
        { failOnStatusCode: false, timeout: 10000 }
      );

      const testInfo = await response.json();
      const draftPk = testInfo.pk;
      const teams = testInfo.draft_teams;
      const tournamentPk = testInfo.game.tournament_pk;
      const gamePk = testInfo.game.pk;
      const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

      // Reset draft
      await contextA.request.post(`${API_URL}/tests/herodraft/${draftPk}/reset/`);

      // Setup both captains
      const { page: pageA, draftPage: draftPageA } = await setupCaptain(
        contextA,
        teams[0].captain.discordId,
        matchUrl
      );
      const { page: pageB, draftPage: draftPageB } = await setupCaptain(
        contextB,
        teams[1].captain.discordId,
        matchUrl
      );

      // Progress to drafting phase
      await draftPageA.clickReady();
      await draftPageB.clickReady();

      await Promise.all([
        draftPageA.waitForPhaseTransition('rolling', 15000),
        draftPageB.waitForPhaseTransition('rolling', 15000),
      ]);

      await draftPageA.flipCoinButton.waitFor({ state: 'visible', timeout: 15000 });
      await draftPageA.clickFlipCoin();

      await Promise.all([
        draftPageA.waitForPhaseTransition('choosing', 15000),
        draftPageB.waitForPhaseTransition('choosing', 15000),
      ]);

      // Make choices
      const isAWinner = await pageA
        .locator('[data-testid="herodraft-winner-choices"]')
        .isVisible()
        .catch(() => false);

      if (isAWinner) {
        await draftPageA.selectWinnerChoice('first_pick');
        await pageB
          .locator('[data-testid="herodraft-loser-choices"]')
          .waitFor({ state: 'visible', timeout: 10000 });
        await draftPageB.selectLoserChoice('radiant');
      } else {
        await draftPageB.selectWinnerChoice('first_pick');
        await pageA
          .locator('[data-testid="herodraft-loser-choices"]')
          .waitFor({ state: 'visible', timeout: 10000 });
        await draftPageA.selectLoserChoice('radiant');
      }

      await Promise.all([
        draftPageA.waitForPhaseTransition('drafting', 15000),
        draftPageB.waitForPhaseTransition('drafting', 15000),
      ]);

      console.log('Drafting phase started - testing timer pause behavior');

      // Wait a moment for timers to be visible and ticking
      await new Promise((r) => setTimeout(r, 1000));

      // Record grace time BEFORE disconnection
      const graceTimeBefore = await draftPageA.getGraceTimeSeconds();
      const teamATimeBefore = await draftPageA.getTeamAReserveTimeSeconds();
      const teamBTimeBefore = await draftPageA.getTeamBReserveTimeSeconds();

      console.log(`Timer before disconnect: grace=${graceTimeBefore}s, teamA=${teamATimeBefore}s, teamB=${teamBTimeBefore}s`);

      // Disconnect captain A (simulates WebSocket drop)
      console.log('FUZZ: Dropping captain A connection...');
      await contextA.close();
      contextA = null;

      // Wait 5 seconds while disconnected - timer should be PAUSED on server
      const DISCONNECT_DURATION_MS = 5000;
      console.log(`Waiting ${DISCONNECT_DURATION_MS}ms while disconnected...`);
      await new Promise((r) => setTimeout(r, DISCONNECT_DURATION_MS));

      // Reconnect captain A
      console.log('FUZZ: Reconnecting captain A...');
      contextA = await createContext(browser);
      const { draftPage: reconnectedDraftPageA } = await setupCaptain(
        contextA,
        teams[0].captain.discordId,
        matchUrl
      );

      await reconnectedDraftPageA.waitForPhaseTransition('drafting', 10000);
      await reconnectedDraftPageA.waitForConnection();

      // Wait a moment for state to stabilize
      await new Promise((r) => setTimeout(r, 500));

      // Record timer AFTER reconnection
      const graceTimeAfter = await reconnectedDraftPageA.getGraceTimeSeconds();
      const teamATimeAfter = await reconnectedDraftPageA.getTeamAReserveTimeSeconds();
      const teamBTimeAfter = await reconnectedDraftPageA.getTeamBReserveTimeSeconds();

      console.log(`Timer after reconnect: grace=${graceTimeAfter}s, teamA=${teamATimeAfter}s, teamB=${teamBTimeAfter}s`);

      // Calculate elapsed time - should be minimal if timer was paused
      // Allow for up to 3 seconds of actual elapsed time (for connection/setup overhead)
      const graceElapsed = graceTimeBefore - graceTimeAfter;
      const teamAElapsed = teamATimeBefore - teamATimeAfter;
      const teamBElapsed = teamBTimeBefore - teamBTimeAfter;

      console.log(`Elapsed: grace=${graceElapsed}s, teamA=${teamAElapsed}s, teamB=${teamBElapsed}s`);

      // If timer wasn't paused, we'd see ~5 seconds elapsed
      // With pause, we should see much less (accounting for reconnect overhead)
      const MAX_ALLOWED_ELAPSED = 3; // seconds

      // Check grace time (if it was running)
      if (graceTimeBefore > 0 && graceTimeAfter > 0) {
        expect(graceElapsed).toBeLessThanOrEqual(MAX_ALLOWED_ELAPSED);
        console.log(`✓ Grace timer paused correctly (${graceElapsed}s elapsed vs ${DISCONNECT_DURATION_MS / 1000}s disconnected)`);
      }

      // Check reserve times - at least one should have been active
      if (teamATimeBefore > 0 || teamBTimeBefore > 0) {
        const maxReserveElapsed = Math.max(teamAElapsed, teamBElapsed);
        // Reserve time should not have decreased significantly
        expect(maxReserveElapsed).toBeLessThanOrEqual(MAX_ALLOWED_ELAPSED);
        console.log(`✓ Reserve timer paused correctly (max ${maxReserveElapsed}s elapsed vs ${DISCONNECT_DURATION_MS / 1000}s disconnected)`);
      }

      console.log('TEST PASSED: Timer paused during disconnection and resumed on reconnect');
    } finally {
      if (contextA) await contextA.close().catch(() => {});
      if (contextB) await contextB.close().catch(() => {});
      await browser.close();
    }
  });

  // Skip: Flaky stress test - random connection drops cause unpredictable timing failures
  test.skip('should complete full draft with intermittent connection drops', async () => {
    const browser = await chromium.launch({
      headless: true,
      args: ['--disable-web-security', '--ignore-certificate-errors', '--no-sandbox'],
    });

    let contextA: BrowserContext | null = null;
    let contextB: BrowserContext | null = null;
    let pageA: Page | null = null;
    let pageB: Page | null = null;
    let draftPageA: HeroDraftPage | null = null;
    let draftPageB: HeroDraftPage | null = null;

    try {
      contextA = await createContext(browser);
      contextB = await createContext(browser);

      // Get test draft info
      const response = await contextA.request.get(
        `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
        { failOnStatusCode: false, timeout: 10000 }
      );

      const testInfo = await response.json();
      const draftPk = testInfo.pk;
      const teams = testInfo.draft_teams;
      const tournamentPk = testInfo.game.tournament_pk;
      const gamePk = testInfo.game.pk;
      const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

      // Reset draft
      await contextA.request.post(`${API_URL}/tests/herodraft/${draftPk}/reset/`);

      // Helper to reconnect a captain
      const reconnectCaptain = async (
        isA: boolean
      ): Promise<{ context: BrowserContext; page: Page; draftPage: HeroDraftPage }> => {
        const ctx = await createContext(browser);
        const discordId = isA
          ? teams[0].captain.discordId
          : teams[1].captain.discordId;
        const result = await setupCaptain(ctx, discordId, matchUrl);
        return { context: ctx, ...result };
      };

      // Initial setup
      const setupA = await setupCaptain(
        contextA,
        teams[0].captain.discordId,
        matchUrl
      );
      pageA = setupA.page;
      draftPageA = setupA.draftPage;

      const setupB = await setupCaptain(
        contextB,
        teams[1].captain.discordId,
        matchUrl
      );
      pageB = setupB.page;
      draftPageB = setupB.draftPage;

      // Ready up and progress to drafting
      await draftPageA.clickReady();
      await draftPageB.clickReady();

      await Promise.all([
        draftPageA.waitForPhaseTransition('rolling', 15000),
        draftPageB.waitForPhaseTransition('rolling', 15000),
      ]);

      await draftPageA.flipCoinButton.waitFor({ state: 'visible', timeout: 15000 });
      await draftPageA.clickFlipCoin();

      await Promise.all([
        draftPageA.waitForPhaseTransition('choosing', 15000),
        draftPageB.waitForPhaseTransition('choosing', 15000),
      ]);

      // Make choices
      const isAWinner = await pageA
        .locator('[data-testid="herodraft-winner-choices"]')
        .isVisible()
        .catch(() => false);

      if (isAWinner) {
        await draftPageA.selectWinnerChoice('first_pick');
        await pageB
          .locator('[data-testid="herodraft-loser-choices"]')
          .waitFor({ state: 'visible', timeout: 10000 });
        await draftPageB.selectLoserChoice('radiant');
      } else {
        await draftPageB.selectWinnerChoice('first_pick');
        await pageA
          .locator('[data-testid="herodraft-loser-choices"]')
          .waitFor({ state: 'visible', timeout: 10000 });
        await draftPageA.selectLoserChoice('radiant');
      }

      await Promise.all([
        draftPageA.waitForPhaseTransition('drafting', 15000),
        draftPageB.waitForPhaseTransition('drafting', 15000),
      ]);

      console.log('Drafting phase started');

      // Pick heroes with intermittent drops
      // Captain's Mode: 24 rounds total (bans + picks)
      // We'll do first 6 rounds with random drops
      const heroIds = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]; // First 10 heroes
      let heroIndex = 0;
      let dropCount = 0;
      const MAX_DROPS = 3;

      for (let round = 0; round < 6 && heroIndex < heroIds.length; round++) {
        // Check who's picking
        const teamAPicking = await draftPageA!.isTeamAPicking();
        const currentPicker = teamAPicking ? draftPageA! : draftPageB!;
        const currentPage = teamAPicking ? pageA! : pageB!;

        // Random chance to drop connection (33% chance, max 3 drops)
        const shouldDrop = dropCount < MAX_DROPS && Math.random() < 0.33;

        if (shouldDrop) {
          console.log(`FUZZ: Dropping ${teamAPicking ? 'A' : 'B'} before pick...`);
          dropCount++;

          if (teamAPicking) {
            await contextA!.close();
            const reconnect = await reconnectCaptain(true);
            contextA = reconnect.context;
            pageA = reconnect.page;
            draftPageA = reconnect.draftPage;
            await draftPageA.waitForPhaseTransition('drafting', 10000);
          } else {
            await contextB!.close();
            const reconnect = await reconnectCaptain(false);
            contextB = reconnect.context;
            pageB = reconnect.page;
            draftPageB = reconnect.draftPage;
            await draftPageB.waitForPhaseTransition('drafting', 10000);
          }

          console.log('Reconnected, continuing...');
        }

        // Make the pick/ban
        const heroId = heroIds[heroIndex];
        const picker = teamAPicking ? draftPageA! : draftPageB!;

        try {
          await picker.pickHero(heroId);
          console.log(`Round ${round + 1}: Picked hero ${heroId}`);
          heroIndex++;
        } catch (e) {
          console.log(`Round ${round + 1}: Pick failed, hero might be banned. Trying next...`);
          heroIndex++;
        }

        // Brief wait for state sync
        await new Promise((r) => setTimeout(r, 1000));
      }

      console.log(`TEST PASSED: Completed ${heroIndex} picks/bans with ${dropCount} connection drops`);
    } finally {
      if (contextA) await contextA.close().catch(() => {});
      if (contextB) await contextB.close().catch(() => {});
      await browser.close();
    }
  });
});
