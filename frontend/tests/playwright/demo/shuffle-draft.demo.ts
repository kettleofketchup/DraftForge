/**
 * Shuffle Draft Demo - Full Flow Video Recording
 *
 * Records a complete shuffle MMR draft from start to finish for documentation.
 * Shuffle draft has MMR-based double pick mechanics where lower MMR teams
 * can get consecutive picks if they stay under the threshold.
 *
 * Uses two-phase recording:
 * - Phase 1: Setup (no video) - navigate, set draft style, restart draft
 * - Phase 2: Video recording - record the actual draft flow
 *
 * Video output: 1:1 aspect ratio (800x800) for docs and social media.
 * Named output: shuffle_draft.webm
 */

import { test, expect, chromium } from '@playwright/test';
import { loginAdmin, loginAdminFromPage, waitForHydration, DOCKER_HOST } from '../fixtures/auth';
import { waitForDemoReady, waitForDraftReady, waitForLoadingComplete } from '../fixtures/demo-utils';
import * as path from 'path';
import * as fs from 'fs/promises';
import { fileURLToPath } from 'url';

// ESM-compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Use DOCKER_HOST from auth.ts for consistent hostname handling
const API_URL = `https://${DOCKER_HOST}/api`;
const BASE_URL = `https://${DOCKER_HOST}`;
const VIDEO_OUTPUT_DIR = 'demo-results/videos';
const DEMO_METADATA_FILE = path.join(VIDEO_OUTPUT_DIR, 'shuffle.demo.yaml');

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

