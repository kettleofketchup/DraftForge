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
 *
 * Chat: one unrecorded team member per side suggests heroes (right-click) and
 * talks in team chat; captains open chat with Enter, trade /all lines and
 * answer their own team. Timestamps land in herodraft.demo.yaml (chat_clip)
 * for `just demo::clips`.
 */

import {
  chromium,
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import * as fs from 'fs/promises';
import * as path from 'path';
import { fileURLToPath } from 'url';
import {
  API_URL,
  loginAsDiscordId,
  loginAsUser,
  waitForHydration,
} from '../fixtures/auth';
import { BASE_URL } from '../fixtures/base-url';
import { HeroDraftPage } from '../helpers/HeroDraftPage';

// ESM-compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const VIDEO_OUTPUT_DIR = 'demo-results/videos';
const DOCS_VIDEO_DIR = path.resolve(__dirname, '../../../docs/assets/videos');
const DEMO_METADATA_FILE = path.join(VIDEO_OUTPUT_DIR, 'herodraft.demo.yaml');

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
    member_pks: number[];
  }>;
}

interface MemberContext {
  context: BrowserContext;
  page: Page;
}

const CHAT_TYPE_DELAY_MS = 35;

function chatInput(page: Page) {
  return page.getByTestId('herodraft-chat-input');
}

function chatRowWith(page: Page, text: string) {
  return page
    .locator('[data-testid^="herodraft-chat-message-"]')
    .filter({ hasText: text });
}

function suggestionRow(
  page: Page,
  kind: 'suggest_pick' | 'suggest_ban',
  heroId: number,
) {
  return page.locator(
    `[data-testid^="herodraft-chat-message-"][data-kind="${kind}"][data-hero-id="${heroId}"]`,
  );
}

/** Enter with nothing focused opens the chat panel and focuses the composer. */
async function openChatWithEnter(page: Page): Promise<void> {
  await expect(page.getByTestId('herodraft-chat-enter-hint')).toBeVisible();
  await page.evaluate(() =>
    (document.activeElement as HTMLElement | null)?.blur(),
  );
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('herodraft-chat-panel')).toBeVisible();
  await expect(chatInput(page)).toBeFocused();
}

/** Types into the focused composer at a readable pace and sends with Enter. */
async function typeChat(page: Page, text: string): Promise<void> {
  const input = chatInput(page);
  await expect(input).toBeFocused();
  await page.keyboard.type(text, { delay: CHAT_TYPE_DELAY_MS });
  await page.keyboard.press('Enter');
  await expect(input).toHaveValue('');
}

async function memberSendChat(page: Page, text: string): Promise<void> {
  const input = chatInput(page);
  await expect(input).toBeEnabled({ timeout: 15000 });
  await input.fill(text);
  await input.press('Enter');
  await expect(input).toHaveValue('');
}

async function memberSuggest(
  page: Page,
  heroId: number,
  kind: 'suggest_pick' | 'suggest_ban',
): Promise<void> {
  const hero = page.getByTestId(`herodraft-hero-${heroId}`);
  await hero.scrollIntoViewIfNeeded();
  await hero.click({ button: 'right' });
  const menu = page.getByTestId('herodraft-hero-suggest-menu');
  await expect(menu).toBeVisible();
  await page
    .getByTestId(
      kind === 'suggest_pick'
        ? 'herodraft-hero-suggest-pick'
        : 'herodraft-hero-suggest-ban',
    )
    .click();
  await expect(menu).toBeHidden();
}

async function closeChat(page: Page): Promise<void> {
  const panel = page.getByTestId('herodraft-chat-panel');
  if (!(await panel.isVisible())) return;
  await page.getByTestId('herodraft-chat-toggle').click();
  await expect(panel).toBeHidden();
}

