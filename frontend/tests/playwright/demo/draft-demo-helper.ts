/**
 * Shared Draft Demo Helper
 *
 * Common logic for recording draft demos (snake, shuffle, etc.)
 * Only the tournament key and output names differ between draft types.
 */

import { test, expect, chromium } from '@playwright/test';
import { loginAdminFromPage, waitForHydration, DOCKER_HOST } from '../fixtures/auth';
import { waitForDemoReady, waitForDraftReady, waitForLoadingComplete } from '../fixtures/demo-utils';
import * as path from 'path';
import * as fs from 'fs/promises';

const API_URL = `https://${DOCKER_HOST}/api`;
const BASE_URL = `https://${DOCKER_HOST}`;
const VIDEO_OUTPUT_DIR = 'demo-results/videos';

interface TournamentData {
  pk: number;
  name: string;
  teams: Array<{
    pk: number;
    name: string;
    captain: { pk: number; username: string };
    draft_order: number;
  }>;
  draft?: {
    pk: number;
    draft_style: string;
    state: string;
  };
}

export interface DraftDemoConfig {
  /** Tournament key used in populate.py (e.g., 'demo_shuffle_draft', 'demo_snake_draft') */
  tournamentKey: string;
  /** Draft style to set via API (e.g., 'shuffle', 'snake') */
  draftStyle: string;
  /** Output video filename without extension (e.g., 'shuffle_draft') */
  outputName: string;
  /** Directory for docs assets (relative to demo file) */
  docsVideoDir: string;
}