test.describe('Shuffle Draft Demo', () => {
  test('Complete Shuffle MMR Draft Flow', async ({}) => {
    // Increase timeout for full demo recording
    test.setTimeout(300_000);

    const windowSize = 800;

    // Use system chromium in Docker (Alpine) since Playwright's bundled chromium requires glibc
    // When running locally, let Playwright use its bundled chromium (undefined path)
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

    // Get Demo Shuffle Draft Tournament
    const response = await setupContext.request.get(
      `${API_URL}/tests/tournament-by-key/demo_shuffle_draft/`,
      { failOnStatusCode: false, timeout: 10000 }
    );

    if (!response.ok()) {
      throw new Error(
        `Failed to get tournament data. Run 'inv db.populate.all' first.`
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
    // This ensures browser's native cookie jar is used for XHR requests
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
      'button:has-text("Start Draft"), button:has-text("Live Draft")'
    );
    await startDraftButton.first().click();

    let dialog = setupPage.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();
    await setupPage.waitForTimeout(500);

    // Step 1: Initialize the draft via API (more reliable than UI)
    // Get CSRF token from cookies
    const cookies = await setupContext.cookies();
    const csrfCookie = cookies.find(c => c.name === 'csrftoken');
    const csrfToken = csrfCookie?.value || '';
    console.log(`Setup: CSRF token available: ${!!csrfToken}`);

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
    await setupPage.locator('button:has-text("Start Draft"), button:has-text("Live Draft")').first().click();
    await expect(setupPage.locator('[role="dialog"]')).toBeVisible();
    await setupPage.waitForTimeout(500);

    // Now the draft should exist - get draft pk from the initialized tournament
    console.log('Setup: Setting draft style via API...');

    // Fetch tournament again to get draft pk
    const tournamentResponse = await setupContext.request.get(
      `${API_URL}/tests/tournament-by-key/demo_shuffle_draft/`,
      { failOnStatusCode: false }
    );
    const updatedTournament = await tournamentResponse.json();
    const draftPk = updatedTournament.draft?.pk;

    if (draftPk) {
      // Set draft style to shuffle via API
      const styleResponse = await setupContext.request.patch(
        `${API_URL}/drafts/${draftPk}/`,
        {
          data: { draft_style: 'shuffle' },
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

    // Close any open dialog before navigating - use Escape key for reliability
    const dialogAfterReload = setupPage.locator('[role="dialog"]');
    while (await dialogAfterReload.isVisible().catch(() => false)) {
      console.log('Setup: Closing open dialog with Escape key...');
      await setupPage.keyboard.press('Escape');
      await setupPage.waitForTimeout(500);
    }

    // Open draft modal and verify
    await setupPage.locator('[data-testid="teamsTab"]').click({ force: true });
    await setupPage.waitForTimeout(300);
    await setupPage.locator('button:has-text("Start Draft"), button:has-text("Live Draft")').first().click();

    dialog = setupPage.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();
    await setupPage.waitForTimeout(500);
    console.log('Setup: Draft ready with Shuffle style');

    // Wait for draft to be ready (Pick buttons exist in DOM)
    // Note: PlayerRow renders in multiple responsive layouts, so some may be hidden
    const allPickButtons = dialog.locator('[data-testid="available-player"] button:has-text("Pick")');
    await allPickButtons.first().waitFor({ state: 'attached', timeout: 15000 });
    console.log('Setup: Pick buttons attached to DOM, draft ready');

    // Test pick in setup context to verify auth works
    console.log('Setup: Testing a pick to verify auth...');

    // Monitor network to verify pick_player request status
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

    // Also verify network response was successful
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

    // Re-initialize draft with shuffle style
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
    // IMPORTANT: Video recording starts when context is created, not when page is created
    // Capture timestamp BEFORE creating context to account for encoder initialization
    const recordingStartTime = Date.now();

    const videoContext = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowSize, height: windowSize },
      // DON'T use storageState - login fresh in this context instead
      recordVideo: {
        dir: VIDEO_OUTPUT_DIR,
        size: { width: windowSize, height: windowSize },
      },
    });

    // Inject playwright marker to disable react-scan in video
    await videoContext.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });

    // Create page first, then login from within page context
    const page = await videoContext.newPage();
    console.log('Video: Recording started');

    // Navigate first to establish origin, then login from page
    await page.goto(`https://${DOCKER_HOST}/`);
    await loginAdminFromPage(page);
    const videoCookies = await videoContext.cookies();
    const hasSession = videoCookies.some(c => c.name === 'sessionid');
    const hasCSRF = videoCookies.some(c => c.name === 'csrftoken');
    console.log(`Video: Fresh login (sessionid: ${hasSession}, csrftoken: ${hasCSRF})`);

    // Capture console errors for debugging
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log(`Console Error: ${msg.text()}`);
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
    await page.locator('button:has-text("Start Draft"), button:has-text("Live Draft")').first().click();
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
      `# Auto-generated by shuffle draft demo test\n# Use 'inv demo.trim' to apply these trim values\n\n` +
      `shuffle_draft:\n` +
      `  video: shuffle_draft.webm\n` +
      `  trim_start_seconds: ${trimStartSeconds.toFixed(2)}\n\n` +
      `recorded_at: ${new Date().toISOString()}\n`
    );
    console.log(`Video: Saved trim metadata to ${DEMO_METADATA_FILE}`);

    await page.waitForTimeout(1000);

    // Perform picks - shuffle draft has MMR-based double pick mechanics
    const maxPicks = 16; // 4 teams x 4 players each
    let picksMade = 0;

    for (let i = 0; i < maxPicks; i++) {
      const dialogEl = page.locator('[role="dialog"]');
      // Select visible Pick buttons only (responsive layouts render same buttons multiple times)
      const pickBtns = dialogEl.locator('[data-testid="available-player"]:visible button:has-text("Pick")');

      // Scroll dialog content to show the player list
      const scrollArea = dialogEl.locator('[data-radix-scroll-area-viewport]').first();
      await scrollArea.evaluate((el) => el.scrollTo({ top: 300, behavior: 'smooth' }));
      await page.waitForTimeout(500);

      // Wait for pick buttons to be visible after scroll
      await pickBtns.first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
      const pickCount = await pickBtns.count();

      if (pickCount === 0) {
        console.log(`No more picks available after ${picksMade} picks`);
        break;
      }

      // Click the first visible pick button
      const firstPickBtn = pickBtns.first();
      await firstPickBtn.scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
      await firstPickBtn.click();
      await page.waitForTimeout(300);

      // Handle confirmation
      const confirmDialog = page.locator('[role="alertdialog"]');
      if (await confirmDialog.isVisible().catch(() => false)) {
        const pickConfirmBtn = confirmDialog.locator(
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

      // Scroll back to top of dialog to show pick order update
      // Must scroll the ScrollArea viewport, not the dialog itself
      const dialogScrollArea = dialogEl.locator('[data-radix-scroll-area-viewport]').first();
      await dialogScrollArea.evaluate((el) => el.scrollTo({ top: 0, behavior: 'smooth' }));
      await page.waitForTimeout(1200); // Pause to show pick order update

      picksMade++;
      console.log(`Pick ${picksMade}/${maxPicks} completed`);
    }

    // Final pause to show completed draft
    await page.waitForTimeout(3000);

    // Save video with named output to both locations
    await page.close();
    const video = page.video();
    if (video) {
      const videoPath = path.join(VIDEO_OUTPUT_DIR, 'shuffle_draft.webm');
      await video.saveAs(videoPath);
      console.log('Saved: shuffle_draft.webm');

      // Also copy to docs/assets/videos
      const docsVideoDir = path.resolve(__dirname, '../../../docs/assets/videos');
      await fs.mkdir(docsVideoDir, { recursive: true });
      await fs.copyFile(videoPath, path.join(docsVideoDir, 'shuffle_draft.webm'));
      console.log('Copied to: docs/assets/videos/shuffle_draft.webm');
    }

    await videoContext.close();
    await browser.close();

    console.log(
      `Shuffle Draft Demo complete! Made ${picksMade} picks.`
    );
  });
});
