/**
 * Site Snapshots Demo - Screenshot Generation
 *
 * Takes screenshots of key pages for documentation and feature previews.
 * Screenshots are saved to docs/assets/site_snapshots/
 *
 * Pages captured:
 * - Home page
 * - Tournaments list
 * - Tournament detail page
 * - Bracket view
 */

import { test, chromium } from '@playwright/test';
import { loginAdmin, waitForHydration } from '../fixtures/auth';
import { waitForDemoReady, waitForBracketReady } from '../fixtures/demo-utils';
import * as path from 'path';
import * as fs from 'fs';
import { fileURLToPath } from 'url';

// ESM-compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Use nginx hostname inside Docker containers, localhost for local runs
const DOCKER_HOST = process.env.DOCKER_HOST || 'nginx';
const API_URL = `https://${DOCKER_HOST}/api`;
const BASE_URL = `https://${DOCKER_HOST}`;
// Output to demo-results/site_snapshots/ (in mounted volume)
// Invoke task will copy to docs/assets/site_snapshots/
const SNAPSHOT_OUTPUT_DIR = 'demo-results/site_snapshots';

test.describe('Site Snapshots', () => {
  test('Capture all site screenshots', async ({}) => {
    test.setTimeout(120_000);

    const windowWidth = 1280;
    const windowHeight = 800;

    // Use system chromium in Docker (Alpine) since Playwright's bundled chromium requires glibc
    // When running locally, let Playwright use its bundled chromium (undefined path)
    // In Alpine Docker, chromium is at /usr/lib/chromium/chromium
    let executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined;
    if (executablePath === '/usr/bin/chromium-browser') {
      executablePath = '/usr/lib/chromium/chromium';
    }
    const browserOptions = {
      headless: true,
      ...(executablePath && { executablePath }),
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        `--window-size=${windowWidth},${windowHeight}`,
      ],
    };

    console.log(`Using chromium: ${executablePath || 'bundled'}`);
    console.log(`DOCKER_HOST: ${DOCKER_HOST}`);

    const browser = await chromium.launch(browserOptions);
    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: windowWidth, height: windowHeight },
    });

    // Inject playwright marker to disable react-scan
    await context.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });

    // Login as admin
    await loginAdmin(context);

    const page = await context.newPage();

    // Ensure output directory exists (relative to cwd, which is /app in Docker)
    const outputDir = path.resolve(process.cwd(), SNAPSHOT_OUTPUT_DIR);
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    // 1. Home page
    console.log('Capturing: Home page');
    await page.goto(BASE_URL);
    await waitForHydration(page);
    await waitForDemoReady(page, { timeout: 15000 });
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(outputDir, 'home.png'),
      fullPage: false,
    });

    // 2. Tournaments list
    console.log('Capturing: Tournaments list');
    await page.goto(`${BASE_URL}/tournaments`);
    await waitForHydration(page);
    await waitForDemoReady(page, { timeout: 15000 });
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(outputDir, 'tournaments.png'),
      fullPage: false,
    });

    // Get a tournament for detail pages - prefer one with 4+ teams for a good bracket view
    const tournamentsResponse = await context.request.get(`${API_URL}/tournaments/`, {
      failOnStatusCode: false,
      timeout: 30000,
    });
    const tournaments = await tournamentsResponse.json();
    const tournamentList = tournaments.results || tournaments;

    // Find a tournament with 4+ teams for a better bracket screenshot
    const tournament = tournamentList.find(
      (t: { team_count?: number }) => (t.team_count ?? 0) >= 4
    ) || tournamentList[0];

    if (tournament) {
      // 3. Tournament detail page
      console.log('Capturing: Tournament detail');
      await page.goto(`${BASE_URL}/tournament/${tournament.pk}`);
      await waitForHydration(page);
      await waitForDemoReady(page, { timeout: 15000 });
      await page.waitForTimeout(500);
      await page.screenshot({
        path: path.join(outputDir, 'tournament.png'),
        fullPage: false,
      });

      // 4. Bracket view (if tournament has bracket)
      console.log('Capturing: Bracket view');
      const bracketTab = page.locator('[data-testid="bracketTab"]');
      if (await bracketTab.isVisible().catch(() => false)) {
        await bracketTab.click();
        await page.waitForTimeout(500);
        await waitForBracketReady(page, { timeout: 10000 });

        // Wait for React Flow nodes to render
        await page.waitForSelector('.react-flow__node', { timeout: 10000 });

        // Wait for viewport positioning effect to complete
        await page.waitForTimeout(500);

        // Center the bracket using exposed fitView function
        await page.evaluate(() => {
          const win = window as Window & { bracketFitView?: () => void };
          if (win.bracketFitView) {
            win.bracketFitView();
          }
        });
        await page.waitForTimeout(400);

        await page.screenshot({
          path: path.join(outputDir, 'bracket.png'),
          fullPage: false,
        });
      }
    }

    await context.close();
    await browser.close();

    console.log('Site snapshots complete!');
    console.log(`Screenshots saved to: ${outputDir}`);
  });
});