export async function runDraftDemo(config: DraftDemoConfig): Promise<void> {
  const { tournamentKey, draftStyle, outputName, docsVideoDir } = config;
  const DEMO_METADATA_FILE = path.join(VIDEO_OUTPUT_DIR, `${outputName}.demo.yaml`);

  const windowSize = 1200;

  // Use system chromium in Docker (Alpine) since Playwright's bundled chromium requires glibc
  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined;
  const browserOptions = {
    headless: true,
    slowMo: 100,
    ...(executablePath && { executablePath }),
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      `--window-size=${windowSize},${windowSize}`,
    ],
  };

  const browser = await chromium.launch(browserOptions);

  // Create video output directory
  await fs.mkdir(VIDEO_OUTPUT_DIR, { recursive: true });

  // =========================================================================
  // PHASE 1: Setup (no video recording)
  // =========================================================================
  const setupContext = await browser.newContext({
    ignoreHTTPSErrors: true,
    viewport: { width: windowSize, height: windowSize },
  });

  // Inject playwright marker to disable react-scan
  await setupContext.addInitScript(() => {
    (window as Window & { playwright?: boolean }).playwright = true;
  });

  // Get tournament by key
  const response = await setupContext.request.get(
    `${API_URL}/tests/tournament-by-key/${tournamentKey}/`,
    { failOnStatusCode: false, timeout: 10000 }
  );

  if (!response.ok()) {
    throw new Error(
      `Failed to get tournament data for '${tournamentKey}'. Run 'inv db.populate.all' first.`
    );
  }

  const tournament: TournamentData = await response.json();
  console.log(`Demo: ${tournament.name} (pk=${tournament.pk})`);

  // Reset the draft to initial state
  await setupContext.request.post(
    `${API_URL}/tests/tournament/${tournament.pk}/reset-draft/`,
    { failOnStatusCode: false }
  );

  // Create page FIRST, then login from within page context
  const setupPage = await setupContext.newPage();

  // Navigate to tournament first to establish origin
  await setupPage.goto(`${BASE_URL}/tournament/${tournament.pk}`);

  // Login from within the page so browser handles cookies natively
  await loginAdminFromPage(setupPage);
  console.log('Setup: Logged in as admin (kettleofketchup) from page context');
  await waitForHydration(setupPage);
  await waitForDemoReady(setupPage, { timeout: 30000 });

  // Click Teams tab
  const teamsTab = setupPage.locator('[data-testid="teamsTab"]');
  await teamsTab.click();
  await setupPage.waitForTimeout(500);

  // Open draft modal
  const startDraftButton = setupPage.locator(
    'button:has-text("Start Draft"), button:has-text("Start Team Draft"), button:has-text("Live Draft")'
  );
  await startDraftButton.first().click();

  let dialog = setupPage.locator('[role="dialog"]');
  await expect(dialog).toBeVisible();
  await setupPage.waitForTimeout(500);

  // Get CSRF token from cookies
  const cookies = await setupContext.cookies();
  const csrfCookie = cookies.find(c => c.name === 'csrftoken');
  const csrfToken = csrfCookie?.value || '';
  console.log(`Setup: CSRF token available: ${!!csrfToken}`);

  // Initialize the draft via API
  console.log('Setup: Initializing draft via API...');
  const initResponse = await setupContext.request.post(
    `${API_URL}/tournaments/init-draft`,
    {
      data: { tournament_pk: tournament.pk },
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      failOnStatusCode: false,
    }
  );
  console.log(`Setup: Init draft API response: ${initResponse.status()}`);
  if (!initResponse.ok()) {
    const errorText = await initResponse.text();
    console.log(`Setup: Init draft error: ${errorText}`);
  }

  // Close the dialog first before reloading
  const closeBtn = setupPage.locator('[data-testid="close-draft-modal"]');
  if (await closeBtn.isVisible().catch(() => false)) {
    await closeBtn.click();
    await setupPage.waitForTimeout(300);
  }

  // Reload page to pick up new draft state
  await setupPage.reload();
  await waitForHydration(setupPage);

  // Navigate to Teams tab
  await setupPage.locator('[data-testid="teamsTab"]').click();
  await setupPage.waitForTimeout(300);

  // Re-open draft modal
  await setupPage.locator('button:has-text("Start Draft"), button:has-text("Start Team Draft"), button:has-text("Live Draft")').first().click();
  await expect(setupPage.locator('[role="dialog"]')).toBeVisible();
  await setupPage.waitForTimeout(500);

  // Fetch tournament again to get draft pk
  console.log(`Setup: Setting draft style to '${draftStyle}' via API...`);
  const tournamentResponse = await setupContext.request.get(
    `${API_URL}/tests/tournament-by-key/${tournamentKey}/`,
    { failOnStatusCode: false }
  );
  const updatedTournament = await tournamentResponse.json();
  const draftPk = updatedTournament.draft?.pk;

  if (draftPk) {
    // Set draft style via API
    const styleResponse = await setupContext.request.patch(
      `${API_URL}/drafts/${draftPk}/`,
      {
        data: { draft_style: draftStyle },
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        failOnStatusCode: false,
      }
    );
    console.log(`Setup: Set draft style API response: ${styleResponse.status()}`);
  }

  // Restart the draft to apply the style and generate rounds
  console.log('Setup: Restarting draft via API...');
  const restartResponse = await setupContext.request.post(
    `${API_URL}/tournaments/init-draft`,
    {
      data: { tournament_pk: tournament.pk },
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      failOnStatusCode: false,
    }
  );
  console.log(`Setup: Restart draft API response: ${restartResponse.status()}`);

  // Close dialog and reload to pick up changes
  const closeBtn2 = setupPage.locator('[data-testid="close-draft-modal"]');
  if (await closeBtn2.isVisible().catch(() => false)) {
    await closeBtn2.click();
    await setupPage.waitForTimeout(300);
  }

  await setupPage.reload();
  await waitForHydration(setupPage);

  // Close any open dialog before navigating
  const dialogAfterReload = setupPage.locator('[role="dialog"]');
  while (await dialogAfterReload.isVisible().catch(() => false)) {
    console.log('Setup: Closing open dialog with Escape key...');
    await setupPage.keyboard.press('Escape');
    await setupPage.waitForTimeout(500);
  }

  // Open draft modal and verify
  await setupPage.locator('[data-testid="teamsTab"]').click({ force: true });
  await setupPage.waitForTimeout(300);
  await setupPage.locator('button:has-text("Start Draft"), button:has-text("Start Team Draft"), button:has-text("Live Draft")').first().click();

  dialog = setupPage.locator('[role="dialog"]');
  await expect(dialog).toBeVisible();
  await setupPage.waitForTimeout(500);
  console.log(`Setup: Draft ready with ${draftStyle} style`);

  // Wait for draft to be ready (Pick buttons exist in DOM)
  const allPickButtons = dialog.locator('[data-testid="available-player"] button:has-text("Pick")');
  await allPickButtons.first().waitFor({ state: 'attached', timeout: 15000 });
  console.log('Setup: Pick buttons attached to DOM, draft ready');

  // Test pick in setup context to verify auth works
  console.log('Setup: Testing a pick to verify auth...');

  let setupPickStatus: number | null = null;
  setupPage.on('response', response => {
    if (response.url().includes('pick_player')) {
      setupPickStatus = response.status();
    }
  });

  const testPickBtn = dialog.locator('[data-testid="available-player"]:visible button:has-text("Pick")').first();
  await testPickBtn.scrollIntoViewIfNeeded();
  await testPickBtn.click();
  await setupPage.waitForTimeout(300);

  // Handle confirmation dialog
  const confirmDialog = setupPage.locator('[role="alertdialog"]');
  if (await confirmDialog.isVisible().catch(() => false)) {
    const pickConfirmBtn = confirmDialog.locator('button:has-text("Confirm"), button:has-text("Pick")');
    if (await pickConfirmBtn.isVisible().catch(() => false)) {
      await pickConfirmBtn.first().click();
    }
  }
  await setupPage.waitForTimeout(2000);

  // Check for error toast
  const errorToast = setupPage.locator('text="Failed to update captains"');
  if (await errorToast.isVisible().catch(() => false)) {
    throw new Error('Setup: Test pick failed with 403 - auth not working');
  }

  if (setupPickStatus === 403) {
    throw new Error('Setup: Test pick got 403 at network level');
  }
  console.log(`Setup: Test pick successful (network status: ${setupPickStatus})`);

  // Reset draft for clean video recording
  await setupContext.request.post(
    `${API_URL}/tests/tournament/${tournament.pk}/reset-draft/`,
    { failOnStatusCode: false }
  );
  console.log('Setup: Reset draft for video recording');

  // Re-initialize draft with correct style
  await setupContext.request.post(
    `${API_URL}/tournaments/init-draft`,
    {
      data: { tournament_pk: tournament.pk },
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      failOnStatusCode: false,
    }
  );

  // Save storage state for video context
  const storageState = await setupContext.storageState();
  await setupContext.close();

  // =========================================================================
  // PHASE 2: Video recording with timestamp tracking
  // =========================================================================
  const recordingStartTime = Date.now();

  const videoContext = await browser.newContext({
    ignoreHTTPSErrors: true,
    viewport: { width: windowSize, height: windowSize },
    recordVideo: {
      dir: VIDEO_OUTPUT_DIR,
      size: { width: windowSize, height: windowSize },
    },
  });

  // Inject playwright marker to disable react-scan in video
  await videoContext.addInitScript(() => {
    (window as Window & { playwright?: boolean }).playwright = true;
  });

  const page = await videoContext.newPage();
  console.log('Video: Recording started');

  // Navigate first to establish origin, then login from page
  await page.goto(`https://${DOCKER_HOST}/`);
  await loginAdminFromPage(page);
  const videoCookies = await videoContext.cookies();
  const hasSession = videoCookies.some(c => c.name === 'sessionid');
  const hasCSRF = videoCookies.some(c => c.name === 'csrftoken');
  console.log(`Video: Fresh login (sessionid: ${hasSession}, csrftoken: ${hasCSRF})`);

  // Capture console errors for debugging (filter out harmless React DevTools errors)
  page.on('console', msg => {
    if (msg.type() === 'error') {
      const text = msg.text();
      // Ignore React DevTools manifest fetch errors - harmless dev tooling
      if (text.includes('manifest patches') || text.includes('fetchAndApplyManifestPatches')) {
        return;
      }
      console.log(`Console Error: ${text}`);
    }
  });

  // Capture pick_player requests and fail on 403
  let networkError: string | null = null;
  page.on('response', response => {
    if (response.url().includes('pick_player')) {
      console.log(`Network ${response.status()}: ${response.request().method()} ${response.url()}`);
      if (response.status() === 403) {
        networkError = `403 Forbidden on ${response.url()}`;
      }
    }
  });

  // Navigate directly to tournament with draft modal
  await page.goto(`${BASE_URL}/tournament/${tournament.pk}`);

  await waitForHydration(page);
  await waitForDemoReady(page, { timeout: 30000 });

  // Pause for title shot
  await page.waitForTimeout(1500);

  // Click Teams tab
  await page.locator('[data-testid="teamsTab"]').click();
  await page.waitForTimeout(1500);

  // Open draft modal
  await page.locator('button:has-text("Start Draft"), button:has-text("Start Team Draft"), button:has-text("Live Draft")').first().click();
  await expect(page.locator('[role="dialog"]')).toBeVisible();
  await waitForDraftReady(page, { timeout: 15000 });
  await waitForLoadingComplete(page, { timeout: 5000 });

  // THIS is the actual trim point - when draft modal is ready with Pick buttons
  const contentVisibleTime = Date.now();
  const trimStartSeconds = (contentVisibleTime - recordingStartTime) / 1000;
  console.log(`Video: Draft modal ready (trim first ${trimStartSeconds.toFixed(2)}s)`);

  // Save trim metadata
  await fs.mkdir(VIDEO_OUTPUT_DIR, { recursive: true });
  await fs.writeFile(
    DEMO_METADATA_FILE,
    `# Auto-generated by ${draftStyle} draft demo test\n# Use 'inv demo.trim' to apply these trim values\n\n` +
    `${outputName}:\n` +
    `  video: ${outputName}.webm\n` +
    `  trim_start_seconds: ${trimStartSeconds.toFixed(2)}\n\n` +
    `recorded_at: ${new Date().toISOString()}\n`
  );
  console.log(`Video: Saved trim metadata to ${DEMO_METADATA_FILE}`);

  await page.waitForTimeout(1000);

  // Perform picks
  const maxPicks = 16; // 4 teams x 4 players each
  let picksMade = 0;

  for (let i = 0; i < maxPicks; i++) {
    const dialogEl = page.locator('[role="dialog"]');
    const scrollArea = dialogEl.locator('[data-radix-scroll-area-viewport]').first();

    // Start each pick at the top to show current captain/pick order
    await scrollArea.evaluate((el) => el.scrollTo({ top: 0, behavior: 'instant' }));
    await page.waitForTimeout(800);

    // Select visible Pick buttons only (responsive layouts render same buttons multiple times)
    const pickBtns = dialogEl.locator('[data-testid="available-player"]:visible button:has-text("Pick")');

    // Scroll dialog content to show the player list
    await scrollArea.evaluate((el) => el.scrollTo({ top: 400, behavior: 'smooth' }));
    await page.waitForTimeout(600);

    // Wait for pick buttons to be visible after scroll
    await pickBtns.first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
    const pickCount = await pickBtns.count();

    if (pickCount === 0) {
      console.log(`No more picks available after ${picksMade} picks`);
      break;
    }

    // Get the player row containing the first pick button
    const firstPlayerRow = dialogEl.locator('[data-testid="available-player"]:visible').first();
    await firstPlayerRow.scrollIntoViewIfNeeded();
    await page.waitForTimeout(200);

    // Hover over the avatar to show player popover
    const avatar = firstPlayerRow.locator('img').first();
    if (await avatar.isVisible().catch(() => false)) {
      await avatar.hover();
      await page.waitForTimeout(1000); // Show player popover
    }

    // Click the pick button
    const firstPickBtn = firstPlayerRow.locator('button:has-text("Pick")');
    await firstPickBtn.click();
    await page.waitForTimeout(300);

    // Handle confirmation
    const confirmDialogEl = page.locator('[role="alertdialog"]');
    if (await confirmDialogEl.isVisible().catch(() => false)) {
      const pickConfirmBtn = confirmDialogEl.locator(
        'button:has-text("Confirm"), button:has-text("Pick")'
      );
      if (await pickConfirmBtn.isVisible().catch(() => false)) {
        await pickConfirmBtn.first().click();
      }
    }

    await page.waitForTimeout(1000);

    // Fail fast on 403 errors
    if (networkError) {
      throw new Error(`Network error during pick: ${networkError}`);
    }

    picksMade++;
    console.log(`Pick ${picksMade}/${maxPicks} completed`);

    // Check if dialog is still visible before scrolling (draft may have completed)
    const isDialogStillVisible = await dialogEl.isVisible().catch(() => false);
    if (!isDialogStillVisible) {
      console.log('Dialog closed - draft complete');
      break;
    }

    // Check if there are more picks available
    const remainingPicks = await dialogEl
      .locator('[data-testid="available-player"]:visible button:has-text("Pick")')
      .count()
      .catch(() => 0);
    if (remainingPicks === 0) {
      console.log('No more picks available - draft complete');
      break;
    }

    // Scroll back to top of dialog to show pick order update
    await scrollArea.evaluate((el) => el.scrollTo({ top: 0, behavior: 'smooth' }));
    // Move mouse offscreen to avoid triggering popovers
    await page.mouse.move(0, 0);
    await page.waitForTimeout(1500); // Pause to show pick order update
  }

  // Final pause to show completed draft
  await page.waitForTimeout(3000);

  // Save video with named output to both locations
  await page.close();
  const video = page.video();
  if (video) {
    const videoPath = path.join(VIDEO_OUTPUT_DIR, `${outputName}.webm`);
    await video.saveAs(videoPath);
    console.log(`Saved: ${outputName}.webm`);

    // Also copy to docs/assets/videos
    await fs.mkdir(docsVideoDir, { recursive: true });
    await fs.copyFile(videoPath, path.join(docsVideoDir, `${outputName}.webm`));
    console.log(`Copied to: ${docsVideoDir}/${outputName}.webm`);
  }

  await videoContext.close();
  await browser.close();

  console.log(`${draftStyle.charAt(0).toUpperCase() + draftStyle.slice(1)} Draft Demo complete! Made ${picksMade} picks.`);
}
