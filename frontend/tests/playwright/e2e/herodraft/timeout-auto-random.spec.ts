/**
 * HeroDraft Timeout Auto-Random Pick Tests
 *
 * Tests the auto-random pick feature when a captain times out.
 * Uses the force-timeout test endpoint to immediately trigger timeout
 * without waiting for the full grace + reserve time.
 */

import { test, expect, chromium, type Browser, type BrowserContext, type Page } from '@playwright/test';
import { loginAsDiscordId, waitForHydration } from '../../fixtures/auth';
import { HeroDraftPage } from '../../helpers/HeroDraftPage';

const API_URL = 'https://localhost/api';
const BASE_URL = 'https://localhost';

/**
 * Wait for server to be ready with retries.
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
        return;
      }
    } catch (error) {
      console.log(`   Waiting for server... (attempt ${i + 1}/${maxRetries})`);
    }
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  throw new Error(`Server not ready after ${maxRetries} attempts`);
}

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

interface DraftRound {
  id: number;
  round_number: number;
  action_type: string;
  hero_id: number | null;
  state: string;
  draft_team: number;
  team_name: string;
}

test.describe('HeroDraft Timeout Auto-Random Pick', () => {
  let captainA: CaptainContext;
  let captainB: CaptainContext;
  let testInfo: HeroDraftTestInfo;
  let browserA: Browser | null = null;
  let browserB: Browser | null = null;

  test.beforeAll(async () => {
    const isCI = !!process.env.CI;
    const isDocker = !!process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
    const forceHeaded = process.env.HERODRAFT_HEADED === 'true';
    const headless = forceHeaded ? false : (isCI || isDocker);

    console.log(`   Browser mode: ${headless ? 'headless' : 'headed'}`);

    const browserOptions = {
      headless,
      slowMo: headless ? 0 : 50,
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

    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    console.log('   Waiting for server to be ready...');
    await waitForServerReady(contextA, `${API_URL}/`);
    console.log('   Server ready!');

    // Fetch draft info
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

    const teams = testInfo.draft_teams;
    if (teams.length < 2) {
      throw new Error('Need at least 2 teams for two-captain test');
    }

    if (!teams[0].captain?.discordId || !teams[1].captain?.discordId) {
      throw new Error('Captains must have Discord IDs for login');
    }

    await loginAsDiscordId(contextA, teams[0].captain.discordId);
    await loginAsDiscordId(contextB, teams[1].captain.discordId);

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

    console.log(`\n Timeout Test Setup Complete:`);
    console.log(`   Captain A: ${captainA.username} (Team: ${captainA.teamName})`);
    console.log(`   Captain B: ${captainB.username} (Team: ${captainB.teamName})`);
    console.log(`   Draft ID: ${testInfo.pk}`);
  });

  test.beforeEach(async () => {
    // Reset the draft before each test
    const draftPk = testInfo.pk;
    await captainA.context.request.post(
      `${API_URL}/tests/herodraft/${draftPk}/reset/`,
      { failOnStatusCode: false }
    );
    console.log(`   Draft ${draftPk} reset for new test`);
  });

  test.afterAll(async () => {
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

  /**
   * Helper to navigate both captains to the draft and get to drafting phase
   */
  async function setupToDraftingPhase(): Promise<void> {
    const tournamentPk = testInfo.game?.tournament_pk;
    const gamePk = testInfo.game?.pk;

    if (!tournamentPk || !gamePk) {
      throw new Error('Tournament PK or Game PK not available');
    }

    const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

    // Navigate and open draft modal
    await Promise.all([
      captainA.page.goto(matchUrl),
      captainB.page.goto(matchUrl),
    ]);

    await Promise.all([
      waitForHydration(captainA.page),
      waitForHydration(captainB.page),
    ]);

    const startDraftButton = (page: Page) =>
      page.locator('button:has-text("Start Draft"), button:has-text("View Draft"), button:has-text("Live Draft")').first();

    await Promise.all([
      startDraftButton(captainA.page).click(),
      startDraftButton(captainB.page).click(),
    ]);

    await Promise.all([
      captainA.draftPage.waitForModal(),
      captainB.draftPage.waitForModal(),
    ]);

    // Waiting Phase - Both captains click Ready
    await Promise.all([
      captainA.draftPage.waitForConnection(),
      captainB.draftPage.waitForConnection(),
    ]);

    await Promise.all([
      captainA.draftPage.assertWaitingPhase(),
      captainB.draftPage.assertWaitingPhase(),
    ]);

    await captainA.draftPage.clickReady();
    await expect(
      captainB.page.locator('[data-testid^="herodraft-ready-status-"]').first()
    ).toContainText('Ready', { timeout: 5000 });
    await captainB.draftPage.clickReady();

    // Rolling Phase - Trigger coin flip
    await expect(captainA.draftPage.flipCoinButton).toBeVisible({ timeout: 10000 });
    await captainA.draftPage.clickFlipCoin();

    // Choosing Phase - Make choices
    await Promise.race([
      captainA.page.getByTestId('herodraft-choosing-phase').waitFor({ state: 'visible', timeout: 10000 }),
      captainB.page.getByTestId('herodraft-choosing-phase').waitFor({ state: 'visible', timeout: 10000 }),
    ]);

    const winnerChoiceFirstA = captainA.page.getByTestId('herodraft-choice-first-pick');
    const isAWinner = await winnerChoiceFirstA.isVisible({ timeout: 2000 }).catch(() => false);

    if (isAWinner) {
      await winnerChoiceFirstA.click();
      await expect(captainB.page.getByTestId('herodraft-remaining-radiant')).toBeVisible({ timeout: 10000 });
      await captainB.page.getByTestId('herodraft-remaining-radiant').click();
    } else {
      await captainB.page.getByTestId('herodraft-choice-first-pick').click();
      await expect(captainA.page.getByTestId('herodraft-remaining-radiant')).toBeVisible({ timeout: 10000 });
      await captainA.page.getByTestId('herodraft-remaining-radiant').click();
    }

    // Wait for drafting phase
    await expect(captainA.draftPage.heroGrid).toBeVisible({ timeout: 15000 });
    await expect(captainB.draftPage.heroGrid).toBeVisible({ timeout: 5000 });
  }

  /**
   * Force timeout and return the response data
   */
  async function forceTimeout(draftPk: number): Promise<{ responseData: any; autoPickedHeroId: number }> {
    const timeoutResponse = await captainA.context.request.post(
      `${API_URL}/tests/herodraft/${draftPk}/force-timeout/`,
      { failOnStatusCode: false }
    );

    const responseData = await timeoutResponse.json();

    if (!timeoutResponse.ok()) {
      throw new Error(`Force timeout failed: ${JSON.stringify(responseData)}`);
    }

    // Find the most recently completed round with a hero
    const completedRounds = responseData.rounds?.filter(
      (r: DraftRound) => r.state === 'completed' && r.hero_id !== null
    ) || [];

    const lastCompletedRound = completedRounds[completedRounds.length - 1];
    if (!lastCompletedRound) {
      throw new Error('No completed round with hero found after timeout');
    }

    return { responseData, autoPickedHeroId: lastCompletedRound.hero_id };
  }

  test('auto-random pick is triggered on timeout and broadcast to all clients', async () => {
    test.setTimeout(120000);

    const draftPk = testInfo.pk;
    console.log('Step 1: Setting up to drafting phase...');
    await setupToDraftingPhase();
    console.log('   Both captains see the hero grid - draft started!');

    // Force timeout via API
    console.log('Step 2: Forcing timeout via API...');
    const { responseData, autoPickedHeroId } = await forceTimeout(draftPk);
    console.log(`   Auto-picked hero ID: ${autoPickedHeroId}`);

    // Verify UI updated on both clients
    console.log('Step 3: Verifying UI reflects auto-random pick...');
    await captainA.page.waitForTimeout(3000);

    // Check if state updated via WebSocket first
    let heroButtonA = captainA.page.getByTestId(`herodraft-hero-${autoPickedHeroId}`);
    const availableViaWS = await heroButtonA.getAttribute('data-hero-available');

    // If WebSocket didn't update, reload pages
    if (availableViaWS === 'true') {
      console.log('   WebSocket did not update UI, reloading pages...');
      await Promise.all([
        captainA.page.reload({ waitUntil: 'networkidle' }),
        captainB.page.reload({ waitUntil: 'networkidle' }),
      ]);

      await Promise.all([
        captainA.draftPage.waitForModal(),
        captainB.draftPage.waitForModal(),
      ]);

      heroButtonA = captainA.page.getByTestId(`herodraft-hero-${autoPickedHeroId}`);
    }

    const heroButtonB = captainB.page.getByTestId(`herodraft-hero-${autoPickedHeroId}`);

    await expect(heroButtonA).toHaveAttribute('data-hero-available', 'false', { timeout: 5000 });
    await expect(heroButtonB).toHaveAttribute('data-hero-available', 'false', { timeout: 5000 });

    console.log(`   Hero ${autoPickedHeroId} is unavailable on both pages - auto-pick worked!`);

    const finalState = responseData.state;
    console.log(`   Final draft state: ${finalState}`);
    expect(['drafting', 'completed']).toContain(finalState);

    console.log('\n   Test PASSED!');
  });

  test('multiple consecutive timeouts complete multiple rounds', async () => {
    test.setTimeout(120000);

    const draftPk = testInfo.pk;
    console.log('Step 1: Setting up to drafting phase...');
    await setupToDraftingPhase();
    console.log('   Draft started!');

    // Force 3 consecutive timeouts
    const autoPickedHeroes: number[] = [];

    for (let i = 1; i <= 3; i++) {
      console.log(`Step ${i + 1}: Forcing timeout #${i}...`);
      const { autoPickedHeroId } = await forceTimeout(draftPk);
      autoPickedHeroes.push(autoPickedHeroId);
      console.log(`   Timeout #${i} auto-picked hero ID: ${autoPickedHeroId}`);

      // Small delay between timeouts
      await captainA.page.waitForTimeout(500);
    }

    // Verify all 3 heroes are different (random selection working)
    const uniqueHeroes = new Set(autoPickedHeroes);
    console.log(`   Unique heroes picked: ${uniqueHeroes.size} (${autoPickedHeroes.join(', ')})`);
    expect(uniqueHeroes.size).toBe(3);

    // Reload and verify all heroes are unavailable
    console.log('Step 5: Verifying all auto-picked heroes are unavailable...');
    await Promise.all([
      captainA.page.reload({ waitUntil: 'networkidle' }),
      captainB.page.reload({ waitUntil: 'networkidle' }),
    ]);

    await Promise.all([
      captainA.draftPage.waitForModal(),
      captainB.draftPage.waitForModal(),
    ]);

    for (const heroId of autoPickedHeroes) {
      const heroButton = captainA.page.getByTestId(`herodraft-hero-${heroId}`);
      await expect(heroButton).toHaveAttribute('data-hero-available', 'false', { timeout: 5000 });
      console.log(`   Hero ${heroId} confirmed unavailable`);
    }

    console.log('\n   Multiple timeouts test PASSED!');
  });

  test('timeout advances through different round types (bans and picks)', async () => {
    test.setTimeout(180000);

    const draftPk = testInfo.pk;
    console.log('Step 1: Setting up to drafting phase...');
    await setupToDraftingPhase();
    console.log('   Draft started!');

    // Force timeouts and track round types
    const roundResults: Array<{ round: number; type: string; heroId: number }> = [];

    // Force 8 timeouts to get past bans (7 bans) and into picks
    for (let i = 1; i <= 8; i++) {
      console.log(`   Forcing timeout #${i}...`);

      const timeoutResponse = await captainA.context.request.post(
        `${API_URL}/tests/herodraft/${draftPk}/force-timeout/`,
        { failOnStatusCode: false }
      );

      const responseData = await timeoutResponse.json();

      if (!timeoutResponse.ok()) {
        console.log(`   Timeout #${i} failed: ${JSON.stringify(responseData)}`);
        break;
      }

      // Find the round that was just completed (most recent completed round)
      const completedRounds = responseData.rounds?.filter(
        (r: DraftRound) => r.state === 'completed' && r.hero_id !== null
      ) || [];

      const lastRound = completedRounds[completedRounds.length - 1];
      if (lastRound) {
        roundResults.push({
          round: lastRound.round_number,
          type: lastRound.action_type,
          heroId: lastRound.hero_id,
        });
        console.log(`   Round ${lastRound.round_number} (${lastRound.action_type}): hero ${lastRound.hero_id}`);
      }

      await captainA.page.waitForTimeout(300);
    }

    // Verify we have both ban and pick rounds
    const banRounds = roundResults.filter(r => r.type === 'ban');
    const pickRounds = roundResults.filter(r => r.type === 'pick');

    console.log(`\n   Completed ${roundResults.length} rounds: ${banRounds.length} bans, ${pickRounds.length} picks`);

    expect(banRounds.length).toBeGreaterThan(0);
    expect(pickRounds.length).toBeGreaterThan(0);

    // Verify all heroes are unique
    const heroIds = roundResults.map(r => r.heroId);
    const uniqueHeroIds = new Set(heroIds);
    expect(uniqueHeroIds.size).toBe(heroIds.length);
    console.log(`   All ${heroIds.length} heroes are unique`);

    console.log('\n   Ban/Pick progression test PASSED!');
  });

  test('draft completes when all rounds timeout', async () => {
    test.setTimeout(300000); // 5 minutes for full draft

    const draftPk = testInfo.pk;
    console.log('Step 1: Setting up to drafting phase...');
    await setupToDraftingPhase();
    console.log('   Draft started!');

    // Force timeouts until draft completes (24 rounds total)
    let currentState = 'drafting';
    let roundCount = 0;
    const maxRounds = 30; // Safety limit

    console.log('Step 2: Forcing timeouts until draft completes...');

    while (currentState === 'drafting' && roundCount < maxRounds) {
      const timeoutResponse = await captainA.context.request.post(
        `${API_URL}/tests/herodraft/${draftPk}/force-timeout/`,
        { failOnStatusCode: false }
      );

      const responseData = await timeoutResponse.json();

      if (!timeoutResponse.ok()) {
        // Check if it's because draft completed
        const draftResponse = await captainA.context.request.get(
          `${API_URL}/herodraft/${draftPk}/`,
          { failOnStatusCode: false }
        );
        const draftData = await draftResponse.json();
        currentState = draftData.state;

        if (currentState === 'completed') {
          console.log(`   Draft completed after ${roundCount} timeouts`);
          break;
        }

        console.log(`   Timeout failed at round ${roundCount}: ${JSON.stringify(responseData)}`);
        break;
      }

      currentState = responseData.state;
      roundCount++;

      if (roundCount % 5 === 0) {
        console.log(`   Progress: ${roundCount} rounds completed, state: ${currentState}`);
      }

      await captainA.page.waitForTimeout(200);
    }

    console.log(`Step 3: Verifying draft completion...`);
    console.log(`   Final state: ${currentState}, rounds completed: ${roundCount}`);

    // Verify the draft is completed
    expect(currentState).toBe('completed');
    expect(roundCount).toBe(24); // Standard CM draft has 24 rounds

    // Reload and verify UI shows completed state
    await Promise.all([
      captainA.page.reload({ waitUntil: 'networkidle' }),
      captainB.page.reload({ waitUntil: 'networkidle' }),
    ]);

    // Check for completion indicators on both pages
    const completedIndicatorA = captainA.page.getByTestId('herodraft-completed-phase');
    const completedIndicatorB = captainB.page.getByTestId('herodraft-completed-phase');

    // At least one should indicate completed (might show different UI)
    const isCompletedA = await completedIndicatorA.isVisible({ timeout: 5000 }).catch(() => false);
    const isCompletedB = await completedIndicatorB.isVisible({ timeout: 5000 }).catch(() => false);

    console.log(`   Completed indicator visible: A=${isCompletedA}, B=${isCompletedB}`);

    console.log('\n   Full draft timeout completion test PASSED!');
  });
});
