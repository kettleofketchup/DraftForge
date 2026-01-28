/**
 * HeroDraft with Bracket Demo - Full Flow Video Recording
 *
 * Records a complete Captain's Mode hero draft from start to finish,
 * accessed from the tournament bracket. Shows both captains' perspectives.
 *
 * Video output: 1:1 aspect ratio (800x800) for docs and social media.
 * Named outputs: captain1_herodraft.webm, captain2_herodraft.webm
 *
 * Flow:
 * 1. Navigate to tournament bracket
 * 2. Click on a match to open match modal
 * 3. Start the hero draft
 * 4. Complete waiting phase (both ready)
 * 5. Rolling phase (coin flip)
 * 6. Choosing phase (winner picks order/side)
 * 7. Drafting phase (24 rounds: 14 bans + 10 picks)
 */

import {
  test,
  expect,
  chromium,
  type Browser,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import { loginAsDiscordId, waitForHydration } from '../fixtures/auth';
import { HeroDraftPage } from '../helpers/HeroDraftPage';
import * as path from 'path';

// Use nginx hostname inside Docker containers, localhost for local runs
const DOCKER_HOST = process.env.DOCKER_HOST || 'nginx';
const API_URL = `https://${DOCKER_HOST}/api`;
const BASE_URL = `https://${DOCKER_HOST}`;
const VIDEO_OUTPUT_DIR = 'demo-results/videos';

interface CaptainContext {
  browser: Browser;
  context: BrowserContext;
  page: Page;
  draftPage: HeroDraftPage;
  username: string;
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
  }>;
}