test.describe('HeroDraft with Bracket Demo', () => {
  let captainA: CaptainContext;
  let captainB: CaptainContext;
  let testInfo: HeroDraftTestInfo;

  // Store browsers at top level for cleanup
  let browserA: Browser | null = null;
  let browserB: Browser | null = null;
  const members: MemberContext[] = [];

  test.afterAll(async () => {
    for (const member of members) {
      await member.context.close().catch(() => {});
    }

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
        console.log(
          `Saved: captain1_herodraft.webm (demo-results + docs/assets/videos)`,
        );
      }
      if (videoPathB) {
        const destB = path.join(VIDEO_OUTPUT_DIR, 'captain2_herodraft.webm');
        const docsDestB = path.join(DOCS_VIDEO_DIR, 'captain2_herodraft.webm');
        await fs.copyFile(videoPathB, destB);
        await fs.copyFile(videoPathB, docsDestB);
        console.log(
          `Saved: captain2_herodraft.webm (demo-results + docs/assets/videos)`,
        );
      }
    } catch (e) {
      console.error('Error copying videos:', e);
    }
  });

  test('Complete HeroDraft from Tournament Bracket', async () => {
    test.setTimeout(600_000); // 10 minutes for full draft

    // Use system chromium in Docker (Alpine)
    const executablePath =
      process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined;
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

    // Fetch draft info from Demo HeroDraft Tournament
    const response = await setupContextA.request.get(
      `${API_URL}/tests/herodraft-by-key/demo_herodraft/`,
      { failOnStatusCode: false, timeout: 10000 },
    );

    if (!response.ok()) {
      await setupContextA.close();
      await setupContextB.close();
      throw new Error(
        `Failed to get HeroDraft test data. Run 'just db::populate::all' first.`,
      );
    }

    testInfo = await response.json();

    // Reset the draft
    await setupContextA.request.post(
      `${API_URL}/tests/herodraft/${testInfo.pk}/reset/`,
      { failOnStatusCode: false },
    );

    const teams = testInfo.draft_teams;
    const herodraftUrl = `${BASE_URL}/herodraft/${testInfo.pk}`;

    console.log(`Draft ID: ${testInfo.pk}`);
    console.log(
      `Captain A: ${teams[0].captain.username} (${teams[0].team_name})`,
    );
    console.log(
      `Captain B: ${teams[1].captain.username} (${teams[1].team_name})`,
    );

    // Login both captains
    await loginAsDiscordId(setupContextA, teams[0].captain.discordId);
    await loginAsDiscordId(setupContextB, teams[1].captain.discordId);

    const setupPageA = await setupContextA.newPage();
    const setupPageB = await setupContextB.newPage();

    // Navigate directly to herodraft URL
    await Promise.all([
      setupPageA.goto(herodraftUrl),
      setupPageB.goto(herodraftUrl),
    ]);
    await Promise.all([
      waitForHydration(setupPageA),
      waitForHydration(setupPageB),
    ]);

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
    const dismissAllOverlays = async (page: Page, name: string) => {
      // Try clicking dismiss banner button if visible
      const dismissBtn = page.locator('button:has-text("Dismiss banner")');
      if (await dismissBtn.isVisible().catch(() => false)) {
        console.log(`Setup: Dismissing banner for ${name}...`);
        await dismissBtn.click({ force: true });
        await page.waitForTimeout(300);
      }

      // Check for alert dialogs (NOT the herodraft modal itself)
      const alertDialog = page.locator('[role="alertdialog"]');
      if (await alertDialog.isVisible().catch(() => false)) {
        console.log(`Setup: Closing alert dialog for ${name}...`);
        await page.keyboard.press('Escape');
        await page.waitForTimeout(300);
      }
    };

    await dismissAllOverlays(setupPageA, teams[0].captain.username);
    await dismissAllOverlays(setupPageB, teams[1].captain.username);

    // Click ready with retry logic and overlay dismissal
    const clickReadyWithRetry = async (
      page: Page,
      name: string,
      maxRetries = 5,
    ) => {
      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        // Always dismiss overlays before each attempt
        await dismissAllOverlays(page, name);

        try {
          console.log(`Setup: ${name} clicking ready (attempt ${attempt})...`);

          // First verify we're in the waiting phase
          const waitingPhase = page.locator(
            '[data-testid="herodraft-waiting-phase"]',
          );
          if (!(await waitingPhase.isVisible().catch(() => false))) {
            // Maybe already in rolling phase?
            const rollingPhase = page.locator(
              '[data-testid="herodraft-rolling-phase"]',
            );
            if (await rollingPhase.isVisible().catch(() => false)) {
              console.log(
                `Setup: ${name} already in rolling phase, skipping ready`,
              );
              return;
            }
            console.log(`Setup: ${name} not in waiting phase yet, waiting...`);
            await waitingPhase.waitFor({ state: 'visible', timeout: 10000 });
          }

          const readyBtn = page.locator(
            '[data-testid="herodraft-ready-button"]',
          );

          // Wait for ready button to appear (it only shows for captains who haven't clicked ready)
          console.log(`Setup: ${name} waiting for ready button...`);
          await readyBtn.waitFor({ state: 'visible', timeout: 10000 });
          console.log(`Setup: ${name} ready button is visible`);

          // Set up response listener BEFORE clicking
          const responsePromise = page.waitForResponse(
            (response) =>
              response.url().includes('/set-ready/') &&
              response.status() === 200,
            { timeout: 15000 },
          );

          // Use Playwright's native click with force to bypass any overlays
          await readyBtn.click({ force: true });
          console.log(
            `Setup: ${name} clicked ready button, waiting for API response...`,
          );

          // Wait for the API call to complete
          const response = await responsePromise;
          console.log(
            `Setup: ${name} set-ready API returned ${response.status()}`,
          );

          // Wait for button to disappear (indicates ready state was accepted by UI)
          await readyBtn.waitFor({ state: 'hidden', timeout: 5000 });
          console.log(`Setup: ${name} ready confirmed - button hidden`);
          return;
        } catch (e) {
          console.log(`Setup: ${name} ready attempt ${attempt} failed: ${e}`);
          if (attempt === maxRetries) {
            // Debug: capture page state
            const pageUrl = page.url();
            const waitingVisible = await page
              .locator('[data-testid="herodraft-waiting-phase"]')
              .isVisible()
              .catch(() => false);
            const readyBtnVisible = await page
              .locator('[data-testid="herodraft-ready-button"]')
              .isVisible()
              .catch(() => false);
            console.log(
              `Setup: Debug - URL: ${pageUrl}, waiting phase visible: ${waitingVisible}, ready btn visible: ${readyBtnVisible}`,
            );
            throw new Error(
              `Failed to click ready for ${name} after ${maxRetries} attempts: ${e}`,
            );
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
      setupPageA
        .locator(flipCoinSelector)
        .waitFor({ state: 'visible', timeout: 10000 }),
      setupPageB
        .locator(flipCoinSelector)
        .waitFor({ state: 'visible', timeout: 10000 }),
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
    // PHASE 2: Video Recording with timestamp tracking for auto-trim
    // =========================================================================
    // Playwright doesn't support dynamic start/stop of video recording.
    // Solution: Record everything, track when draft UI appears, save timestamp
    // to YAML file, then use ffmpeg to trim the beginning in post-processing.
    console.log('=== PHASE 2: Video Recording ===');

    // Create recording contexts
    // IMPORTANT: Video recording starts when context is created, not when page is created
    // Capture timestamp BEFORE creating context to account for encoder initialization
    const recordingStartTime = Date.now();

    const contextA = await browserA.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowSize, height: windowSize },
      storageState: storageStateA,
      recordVideo: {
        dir: VIDEO_OUTPUT_DIR,
        size: { width: windowSize, height: windowSize },
      },
    });

    // Each video's clock starts at its own context; the clip aligns them.
    const recordingStartTimeB = Date.now();
    const contextB = await browserB.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowSize, height: windowSize },
      storageState: storageStateB,
      recordVideo: {
        dir: VIDEO_OUTPUT_DIR,
        size: { width: windowSize, height: windowSize },
      },
    });

    await contextA.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });
    await contextB.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });

    // Create pages
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    console.log('Video: Recording started');

    // Navigate to herodraft
    console.log('Video: Navigating to herodraft...');
    await Promise.all([pageA.goto(herodraftUrl), pageB.goto(herodraftUrl)]);
    await Promise.all([waitForHydration(pageA), waitForHydration(pageB)]);

    // Wait for loading to complete
    console.log('Video: Waiting for "Loading draft..." to finish...');
    await Promise.all([
      pageA
        .locator('[data-testid="herodraft-loading"]')
        .waitFor({ state: 'hidden', timeout: 60000 }),
      pageB
        .locator('[data-testid="herodraft-loading"]')
        .waitFor({ state: 'hidden', timeout: 60000 }),
    ]);
    console.log('Video: Loading screen hidden');

    // Wait for rolling phase UI - THIS is the actual trim point (what we want to show)
    console.log('Video: Waiting for rolling phase UI...');
    await Promise.all([
      pageA
        .locator('[data-testid="herodraft-rolling-phase"]')
        .waitFor({ state: 'visible', timeout: 30000 }),
      pageB
        .locator('[data-testid="herodraft-rolling-phase"]')
        .waitFor({ state: 'visible', timeout: 30000 }),
    ]);

    // Calculate trim time when rolling phase appears (the actual content we want)
    const contentVisibleTime = Date.now();
    const trimStartSeconds = (contentVisibleTime - recordingStartTime) / 1000;
    console.log(
      `Video: Rolling phase visible (trim first ${trimStartSeconds.toFixed(2)}s)`,
    );

    // Save trim metadata to YAML file
    const trimMetadata = {
      captain1: {
        video: 'captain1_herodraft.webm',
        trim_start_seconds: trimStartSeconds,
      },
      captain2: {
        video: 'captain2_herodraft.webm',
        trim_start_seconds: (contentVisibleTime - recordingStartTimeB) / 1000,
      },
      recorded_at: new Date().toISOString(),
    };
    await fs.mkdir(VIDEO_OUTPUT_DIR, { recursive: true });
    await fs.writeFile(
      DEMO_METADATA_FILE,
      `# Auto-generated by herodraft demo test\n# Use 'just demo::trim' to apply these trim values\n\n` +
        Object.entries(trimMetadata)
          .map(([key, value]) => {
            if (typeof value === 'object') {
              return (
                `${key}:\n` +
                Object.entries(value)
                  .map(
                    ([k, v]) =>
                      `  ${k}: ${typeof v === 'number' ? v.toFixed(2) : v}`,
                  )
                  .join('\n')
              );
            }
            return `${key}: ${value}`;
          })
          .join('\n\n') +
        '\n',
    );
    console.log(`Video: Saved trim metadata to ${DEMO_METADATA_FILE}`);

    // Wait for flip coin button
    await Promise.all([
      pageA
        .locator(flipCoinSelector)
        .waitFor({ state: 'visible', timeout: 10000 }),
      pageB
        .locator(flipCoinSelector)
        .waitFor({ state: 'visible', timeout: 10000 }),
    ]);
    console.log('Video: Draft ready - recording in progress');

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

    // One unrecorded non-captain per team, for team chat and suggestions.
    for (const [i, team] of teams.entries()) {
      const memberPk = team.member_pks.find((pk) => pk !== team.captain.pk);
      if (memberPk === undefined) {
        throw new Error(`${team.team_name} has no non-captain member`);
      }
      const browser = i === 0 ? browserA! : browserB!;
      const context = await browser.newContext({
        ignoreHTTPSErrors: true,
        viewport: { width: windowSize, height: windowSize },
      });
      await context.addInitScript(() => {
        (window as Window & { playwright?: boolean }).playwright = true;
      });
      await loginAsUser(context, memberPk);
      const page = await context.newPage();
      await page.goto(herodraftUrl);
      await waitForHydration(page);
      await new HeroDraftPage(page).waitForConnection(20000);
      members.push({ context, page });
    }
    console.log('Video: Team members connected for chat');

    // Brief pause for synchronized video start
    await Promise.all([pageA.waitForTimeout(1000), pageB.waitForTimeout(1000)]);

    console.log('=== DEMO START (Rolling Phase) ===');

    // =========================================================================
    // ROLLING PHASE (Video recording already started)
    // =========================================================================
    console.log('=== ROLLING PHASE ===');

    // Pause for video - show the rolling phase UI
    await captainA.page.waitForTimeout(1500);

    // Either captain can click the flip coin button
    const flipCoinButton = captainA.page.locator(
      '[data-testid="herodraft-flip-coin-button"]',
    );
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
    console.log(
      `Captain A username: "${captainA.username}", Captain B username: "${captainB.username}"`,
    );

    const winnerIsA = winnerText?.includes(captainA.username);
    const winner = winnerIsA ? captainA : captainB;

    console.log(`${winner.username} won the flip!`);

    // Wait a moment for UI to update
    await winner.page.waitForTimeout(1000);

    // Winner chooses first pick - click button to open confirmation dialog
    const firstPickButton = winner.page.locator(
      '[data-testid="herodraft-choice-first-pick"]',
    );
    await expect(firstPickButton).toBeVisible({ timeout: 10000 });
    console.log('Winner clicking First Pick...');
    await winner.page.waitForTimeout(1500); // Longer pause for visibility

    // Click the choice button to open confirmation dialog
    await firstPickButton.click();

    // Wait for confirmation dialog to appear
    const confirmChoiceDialog = winner.page.locator(
      '[data-testid="herodraft-confirm-choice-dialog"]',
    );
    await expect(confirmChoiceDialog).toBeVisible({ timeout: 5000 });
    console.log('Confirmation dialog opened');
    await winner.page.waitForTimeout(1500); // Pause to show dialog

    // Set up response listener before confirming
    const firstPickResponsePromise = winner.page.waitForResponse(
      (response) =>
        response.url().includes('/submit-choice/') && response.status() === 200,
      { timeout: 15000 },
    );

    // Click confirm button
    const confirmButton = winner.page.locator(
      '[data-testid="herodraft-confirm-choice-submit"]',
    );
    await confirmButton.click();
    await firstPickResponsePromise;
    console.log('Winner chose First Pick (API confirmed)');

    // Wait for loser to see remaining choices
    const loser = winner === captainA ? captainB : captainA;
    await loser.page.waitForTimeout(2000); // Longer pause for transition

    // Loser chooses side (Radiant or Dire) from remaining options
    const radiantButton = loser.page.locator(
      '[data-testid="herodraft-remaining-radiant"]',
    );
    await expect(radiantButton).toBeVisible({ timeout: 10000 });
    console.log('Loser clicking Radiant...');
    await loser.page.waitForTimeout(1500); // Longer pause for visibility

    // Click the choice button to open confirmation dialog
    await radiantButton.click();

    // Wait for confirmation dialog to appear
    const loserConfirmDialog = loser.page.locator(
      '[data-testid="herodraft-confirm-choice-dialog"]',
    );
    await expect(loserConfirmDialog).toBeVisible({ timeout: 5000 });
    console.log('Loser confirmation dialog opened');
    await loser.page.waitForTimeout(1500); // Pause to show dialog

    // Set up response listener before confirming
    const radiantResponsePromise = loser.page.waitForResponse(
      (response) =>
        response.url().includes('/submit-choice/') && response.status() === 200,
      { timeout: 15000 },
    );

    // Click confirm button
    const loserConfirmButton = loser.page.locator(
      '[data-testid="herodraft-confirm-choice-submit"]',
    );
    await loserConfirmButton.click();
    const radiantResponse = await radiantResponsePromise;
    const responseData = await radiantResponse.json();
    console.log(
      `Loser chose Radiant (API confirmed, new state: ${responseData.state})`,
    );

    // Wait for drafting phase UI to appear on both pages
    console.log('Waiting for drafting phase UI...');
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
    const heroGrid = captainA.page.locator(
      '[data-testid="herodraft-hero-grid"]',
    );
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

    // =========================================================================
    // CHAT: Enter keybind, /all chat, team suggestions and replies
    // =========================================================================
    console.log('=== CHAT ===');
    const memberOf = (captain: CaptainContext): Page =>
      members[captain === captainA ? 0 : 1].page;
    const firstMember = memberOf(firstPickCaptain);
    const secondMember = memberOf(secondPickCaptain);

    // Outside the 30 heroes the round loop uses, so both stay available.
    const banHeroId = Number(
      await heroButtons.nth(36).getAttribute('data-hero-id'),
    );
    const pickHeroId = Number(
      await heroButtons.nth(41).getAttribute('data-hero-id'),
    );
    const banHeroName = await heroButtons
      .nth(36)
      .getAttribute('data-hero-name');
    const pickHeroName = await heroButtons
      .nth(41)
      .getAttribute('data-hero-name');
    console.log(
      `Chat: ban suggestion ${banHeroName} (${banHeroId}), pick suggestion ${pickHeroName} (${pickHeroId})`,
    );

    // Show the Enter hint on the closed composer before using it.
    await captainA.page.waitForTimeout(1500);
    await Promise.all([
      openChatWithEnter(captainA.page),
      openChatWithEnter(captainB.page),
    ]);
    await captainA.page.waitForTimeout(600);

    await typeChat(captainA.page, '/all glhf!');
    await expect(chatRowWith(captainB.page, 'glhf!')).toHaveAttribute(
      'data-channel',
      'all',
    );
    await captainB.page.waitForTimeout(400);
    await typeChat(captainB.page, '/all gl hf, have a good one');
    await expect(chatRowWith(captainA.page, 'have a good one')).toHaveAttribute(
      'data-channel',
      'all',
    );
    await captainA.page.waitForTimeout(1200);

    const chatClipStart = Date.now();
    await Promise.all([
      memberSuggest(firstMember, banHeroId, 'suggest_ban'),
      memberSuggest(secondMember, pickHeroId, 'suggest_pick'),
    ]);
    await Promise.all([
      memberSendChat(
        firstMember,
        `They spam ${banHeroName} every game, ban it`,
      ),
      memberSendChat(
        secondMember,
        `${pickHeroName} is still open, let's take it`,
      ),
    ]);
    await Promise.all([
      expect(
        suggestionRow(firstPickCaptain.page, 'suggest_ban', banHeroId),
      ).toBeVisible(),
      expect(
        suggestionRow(secondPickCaptain.page, 'suggest_pick', pickHeroId),
      ).toBeVisible(),
    ]);
    await captainA.page.waitForTimeout(700);
    await Promise.all([
      typeChat(firstPickCaptain.page, `Agreed, banning ${banHeroName}`),
      typeChat(secondPickCaptain.page, 'On it, ours at first pick'),
    ]);
    await captainA.page.waitForTimeout(1500);
    const chatClipEnd = Date.now();

    // Team chat stays on its team: neither captain sees the other's.
    await expect(
      suggestionRow(secondPickCaptain.page, 'suggest_ban', banHeroId),
    ).toHaveCount(0);
    await expect(
      suggestionRow(firstPickCaptain.page, 'suggest_pick', pickHeroId),
    ).toHaveCount(0);
    await expect(
      chatRowWith(secondPickCaptain.page, 'every game, ban it'),
    ).toHaveCount(0);
    await expect(
      chatRowWith(firstPickCaptain.page, 'is still open'),
    ).toHaveCount(0);

    await fs.appendFile(
      DEMO_METADATA_FILE,
      `\nchat_clip:\n` +
        `  starts:\n` +
        `    captain1_herodraft.webm: ${((chatClipStart - recordingStartTime) / 1000).toFixed(2)}\n` +
        `    captain2_herodraft.webm: ${((chatClipStart - recordingStartTimeB) / 1000).toFixed(2)}\n` +
        `  duration_seconds: ${((chatClipEnd - chatClipStart) / 1000).toFixed(2)}\n`,
    );

    // The first-pick captain follows the suggestion: click it, then ban.
    await suggestionRow(firstPickCaptain.page, 'suggest_ban', banHeroId)
      .locator('[data-testid^="herodraft-chat-suggestion-"]')
      .click();
    await firstPickCaptain.page.waitForTimeout(800);
    await Promise.all([closeChat(captainA.page), closeChat(captainB.page)]);

    // Draft sequence helper
    const getCurrentPicker = async (roundNum: number) => {
      // Captain's Mode draft order (2024 patch, first picker perspective):
      // Ban Phase 1: F-F-S-S-F-S-S
      // Pick Phase 1: F-S
      // Ban Phase 2: F-F-S
      // Pick Phase 2: S-F-F-S-S-F
      // Ban Phase 3: F-S-F-S
      // Pick Phase 3: F-S
      const DRAFT_SEQUENCE: [boolean, string][] = [
        [true, 'ban'], // 1
        [true, 'ban'], // 2
        [false, 'ban'], // 3
        [false, 'ban'], // 4
        [true, 'ban'], // 5
        [false, 'ban'], // 6
        [false, 'ban'], // 7
        [true, 'pick'], // 8
        [false, 'pick'], // 9
        [true, 'ban'], // 10
        [true, 'ban'], // 11
        [false, 'ban'], // 12
        [false, 'pick'], // 13
        [true, 'pick'], // 14
        [true, 'pick'], // 15
        [false, 'pick'], // 16
        [false, 'pick'], // 17
        [true, 'pick'], // 18
        [true, 'ban'], // 19
        [false, 'ban'], // 20
        [true, 'ban'], // 21
        [false, 'ban'], // 22
        [true, 'pick'], // 23
        [false, 'pick'], // 24
      ];

      const [isFirstPickTeam] = DRAFT_SEQUENCE[roundNum - 1];
      return isFirstPickTeam ? firstPickCaptain : secondPickCaptain;
    };

    for (let round = 1; round <= maxRounds; round++) {
      console.log(`--- Round ${round}/${maxRounds} ---`);

      const currentPicker = await getCurrentPicker(round);
      const action = await currentPicker.draftPage.getCurrentAction();
      // Get current round BEFORE picking (after pick, active moves to next round)
      const currentRound = await currentPicker.draftPage.getCurrentRound();

      console.log(`${currentPicker.username} will ${action}`);

      // Round 1 is the first-pick ban, round 9 the second team's first pick.
      const heroId =
        round === 1
          ? banHeroId
          : round === 9
            ? pickHeroId
            : heroIds[heroIndex++];
      await currentPicker.draftPage.pickHero(heroId);

      // Wait for round completion (using round captured before pick)
      const roundCompletedA = captainA.page.locator(
        `[data-testid="herodraft-round-${currentRound}"][data-round-state="completed"]`,
      );
      const roundCompletedB = captainB.page.locator(
        `[data-testid="herodraft-round-${currentRound}"][data-round-state="completed"]`,
      );

      try {
        await Promise.all([
          roundCompletedA.waitFor({ state: 'attached', timeout: 5000 }),
          roundCompletedB.waitFor({ state: 'attached', timeout: 5000 }),
        ]);
      } catch {
        console.log(`Round ${currentRound} completion timeout, continuing...`);
      }

      // =========================================================================
      // PAUSE/RESUME DEMONSTRATION - After round 12 (midway through draft)
      // =========================================================================
      if (round === 12) {
        console.log('=== PAUSE/RESUME DEMO ===');

        // Captain A clicks pause button
        const pauseButton = captainA.page.locator(
          '[data-testid="herodraft-pause-btn"]',
        );
        await expect(pauseButton).toBeVisible({ timeout: 5000 });
        console.log('Clicking pause button...');

        // Set up response listener before clicking
        const pauseResponsePromise = captainA.page.waitForResponse(
          (response) =>
            response.url().includes('/pause/') && response.status() === 200,
          { timeout: 10000 },
        );

        await pauseButton.click();

        // Wait for pause API to complete
        await pauseResponsePromise;
        console.log('Pause API confirmed');

        // Wait for paused overlay to appear on both pages (state comes via WebSocket)
        const pausedOverlayA = captainA.page.locator(
          '[data-testid="herodraft-paused-overlay"]',
        );
        const pausedOverlayB = captainB.page.locator(
          '[data-testid="herodraft-paused-overlay"]',
        );
        await expect(pausedOverlayA).toBeVisible({ timeout: 10000 });
        await expect(pausedOverlayB).toBeVisible({ timeout: 10000 });
        console.log('Draft paused - overlay visible on both pages');

        // Topbar countdown must freeze while paused. ±1s tolerance for the
        // second-precision display flipping at the capture boundary.
        const graceBeforeA = await captainA.draftPage.getGraceTimeSeconds();
        const teamABeforeA =
          await captainA.draftPage.getTeamAReserveTimeSeconds();
        const teamBBeforeA =
          await captainA.draftPage.getTeamBReserveTimeSeconds();
        const graceBeforeB = await captainB.draftPage.getGraceTimeSeconds();
        console.log(
          `Paused timers (A view): grace=${graceBeforeA}s, A=${teamABeforeA}s, B=${teamBBeforeA}s; (B view): grace=${graceBeforeB}s`,
        );

        // Show the paused state for video
        await captainA.page.waitForTimeout(3000);

        const graceAfterA = await captainA.draftPage.getGraceTimeSeconds();
        const teamAAfterA =
          await captainA.draftPage.getTeamAReserveTimeSeconds();
        const teamBAfterA =
          await captainA.draftPage.getTeamBReserveTimeSeconds();
        const graceAfterB = await captainB.draftPage.getGraceTimeSeconds();
        console.log(
          `After 3s pause (A view): grace=${graceAfterA}s, A=${teamAAfterA}s, B=${teamBAfterA}s; (B view): grace=${graceAfterB}s`,
        );

        expect(
          Math.abs(graceBeforeA - graceAfterA),
          'grace timer must not advance during pause (A view)',
        ).toBeLessThanOrEqual(1);
        expect(
          Math.abs(teamABeforeA - teamAAfterA),
          'team A reserve must not advance during pause',
        ).toBeLessThanOrEqual(1);
        expect(
          Math.abs(teamBBeforeA - teamBAfterA),
          'team B reserve must not advance during pause',
        ).toBeLessThanOrEqual(1);
        expect(
          Math.abs(graceBeforeB - graceAfterB),
          'grace timer must not advance during pause (B view)',
        ).toBeLessThanOrEqual(1);

        // Captain A clicks resume button
        const resumeButton = captainA.page.locator(
          '[data-testid="herodraft-resume-btn"]',
        );
        await expect(resumeButton).toBeVisible({ timeout: 5000 });
        console.log('Clicking resume button...');

        // Set up response listener before clicking
        const resumeResponsePromise = captainA.page.waitForResponse(
          (response) =>
            response.url().includes('/resume/') && response.status() === 200,
          { timeout: 10000 },
        );

        await resumeButton.click();

        // Wait for resume API to complete
        await resumeResponsePromise;
        console.log('Resume API confirmed');

        // Wait for overlay to disappear (after countdown)
        await expect(pausedOverlayA).not.toBeVisible({ timeout: 15000 });
        await expect(pausedOverlayB).not.toBeVisible({ timeout: 15000 });
        console.log('Draft resumed - continuing...');

        // Brief pause after resume
        await captainA.page.waitForTimeout(1000);
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
