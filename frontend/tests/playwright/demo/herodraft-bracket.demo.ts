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
import { waitForDemoReady, waitForHeroDraftReady, waitForMatchModalReady } from '../fixtures/demo-utils';
import { HeroDraftPage } from '../helpers/HeroDraftPage';
import * as path from 'path';
import * as fs from 'fs/promises';
import { fileURLToPath } from 'url';

// ESM-compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Use nginx hostname inside Docker containers, localhost for local runs
const DOCKER_HOST = process.env.DOCKER_HOST || 'nginx';
const API_URL = `https://${DOCKER_HOST}/api`;
const BASE_URL = `https://${DOCKER_HOST}`;
const VIDEO_OUTPUT_DIR = 'demo-results/videos';
const DOCS_VIDEO_DIR = path.resolve(__dirname, '../../../docs/assets/videos');

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

  test.afterAll(async () => {
    // Get video paths before closing pages
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

    // Copy videos to both demo-results and docs/assets/videos
    await fs.mkdir(DOCS_VIDEO_DIR, { recursive: true });

    try {
      if (videoPathA) {
        const destA = path.join(VIDEO_OUTPUT_DIR, 'captain1_herodraft.webm');
        const docsDestA = path.join(DOCS_VIDEO_DIR, 'captain1_herodraft.webm');
        await fs.copyFile(videoPathA, destA);
        await fs.copyFile(videoPathA, docsDestA);
        console.log(`Saved: captain1_herodraft.webm (demo-results + docs/assets/videos)`);
      }
      if (videoPathB) {
        const destB = path.join(VIDEO_OUTPUT_DIR, 'captain2_herodraft.webm');
        const docsDestB = path.join(DOCS_VIDEO_DIR, 'captain2_herodraft.webm');
        await fs.copyFile(videoPathB, destB);
        await fs.copyFile(videoPathB, docsDestB);
        console.log(`Saved: captain2_herodraft.webm (demo-results + docs/assets/videos)`);
      }
    } catch (e) {
      console.error('Error copying videos:', e);
    }
  });

  test('Complete HeroDraft from Tournament Bracket', async () => {
    test.setTimeout(600_000); // 10 minutes for full draft

    // Use system chromium in Docker (Alpine)
    const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined;
    const browserOptions = {
      headless: true,
      slowMo: 100,
      ...(executablePath && { executablePath }),
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

    const windowSize = 800;

    // =========================================================================
    // PHASE 1: Setup (no video) - complete waiting phase, get to rolling phase
    // =========================================================================
    console.log('=== PHASE 1: Setup (no recording) ===');

    const setupContextA = await browserA.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowSize, height: windowSize },
    });
    const setupContextB = await browserB.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowSize, height: windowSize },
    });

    // Inject playwright marker
    await setupContextA.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });
    await setupContextB.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });

    // Fetch draft info
    const response = await setupContextA.request.get(
      `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
      { failOnStatusCode: false, timeout: 10000 }
    );

    if (!response.ok()) {
      await setupContextA.close();
      await setupContextB.close();
      throw new Error(`Failed to get HeroDraft test data. Run 'inv db.populate.all' first.`);
    }

    testInfo = await response.json();

    // Reset the draft
    await setupContextA.request.post(
      `${API_URL}/tests/herodraft/${testInfo.pk}/reset/`,
      { failOnStatusCode: false }
    );

    const teams = testInfo.draft_teams;
    const herodraftUrl = `${BASE_URL}/herodraft/${testInfo.pk}`;

    console.log(`Draft ID: ${testInfo.pk}`);
    console.log(`Captain A: ${teams[0].captain.username} (${teams[0].team_name})`);
    console.log(`Captain B: ${teams[1].captain.username} (${teams[1].team_name})`);

    // Login both captains
    console.log(`Login: Captain A Discord ID: ${teams[0].captain.discordId}`);
    const loginResultA = await loginAsDiscordId(setupContextA, teams[0].captain.discordId);
    console.log(`Login: Captain A result:`, JSON.stringify(loginResultA));
    const cookiesA = await setupContextA.cookies();
    console.log(`Login: Captain A cookies:`, JSON.stringify(cookiesA, null, 2));

    console.log(`Login: Captain B Discord ID: ${teams[1].captain.discordId}`);
    const loginResultB = await loginAsDiscordId(setupContextB, teams[1].captain.discordId);
    console.log(`Login: Captain B result:`, JSON.stringify(loginResultB));
    const cookiesB = await setupContextB.cookies();
    console.log(`Login: Captain B cookies:`, JSON.stringify(cookiesB, null, 2));

    const setupPageA = await setupContextA.newPage();
    const setupPageB = await setupContextB.newPage();

    // Navigate directly to herodraft URL
    await Promise.all([setupPageA.goto(herodraftUrl), setupPageB.goto(herodraftUrl)]);
    await Promise.all([waitForHydration(setupPageA), waitForHydration(setupPageB)]);

    const setupDraftA = new HeroDraftPage(setupPageA);
    const setupDraftB = new HeroDraftPage(setupPageB);

    // Wait for connection
    await Promise.all([
      setupDraftA.waitForConnection(),
      setupDraftB.waitForConnection(),
    ]);

    // Complete waiting phase - both click ready
    console.log('Setup: Completing waiting phase...');
    await Promise.all([
      setupDraftA.assertWaitingPhase(),
      setupDraftB.assertWaitingPhase(),
    ]);

    // Dismiss any active drafts banners that may block interaction
    // Use Escape key repeatedly until no dialogs/banners are visible
    const dismissAllOverlays = async (page: Page, name: string) => {
      // First try clicking dismiss banner buttons
      let attempts = 0;
      while (attempts < 5) {
        const dismissBtn = page.locator('button:has-text("Dismiss banner")');
        const dialog = page.locator('[role="dialog"], [role="alertdialog"]');

        if (await dismissBtn.isVisible().catch(() => false)) {
          console.log(`Setup: Dismissing banner for ${name}...`);
          await dismissBtn.click({ force: true });
          await page.waitForTimeout(300);
        } else if (await dialog.isVisible().catch(() => false)) {
          console.log(`Setup: Closing dialog for ${name} with Escape...`);
          await page.keyboard.press('Escape');
          await page.waitForTimeout(300);
        } else {
          break;
        }
        attempts++;
      }
    };

    await dismissAllOverlays(setupPageA, teams[0].captain.username);
    await dismissAllOverlays(setupPageB, teams[1].captain.username);

    // Click ready with retry logic and overlay dismissal
    const clickReadyWithRetry = async (page: Page, name: string, maxRetries = 5) => {
      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        // Always dismiss overlays before each attempt
        await dismissAllOverlays(page, name);

        try {
          console.log(`Setup: ${name} clicking ready (attempt ${attempt})...`);

          // First verify we're in the waiting phase
          const waitingPhase = page.locator('[data-testid="herodraft-waiting-phase"]');
          if (!await waitingPhase.isVisible().catch(() => false)) {
            // Maybe already in rolling phase?
            const rollingPhase = page.locator('[data-testid="herodraft-rolling-phase"]');
            if (await rollingPhase.isVisible().catch(() => false)) {
              console.log(`Setup: ${name} already in rolling phase, skipping ready`);
              return;
            }
            console.log(`Setup: ${name} not in waiting phase yet, waiting...`);
            await waitingPhase.waitFor({ state: 'visible', timeout: 10000 });
          }

          const readyBtn = page.locator('[data-testid="herodraft-ready-button"]');

          // Wait for ready button to appear (it only shows for captains who haven't clicked ready)
          console.log(`Setup: ${name} waiting for ready button...`);
          await readyBtn.waitFor({ state: 'visible', timeout: 10000 });
          console.log(`Setup: ${name} ready button is visible`);

          // Set up response listener BEFORE clicking
          const responsePromise = page.waitForResponse(
            (response) => response.url().includes('/set-ready/') && response.status() === 200,
            { timeout: 15000 }
          );

          // Use Playwright's native click with force to bypass any overlays
          await readyBtn.click({ force: true });
          console.log(`Setup: ${name} clicked ready button, waiting for API response...`);

          // Wait for the API call to complete
          const response = await responsePromise;
          console.log(`Setup: ${name} set-ready API returned ${response.status()}`);

          // Wait for button to disappear (indicates ready state was accepted by UI)
          await readyBtn.waitFor({ state: 'hidden', timeout: 5000 });
          console.log(`Setup: ${name} ready confirmed - button hidden`);
          return;
        } catch (e) {
          console.log(`Setup: ${name} ready attempt ${attempt} failed: ${e}`);
          if (attempt === maxRetries) {
            // Debug: capture page state
            const pageUrl = page.url();
            const waitingVisible = await page.locator('[data-testid="herodraft-waiting-phase"]').isVisible().catch(() => false);
            const readyBtnVisible = await page.locator('[data-testid="herodraft-ready-button"]').isVisible().catch(() => false);
            console.log(`Setup: Debug - URL: ${pageUrl}, waiting phase visible: ${waitingVisible}, ready btn visible: ${readyBtnVisible}`);
            throw new Error(`Failed to click ready for ${name} after ${maxRetries} attempts: ${e}`);
          }
          await page.waitForTimeout(2000);
        }
      }
    };

    await clickReadyWithRetry(setupPageA, teams[0].captain.username);
    await setupPageA.waitForTimeout(1000);

    // Dismiss any new banners that appeared after captain A clicked ready
    await dismissAllOverlays(setupPageB, teams[1].captain.username);
    await setupPageB.waitForTimeout(500);

    await clickReadyWithRetry(setupPageB, teams[1].captain.username);
    await setupPageB.waitForTimeout(500);

    // Wait for rolling phase
    await Promise.all([
      setupDraftA.waitForPhaseTransition('rolling', 15000),
      setupDraftB.waitForPhaseTransition('rolling', 15000),
    ]);
    console.log('Setup: Rolling phase reached');

    // Wait for flip coin button to be visible on both pages
    const flipCoinSelector = '[data-testid="herodraft-flip-coin-button"]';
    await Promise.all([
      setupPageA.locator(flipCoinSelector).waitFor({ state: 'visible', timeout: 10000 }),
      setupPageB.locator(flipCoinSelector).waitFor({ state: 'visible', timeout: 10000 }),
    ]);
    console.log('Setup: Flip coin button visible on both pages');

    // Save storage state for video contexts
    const storageStateA = await setupContextA.storageState();
    const storageStateB = await setupContextB.storageState();

    // Close setup contexts
    await setupPageA.close();
    await setupPageB.close();
    await setupContextA.close();
    await setupContextB.close();

    // =========================================================================
    // PHASE 2: Video recording - start with both at rolling phase
    // =========================================================================
    console.log('=== PHASE 2: Video Recording (synchronized start) ===');

    // Create video contexts with storage state
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

    // Inject playwright marker
    await contextA.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });
    await contextB.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });

    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    // Navigate both to herodraft page simultaneously - VIDEO STARTS HERE
    console.log('Video: Starting synchronized navigation...');
    await Promise.all([pageA.goto(herodraftUrl), pageB.goto(herodraftUrl)]);
    await Promise.all([waitForHydration(pageA), waitForHydration(pageB)]);

    // Wait for hero grid to load on both
    await Promise.all([
      waitForHeroDraftReady(pageA, { timeout: 30000 }),
      waitForHeroDraftReady(pageB, { timeout: 30000 }),
    ]);

    // Wait for flip coin button on both
    await Promise.all([
      pageA.locator(flipCoinSelector).waitFor({ state: 'visible', timeout: 10000 }),
      pageB.locator(flipCoinSelector).waitFor({ state: 'visible', timeout: 10000 }),
    ]);
    console.log('Video: Both pages loaded at rolling phase - recording synced');

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

    // Brief pause for synchronized video start
    await Promise.all([
      pageA.waitForTimeout(1000),
      pageB.waitForTimeout(1000),
    ]);

    console.log('=== DEMO START (Rolling Phase) ===');

    // =========================================================================
    // ROLLING PHASE (Video recording already started)
    // =========================================================================
    console.log('=== ROLLING PHASE ===');

    // Pause for video - show the rolling phase UI
    await captainA.page.waitForTimeout(1500);

    // Either captain can click the flip coin button
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
