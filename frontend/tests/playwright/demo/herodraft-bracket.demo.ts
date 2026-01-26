/**
 * HeroDraft with Bracket Demo - Full Flow Video Recording
 *
 * Records a complete Captain's Mode hero draft from start to finish,
 * accessed from the tournament bracket. Shows both captains' perspectives.
 *
 * Video output: 1:1 aspect ratio (800x800) for docs and social media.
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

const API_URL = 'https://localhost/api';
const BASE_URL = 'https://localhost';

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
    // Demo always runs headed for video quality
    const browserOptions = {
      headless: false,
      slowMo: 100, // Slow for demo visibility
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

    const contextA = await browserA.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowSize, height: windowSize },
      recordVideo: {
        dir: 'demo-results/videos/',
        size: { width: windowSize, height: windowSize },
      },
    });

    const contextB = await browserB.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowSize, height: windowSize },
      recordVideo: {
        dir: 'demo-results/videos/',
        size: { width: windowSize, height: windowSize },
      },
    });

    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    // Fetch draft info
    const response = await contextA.request.get(
      `${API_URL}/tests/herodraft-by-key/two_captain_test/`,
      { failOnStatusCode: false, timeout: 10000 }
    );

    if (!response.ok()) {
      throw new Error(
        `Failed to get HeroDraft test data. Run 'inv db.populate.all' first.`
      );
    }

    testInfo = await response.json();

    // Reset the draft
    await contextA.request.post(
      `${API_URL}/tests/herodraft/${testInfo.pk}/reset/`,
      { failOnStatusCode: false }
    );

    const teams = testInfo.draft_teams;

    // Login both captains
    await loginAsDiscordId(contextA, teams[0].captain.discordId);
    await loginAsDiscordId(contextB, teams[1].captain.discordId);

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
    // Save videos before closing
    if (captainA?.context) {
      await captainA.context.close();
    }
    if (captainB?.context) {
      await captainB.context.close();
    }
    await browserA?.close();
    await browserB?.close();
  });

  test('Complete HeroDraft from Tournament Bracket', async () => {
    test.setTimeout(600_000); // 10 minutes for full draft

    const tournamentPk = testInfo.game?.tournament_pk;
    const gamePk = testInfo.game?.pk;

    if (!tournamentPk || !gamePk) {
      throw new Error('Tournament or Game PK not available');
    }

    // Navigate to match page from bracket
    const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

    console.log('=== DEMO START ===');
    console.log(`Match URL: ${matchUrl}`);

    // Navigate both captains to match page
    await Promise.all([
      captainA.page.goto(matchUrl),
      captainB.page.goto(matchUrl),
    ]);

    await Promise.all([
      waitForHydration(captainA.page),
      waitForHydration(captainB.page),
    ]);

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
    await captainA.page.waitForTimeout(1500);

    // =========================================================================
    // ROLLING PHASE
    // =========================================================================
    console.log('=== ROLLING PHASE ===');

    await captainA.draftPage.flipCoinButton.waitFor({
      state: 'visible',
      timeout: 5000,
    });
    await captainA.draftPage.clickFlipCoin();
    console.log('Coin flipped!');

    // Wait for choosing phase
    await Promise.all([
      captainA.draftPage.waitForPhaseTransition('choosing', 10000),
      captainB.draftPage.waitForPhaseTransition('choosing', 10000),
    ]);

    console.log('Choosing phase started');
    await captainA.page.waitForTimeout(1500);

    // =========================================================================
    // CHOOSING PHASE
    // =========================================================================
    console.log('=== CHOOSING PHASE ===');

    const winnerChoices = captainA.page.locator(
      '[data-testid="herodraft-winner-choices"]'
    );
    const isAWinner = await winnerChoices.isVisible().catch(() => false);

    if (isAWinner) {
      console.log(`${captainA.username} won the flip!`);
      await captainA.draftPage.selectWinnerChoice('first_pick');
      await captainA.page.waitForTimeout(1000);

      const loserChoices = captainB.page.locator(
        '[data-testid="herodraft-loser-choices"]'
      );
      await loserChoices.waitFor({ state: 'visible', timeout: 5000 });
      await captainB.draftPage.selectLoserChoice('radiant');
    } else {
      console.log(`${captainB.username} won the flip!`);
      await captainB.draftPage.selectWinnerChoice('first_pick');
      await captainB.page.waitForTimeout(1000);

      const loserChoices = captainA.page.locator(
        '[data-testid="herodraft-loser-choices"]'
      );
      await loserChoices.waitFor({ state: 'visible', timeout: 5000 });
      await captainA.draftPage.selectLoserChoice('radiant');
    }

    // Wait for drafting phase
    await Promise.all([
      captainA.draftPage.waitForPhaseTransition('drafting', 10000),
      captainB.draftPage.waitForPhaseTransition('drafting', 10000),
    ]);

    console.log('Drafting phase started');
    await captainA.page.waitForTimeout(2000);

    // =========================================================================
    // DRAFTING PHASE - 24 rounds
    // =========================================================================
    console.log('=== DRAFTING PHASE ===');

    // Valid Dota 2 hero IDs (skip 24 as it doesn't exist)
    const heroIds = [
      1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
      22, 23, 25, 26, 27, 28, 29, 30, 31,
    ];
    let heroIndex = 0;

    // Captain's Mode: 14 bans + 10 picks = 24 rounds
    const maxRounds = 24;

    // Determine first pick captain from visual indicator
    let firstPickCaptain: CaptainContext = captainA;
    let secondPickCaptain: CaptainContext = captainB;
    let firstPickDetermined = false;

    const getCurrentPicker = async (
      roundNum: number
    ): Promise<CaptainContext> => {
      const teamAIndicator = captainA.page.locator(
        '[data-testid="herodraft-team-a-picking"]'
      );
      const teamBIndicator = captainA.page.locator(
        '[data-testid="herodraft-team-b-picking"]'
      );

      const startTime = Date.now();
      while (Date.now() - startTime < 1000) {
        const teamAPicking = await teamAIndicator.isVisible().catch(() => false);
        const teamBPicking = await teamBIndicator.isVisible().catch(() => false);

        if (teamAPicking || teamBPicking) {
          const picker = teamAPicking ? captainA : captainB;

          if (roundNum === 1 && !firstPickDetermined) {
            firstPickCaptain = picker;
            secondPickCaptain = picker === captainA ? captainB : captainA;
            firstPickDetermined = true;
            console.log(`First pick: ${firstPickCaptain.username}`);
          }

          return picker;
        }
        await captainA.page.waitForTimeout(100);
      }

      // Fallback to sequence
      const DRAFT_SEQUENCE: Array<[boolean, string]> = [
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
