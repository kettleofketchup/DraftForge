/**
 * Snake Draft Demo - Full Flow Video Recording
 *
 * Records a complete snake draft from start to finish for documentation.
 * Snake draft has a predictable pattern where pick order reverses each round.
 *
 * Uses two-phase recording:
 * - Phase 1: Setup (no video) - navigate, set draft style, restart draft
 * - Phase 2: Video recording - record the actual draft flow
 *
 * Video output: 1:1 aspect ratio (800x800) for docs and social media.
 * Named output: snake_draft.webm
 */

import { test, expect, chromium } from '@playwright/test';
import { loginAdmin, waitForHydration } from '../fixtures/auth';
import { waitForDemoReady, waitForDraftReady, waitForLoadingComplete } from '../fixtures/demo-utils';
import * as path from 'path';
import * as fs from 'fs/promises';

// Use nginx hostname inside Docker containers, localhost for local runs
const DOCKER_HOST = process.env.DOCKER_HOST || 'nginx';
const API_URL = `https://${DOCKER_HOST}/api`;
const BASE_URL = `https://${DOCKER_HOST}`;
const VIDEO_OUTPUT_DIR = 'demo-results/videos';
const DEMO_METADATA_FILE = path.join(VIDEO_OUTPUT_DIR, 'snake.demo.yaml');

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

test.describe('Snake Draft Demo', () => {
  test('Complete Snake Draft Flow', async ({}) => {
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

    // Get Demo Snake Draft Tournament (has real player names and Discord avatars)
    const response = await setupContext.request.get(
      `${API_URL}/tests/tournament-by-key/demo_snake_draft/`,
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

    // Login as admin for full control
    await loginAdmin(setupContext);

    const setupPage = await setupContext.newPage();

    // Navigate to tournament
    await setupPage.goto(`${BASE_URL}/tournament/${tournament.pk}`);
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
      `${API_URL}/tests/tournament-by-key/demo_snake_draft/`,
      { failOnStatusCode: false }
    );
    const updatedTournament = await tournamentResponse.json();
    const draftPk = updatedTournament.draft?.pk;

    if (draftPk) {
      // Set draft style to snake via API
      const styleResponse = await setupContext.request.patch(
        `${API_URL}/drafts/${draftPk}/`,
        {
          data: { draft_style: 'snake' },
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
    console.log('Setup: Draft ready with Snake style');

    // Wait for draft to be ready (Pick buttons visible)
    const pickButtons = dialog.locator('button:has-text("Pick")');
    await pickButtons.first().waitFor({ state: 'visible', timeout: 15000 });
    console.log('Setup: Draft ready, Pick buttons visible');

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
      storageState,
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
      `# Auto-generated by snake draft demo test\n# Use 'inv demo.trim' to apply these trim values\n\n` +
      `snake_draft:\n` +
      `  video: snake_draft.webm\n` +
      `  trim_start_seconds: ${trimStartSeconds.toFixed(2)}\n\n` +
      `recorded_at: ${new Date().toISOString()}\n`
    );
    console.log(`Video: Saved trim metadata to ${DEMO_METADATA_FILE}`);

    await page.waitForTimeout(1000);

    // Perform picks - snake draft follows predictable pattern
    // Round 1: 1 → 2 → 3 → 4
    // Round 2: 4 → 3 → 2 → 1
    // etc.
    const maxPicks = 16; // 4 teams x 4 players each
    let picksMade = 0;
    let currentRound = 1;

    for (let i = 0; i < maxPicks; i++) {
      const dialogEl = page.locator('[role="dialog"]');
      const pickBtns = dialogEl.locator('button:has-text("Pick")');
      const pickCount = await pickBtns.count();

      if (pickCount === 0) {
        console.log(`No more picks available after ${picksMade} picks`);
        break;
      }

      // Determine round for logging
      const pickInRound = (picksMade % 4) + 1;
      if (pickInRound === 1 && picksMade > 0) {
        currentRound++;
      }

      console.log(
        `Round ${currentRound}, Pick ${pickInRound}: Making pick ${picksMade + 1}/${maxPicks}`
      );

      // Click first available pick
      await pickBtns.first().click();
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

      // Longer pause at round boundaries
      if (pickInRound === 4) {
        await page.waitForTimeout(1500); // Round complete pause
      } else {
        await page.waitForTimeout(600); // Normal pick pause
      }

      picksMade++;
    }

    // Final pause to show completed draft
    await page.waitForTimeout(3000);

    // Save video with named output to both locations
    await page.close();
    const video = page.video();
    if (video) {
      const videoPath = path.join(VIDEO_OUTPUT_DIR, 'snake_draft.webm');
      await video.saveAs(videoPath);
      console.log('Saved: snake_draft.webm');

      // Also copy to docs/assets/videos
      const docsVideoDir = path.resolve(__dirname, '../../../docs/assets/videos');
      await fs.mkdir(docsVideoDir, { recursive: true });
      await fs.copyFile(videoPath, path.join(docsVideoDir, 'snake_draft.webm'));
      console.log('Copied to: docs/assets/videos/snake_draft.webm');
    }

    await videoContext.close();
    await browser.close();

    console.log(
      `Snake Draft Demo complete! Made ${picksMade} picks across ${currentRound} rounds.`
    );
  });
});