test.describe('HeroDraft with Bracket Demo', () => {
  let captainA: CaptainContext;
  let captainB: CaptainContext;
  let testInfo: HeroDraftTestInfo;

  // Store browsers at top level for cleanup
  let browserA: Browser | null = null;
  let browserB: Browser | null = null;

  test.beforeAll(async () => {
    // Headless for CI/automated recording - video still captures screen
    // Use system chromium in Docker (Alpine) since Playwright's bundled chromium requires glibc
    const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/usr/bin/chromium';
    const browserOptions = {
      headless: true,
      slowMo: 100, // Slow for demo visibility
      executablePath,
      args: [
        '--disable-web-security',
        '--ignore-certificate-errors',
        '--no-sandbox',
        '--disable-gpu',
        '--disable-dev-shm-usage',
      ],
    };

    browserA = await chromium.launch(browserOptions);
    browserB = await chromium.launch(browserOptions);

    // 1:1 aspect ratio for demo videos
    const windowSize = 800;

    // =========================================================================
    // PHASE 1: Setup (no video recording yet)
    // =========================================================================

    // Create setup contexts WITHOUT video recording
    const setupContextA = await browserA.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowSize, height: windowSize },
    });
    const setupContextB = await browserB.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowSize, height: windowSize },
    });

    // Fetch draft info
    const response = await setupContextA.request.get(
      `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
      { failOnStatusCode: false, timeout: 10000 }
    );

    if (!response.ok()) {
      await setupContextA.close();
      await setupContextB.close();
      throw new Error(
        `Failed to get HeroDraft test data. Run 'inv db.populate.all' first.`
      );
    }

    testInfo = await response.json();

    // Reset the draft
    await setupContextA.request.post(
      `${API_URL}/tests/herodraft/${testInfo.pk}/reset/`,
      { failOnStatusCode: false }
    );

    const teams = testInfo.draft_teams;
    const tournamentPk = testInfo.game?.tournament_pk;
    const gamePk = testInfo.game?.pk;
    const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

    // Login both captains in setup contexts
    await loginAsDiscordId(setupContextA, teams[0].captain.discordId);
    await loginAsDiscordId(setupContextB, teams[1].captain.discordId);

    // Navigate to match page and wait for full content to be visible
    // This warms the browser cache so the video context loads much faster
    const setupPageA = await setupContextA.newPage();
    const setupPageB = await setupContextB.newPage();

    await Promise.all([setupPageA.goto(matchUrl), setupPageB.goto(matchUrl)]);
    await Promise.all([waitForHydration(setupPageA), waitForHydration(setupPageB)]);

    // Wait for the "Start Draft" button to be visible - this ensures:
    // 1. Page is fully loaded
    // 2. Match modal auto-opened (URL has /match/ID)
    // 3. Browser has cached all assets
    const startDraftSelector = 'button:has-text("Start Draft"), button:has-text("View Draft"), button:has-text("Live Draft")';
    await Promise.all([
      setupPageA.locator(startDraftSelector).first().waitFor({ state: 'visible', timeout: 30000 }),
      setupPageB.locator(startDraftSelector).first().waitFor({ state: 'visible', timeout: 30000 }),
    ]);
    console.log('Setup: Start Draft button visible on both pages (cache warmed)');

    // Save storage state (cookies, localStorage) for video contexts
    const storageStateA = await setupContextA.storageState();
    const storageStateB = await setupContextB.storageState();

    // Close setup contexts
    await setupPageA.close();
    await setupPageB.close();
    await setupContextA.close();
    await setupContextB.close();

    // =========================================================================
    // PHASE 2: Create video-recording contexts with pre-loaded state
    // =========================================================================

    // Create contexts WITH video recording AND pre-loaded storage state
    const contextA = await browserA.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowSize, height: windowSize },
      storageState: storageStateA,
      recordVideo: {
        dir: VIDEO_OUTPUT_DIR,
        size: { width: windowSize, height: windowSize },
      },
    });

    const contextB = await browserB.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowSize, height: windowSize },
      storageState: storageStateB,
      recordVideo: {
        dir: VIDEO_OUTPUT_DIR,
        size: { width: windowSize, height: windowSize },
      },
    });

    // Inject playwright marker to disable react-scan in demos
    await contextA.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });
    await contextB.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });

    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    // Navigate to match page - video recording starts here
    // Browser cache is warm from setup phase, so this should load fast
    await Promise.all([pageA.goto(matchUrl), pageB.goto(matchUrl)]);

    // Wait for page to fully load and Start Draft button to be visible
    // This ensures the video shows loaded content, not loading screens
    await Promise.all([waitForHydration(pageA), waitForHydration(pageB)]);

    // Reuse startDraftSelector from setup phase
    await Promise.all([
      pageA.locator(startDraftSelector).first().waitFor({ state: 'visible', timeout: 30000 }),
      pageB.locator(startDraftSelector).first().waitFor({ state: 'visible', timeout: 30000 }),
    ]);
    console.log('Video: Start Draft button visible - demo ready');

    captainA = {
      browser: browserA!,
      context: contextA,
      page: pageA,
      draftPage: new HeroDraftPage(pageA),
      username: teams[0].captain.username,
      teamName: teams[0].team_name,
    };

    captainB = {
      browser: browserB!,
      context: contextB,
      page: pageB,
      draftPage: new HeroDraftPage(pageB),
      username: teams[1].captain.username,
      teamName: teams[1].team_name,
    };

    console.log(`Demo Setup:`);
    console.log(`  Captain A: ${captainA.username} (${captainA.teamName})`);
    console.log(`  Captain B: ${captainB.username} (${captainB.teamName})`);
    console.log(`  Draft ID: ${testInfo.pk}`);
  });

  test.afterAll(async () => {
    const fs = await import('fs/promises');

    // Get video paths before closing pages (path() returns a promise)
    const videoPathA = await captainA?.page?.video()?.path();
    const videoPathB = await captainB?.page?.video()?.path();

    // Close pages first to finalize video files
    try {
      if (captainA?.page) await captainA.page.close();
      if (captainB?.page) await captainB.page.close();
    } catch (e) {
      console.error('Error closing pages:', e);
    }

    // Close contexts
    try {
      if (captainA?.context) await captainA.context.close();
      if (captainB?.context) await captainB.context.close();
    } catch (e) {
      console.error('Error closing contexts:', e);
    }

    // Close browsers
    try {
      await browserA?.close();
      await browserB?.close();
    } catch (e) {
      console.error('Error closing browsers:', e);
    }

    // Copy videos to named outputs after everything is closed
    try {
      if (videoPathA) {
        const destA = path.join(VIDEO_OUTPUT_DIR, 'captain1_herodraft.webm');
        await fs.copyFile(videoPathA, destA);
        console.log(`Saved: captain1_herodraft.webm`);
      }
      if (videoPathB) {
        const destB = path.join(VIDEO_OUTPUT_DIR, 'captain2_herodraft.webm');
        await fs.copyFile(videoPathB, destB);
        console.log(`Saved: captain2_herodraft.webm`);
      }
    } catch (e) {
      console.error('Error copying videos:', e);
    }
  });

  test('Complete HeroDraft from Tournament Bracket', async () => {
    test.setTimeout(600_000); // 10 minutes for full draft

    console.log('=== DEMO START ===');
    console.log(`Match URL: ${captainA.page.url()}`);

    // Pause to show match page
    await captainA.page.waitForTimeout(2000);

    // Click Start Draft on both
    const startDraftButton = (page: Page) =>
      page
        .locator(
          'button:has-text("Start Draft"), button:has-text("View Draft"), button:has-text("Live Draft")'
        )
        .first();

    await Promise.all([
      startDraftButton(captainA.page).click(),
      startDraftButton(captainB.page).click(),
    ]);

    await Promise.all([
      captainA.draftPage.waitForModal(),
      captainB.draftPage.waitForModal(),
    ]);

    console.log('Draft modal opened');
    await captainA.page.waitForTimeout(1500);

    // =========================================================================
    // WAITING PHASE
    // =========================================================================
    console.log('=== WAITING PHASE ===');

    await Promise.all([
      captainA.draftPage.waitForConnection(),
      captainB.draftPage.waitForConnection(),
    ]);

    await Promise.all([
      captainA.draftPage.assertWaitingPhase(),
      captainB.draftPage.assertWaitingPhase(),
    ]);

    // Captain A clicks ready
    await captainA.draftPage.clickReady();
    console.log(`${captainA.username} ready`);
    await captainA.page.waitForTimeout(1000);

    // Captain B clicks ready
    await captainB.draftPage.clickReady();
    console.log(`${captainB.username} ready`);

    // Wait for rolling phase
    await Promise.all([
      captainA.draftPage.waitForPhaseTransition('rolling', 15000),
      captainB.draftPage.waitForPhaseTransition('rolling', 15000),
    ]);

    console.log('Both ready, rolling phase started');

    // =========================================================================
    // ROLLING PHASE
    // =========================================================================
    console.log('=== ROLLING PHASE ===');

    // Either captain can click the flip coin button
    await captainA.page.waitForTimeout(1000); // Pause for video
    const flipCoinButton = captainA.page.locator('[data-testid="herodraft-flip-coin-button"]');
    await expect(flipCoinButton).toBeVisible({ timeout: 10000 });
    await flipCoinButton.click();
    console.log('Coin flip triggered!');

    await captainA.page.waitForTimeout(1500); // Let transition happen

    // Wait for choosing phase
    await Promise.all([
      captainA.draftPage.waitForPhaseTransition('choosing', 15000),
      captainB.draftPage.waitForPhaseTransition('choosing', 15000),
    ]);

    console.log('Choosing phase started');

    // =========================================================================
    // CHOOSING PHASE
    // =========================================================================
    console.log('=== CHOOSING PHASE ===');

    // Determine who won the flip
    const winnerText = await captainA.page
      .locator('[data-testid="herodraft-flip-winner"]')
      .textContent();
    console.log(`Winner text: "${winnerText}"`);
    console.log(`Captain A username: "${captainA.username}", Captain B username: "${captainB.username}"`);

    const winnerIsA = winnerText?.includes(captainA.username);
    const winner = winnerIsA ? captainA : captainB;

    console.log(`${winner.username} won the flip!`);

    // Wait a moment for UI to update
    await winner.page.waitForTimeout(1000);

    // Winner chooses first pick
    const firstPickButton = winner.page.locator('[data-testid="herodraft-choice-first-pick"]');
    await expect(firstPickButton).toBeVisible({ timeout: 10000 });
    console.log('Winner clicking First Pick...');
    await winner.page.waitForTimeout(1000);
    await firstPickButton.click();
    console.log('Winner chose First Pick');

    // Wait for loser to see remaining choices
    const loser = winner === captainA ? captainB : captainA;
    await loser.page.waitForTimeout(1500);

    // Loser chooses side (Radiant or Dire) from remaining options
    const radiantButton = loser.page.locator('[data-testid="herodraft-remaining-radiant"]');
    await expect(radiantButton).toBeVisible({ timeout: 10000 });
    console.log('Loser clicking Radiant...');
    await loser.page.waitForTimeout(1000);
    await radiantButton.click();
    console.log('Loser chose Radiant');

    // Wait for drafting phase
    await Promise.all([
      captainA.draftPage.waitForPhaseTransition('drafting', 15000),
      captainB.draftPage.waitForPhaseTransition('drafting', 15000),
    ]);

    console.log('Drafting phase started');

    // =========================================================================
    // DRAFTING PHASE
    // =========================================================================
    console.log('=== DRAFTING PHASE ===');

    const maxRounds = 24;
    let heroIndex = 0;

    // Get hero IDs from the grid (first 30 heroes)
    const heroGrid = captainA.page.locator('[data-testid="herodraft-hero-grid"]');
    await expect(heroGrid).toBeVisible();

    const heroButtons = heroGrid.locator('[data-hero-id]');
    const heroCount = await heroButtons.count();

    const heroIds: number[] = [];
    for (let i = 0; i < Math.min(heroCount, 30); i++) {
      const heroId = await heroButtons.nth(i).getAttribute('data-hero-id');
      if (heroId) heroIds.push(parseInt(heroId));
    }

    // Winner chose "First Pick", so they are the first pick captain
    const firstPickCaptain = winner;
    const secondPickCaptain = winner === captainA ? captainB : captainA;

    console.log(`First pick: ${firstPickCaptain.username}`);

    // Draft sequence helper
    const getCurrentPicker = async (roundNum: number) => {
      // Captain's Mode draft order (first picker perspective):
      // B B B B B B B P P B B B P P P P P P B B B B P P
      const DRAFT_SEQUENCE: [boolean, string][] = [
        [true, 'ban'],
        [true, 'ban'],
        [false, 'ban'],
        [false, 'ban'],
        [true, 'ban'],
        [false, 'ban'],
        [false, 'ban'],
        [true, 'pick'],
        [false, 'pick'],
        [false, 'ban'],
        [true, 'ban'],
        [false, 'ban'],
        [true, 'pick'],
        [false, 'pick'],
        [true, 'pick'],
        [false, 'pick'],
        [true, 'pick'],
        [false, 'pick'],
        [true, 'ban'],
        [false, 'ban'],
        [true, 'ban'],
        [false, 'ban'],
        [true, 'pick'],
        [false, 'pick'],
      ];

      const [isFirstPickTeam] = DRAFT_SEQUENCE[roundNum - 1];
      return isFirstPickTeam ? firstPickCaptain : secondPickCaptain;
    };

    for (let round = 1; round <= maxRounds; round++) {
      console.log(`--- Round ${round}/${maxRounds} ---`);

      const currentPicker = await getCurrentPicker(round);
      const action = await currentPicker.draftPage.getCurrentAction();

      console.log(`${currentPicker.username} will ${action}`);

      await currentPicker.draftPage.pickHero(heroIds[heroIndex]);
      heroIndex++;

      // Wait for round completion
      const currentRound = await currentPicker.draftPage.getCurrentRound();
      const roundCompletedA = captainA.page.locator(
        `[data-testid="herodraft-round-${currentRound}"][data-round-state="completed"]`
      );
      const roundCompletedB = captainB.page.locator(
        `[data-testid="herodraft-round-${currentRound}"][data-round-state="completed"]`
      );

      try {
        await Promise.all([
          roundCompletedA.waitFor({ state: 'attached', timeout: 5000 }),
          roundCompletedB.waitFor({ state: 'attached', timeout: 5000 }),
        ]);
      } catch {
        console.log(`Round ${currentRound} completion timeout, continuing...`);
      }

      // Pause for video clarity
      await captainA.page.waitForTimeout(400);
    }

    // Final pause to show completed draft
    console.log('=== DRAFT COMPLETE ===');
    await captainA.page.waitForTimeout(5000);

    console.log(`Demo complete! ${maxRounds} rounds of hero bans and picks.`);
  });
});
