/**
 * CSV Import Demo - Video Recording
 *
 * Records a demo of creating a tournament via UI, then importing 40 players
 * (8 teams of 5) from a CSV file. Shows the full flow:
 *   1. Create tournament
 *   2. Upload CSV → preview → import
 *   3. Scroll through player list
 *   4. View teams
 *   5. Generate and view bracket
 *
 * Output: csv_import.webm (800x800)
 * Pipeline: just demo::csv → just demo::trim → just demo::gifs
 */

import { test, chromium, type Page, type Locator } from '@playwright/test';
import { loginAdmin, waitForHydration, DOCKER_HOST, API_URL } from '../fixtures/auth';
import { waitForDemoReady } from '../fixtures/demo-utils';
import * as path from 'path';
import * as fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BASE_URL = `https://${DOCKER_HOST}`;
const VIDEO_OUTPUT_DIR = 'demo-results/videos';
const DEMO_METADATA_FILE = path.join(VIDEO_OUTPUT_DIR, 'csv_import.demo.yaml');
const CSV_FIXTURE = path.resolve(__dirname, '../fixtures/csv/demo-import.csv');

// ---------------------------------------------------------------------------
// Cursor helpers
// ---------------------------------------------------------------------------

/** Inject a visible cursor dot that follows mouse events. */
function cursorInitScript() {
  function setup() {
    if (document.getElementById('demo-cursor')) return;
    const el = document.createElement('div');
    el.id = 'demo-cursor';
    el.style.cssText = [
      'position:fixed', 'width:20px', 'height:20px', 'border-radius:50%',
      'background:rgba(239,68,68,0.55)', 'border:2px solid white',
      'box-shadow:0 0 6px rgba(0,0,0,0.4)',
      'pointer-events:none', 'z-index:999999',
      'transform:translate(-50%,-50%)',
      'left:-40px', 'top:-40px',
    ].join(';');
    document.body.appendChild(el);
    document.addEventListener('mousemove', (e) => {
      el.style.left = e.clientX + 'px';
      el.style.top = e.clientY + 'px';
    });
  }
  if (document.body) setup();
  else document.addEventListener('DOMContentLoaded', setup);
}

/** Smoothly move the cursor to the centre of a locator (ease-in-out).
 *  Uses JS-based animation to bypass Playwright's slowMo. */
async function moveTo(page: Page, locator: Locator, durationMs = 500) {
  const box = await locator.boundingBox();
  if (!box) return;
  const tx = box.x + box.width / 2;
  const ty = box.y + box.height / 2;

  // Animate entirely in-page JS to avoid slowMo jitter on each mouse.move()
  await page.evaluate(
    ({ tx, ty, ms }) => {
      return new Promise<void>((resolve) => {
        const cursor = document.getElementById('demo-cursor');
        if (!cursor) { resolve(); return; }
        const fromX = parseFloat(cursor.style.left) || 400;
        const fromY = parseFloat(cursor.style.top) || 400;
        const steps = Math.max(12, Math.round(ms / 16));
        let i = 0;
        const tick = () => {
          i++;
          const t = i / steps;
          const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
          const x = fromX + (tx - fromX) * ease;
          const y = fromY + (ty - fromY) * ease;
          cursor.style.left = x + 'px';
          cursor.style.top = y + 'px';
          if (i < steps) requestAnimationFrame(tick);
          else resolve();
        };
        requestAnimationFrame(tick);
      });
    },
    { tx, ty, ms: durationMs },
  );
  // Move Playwright's internal mouse to final position (single call, no loop)
  await page.mouse.move(tx, ty);
}

/** Move cursor to element, pause briefly, then click. */
async function demoClick(page: Page, locator: Locator, moveMs = 500) {
  await moveTo(page, locator, moveMs);
  await page.waitForTimeout(120);
  await locator.click();
}

/** Smooth scroll by deltaY over durationMs. */
async function smoothScroll(page: Page, deltaY: number, durationMs: number) {
  await page.evaluate(
    ({ dy, ms }) => {
      return new Promise<void>((resolve) => {
        // The app uses a ScrollArea with id="outlet_root" as the scrollable container.
        // Find its inner viewport div (has data-radix-scroll-area-viewport).
        const root = document.getElementById('outlet_root');
        const el =
          root?.querySelector('[data-radix-scroll-area-viewport]') ||
          document.scrollingElement ||
          document.documentElement;
        const start = el.scrollTop;
        const steps = Math.max(1, Math.round(ms / 16));
        let i = 0;
        const tick = () => {
          i++;
          const t = i / steps;
          const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
          el.scrollTop = start + dy * ease;
          if (i < steps) requestAnimationFrame(tick);
          else resolve();
        };
        requestAnimationFrame(tick);
      });
    },
    { dy: deltaY, ms: durationMs },
  );
  // Wait for the animation to actually finish on screen
  await page.waitForTimeout(durationMs + 100);
}

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

test.describe('CSV Import Demo', () => {
  test('Import 40 players into a new tournament', async ({}) => {
    test.setTimeout(300_000);

    const width = 800;
    const height = 800;

    const videoDir = path.resolve(process.cwd(), VIDEO_OUTPUT_DIR);
    if (!fs.existsSync(videoDir)) {
      fs.mkdirSync(videoDir, { recursive: true });
    }

    let executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined;
    if (executablePath === '/usr/bin/chromium-browser') {
      executablePath = '/usr/lib/chromium/chromium';
    }

    const browser = await chromium.launch({
      headless: true,
      ...(executablePath && { executablePath }),
      slowMo: 100,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        `--window-size=${width},${height}`,
      ],
    });

    const recordingStartTime = Date.now();

    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width, height },
      recordVideo: { dir: videoDir, size: { width, height } },
    });

    // Inject cursor + playwright marker on every page load
    await context.addInitScript(cursorInitScript);
    await context.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });

    await loginAdmin(context);
    const page = await context.newPage();

    // =========================================================================
    // Step 0 — Reset demo data (delete leftover tournaments + stub users)
    // =========================================================================
    console.log('Step 0: Reset demo data');
    // Delete any existing "Demo CSV Import" tournaments and stub users via API
    await context.request.post(`${API_URL}/tests/demo/demo_csv_import/reset/`);

    // =========================================================================
    // Step 1 — Tournaments page (filtered to Test Organization)
    // =========================================================================
    console.log('Step 1: Navigate to tournaments (Test Organization)');
    await page.goto(`${BASE_URL}/tournaments?organization=4`);
    await waitForHydration(page);
    await waitForDemoReady(page, { timeout: 15000 });

    // =========================================================================
    // Step 2 — Create tournament (slow, with cursor)
    // =========================================================================
    console.log('Step 2: Create tournament');

    const createButton = page.getByRole('button', { name: /create tournament/i });
    await createButton.waitFor({ state: 'visible', timeout: 15000 });

    // Trim metadata — start video right when the page is ready
    const trimStartSeconds = (Date.now() - recordingStartTime) / 1000;
    console.log(`Video: trim first ${trimStartSeconds.toFixed(2)}s`);
    const metadataPath = path.resolve(process.cwd(), DEMO_METADATA_FILE);
    fs.writeFileSync(
      metadataPath,
      `# Auto-generated by CSV import demo\n` +
        `csv_import:\n` +
        `  video: csv_import.webm\n` +
        `  trim_start_seconds: ${trimStartSeconds.toFixed(2)}\n` +
        `recorded_at: ${new Date().toISOString()}\n`,
    );

    // Animated cursor move to the Create Tournament button
    await demoClick(page, createButton, 250);

    // Fill name with visible typing
    const nameInput = page.locator('[data-testid="tournament-name-input"]');
    await nameInput.waitFor({ state: 'visible', timeout: 10000 });
    await moveTo(page, nameInput, 100);
    await nameInput.click();
    await page.keyboard.type('Demo CSV Import', { delay: 35 });
    await page.waitForTimeout(300);

    // Select type
    const typeSelect = page.locator('[data-testid="tournament-type-select"]');
    await demoClick(page, typeSelect, 100);
    const typeOption = page.locator('[data-testid="tournament-type-double"]');
    await typeOption.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, typeOption, 80);
    await page.waitForTimeout(300);

    // Pick date — click trigger to open calendar, then click a day
    const datePicker = page.locator('[data-testid="tournament-date-picker"]');
    await demoClick(page, datePicker, 100);
    const calendar = page.locator('[data-slot="calendar"]');
    await calendar.waitFor({ state: 'visible', timeout: 5000 });
    await page.waitForTimeout(300);
    const dayButton = calendar.locator('[data-testid="calendar-day-15"]').first();
    await demoClick(page, dayButton, 100);
    await page.waitForTimeout(400);

    // Pick time
    const timePicker = page.locator('[data-testid="tournament-time-picker"]');
    await moveTo(page, timePicker, 80);
    await timePicker.click();
    await timePicker.fill('19:00');
    await page.waitForTimeout(300);

    // Select league (Demo CSV League, pk=4)
    const leagueSelect = page.locator('[data-testid="tournament-league-select"]');
    await demoClick(page, leagueSelect, 100);
    const leagueOption = page.locator('[data-testid="tournament-league-4"]');
    await leagueOption.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, leagueOption, 80);
    await page.waitForTimeout(300);

    // Submit
    const submitButton = page.locator('[data-testid="tournament-submit-button"]');
    await demoClick(page, submitButton, 100);
    await page.waitForLoadState('networkidle');

    // Wait for card to appear
    const createdCard = page
      .locator('[data-slot="card-title"]')
      .filter({ hasText: 'Demo CSV Import' })
      .first();
    await createdCard.scrollIntoViewIfNeeded();
    await createdCard.waitFor({ state: 'visible', timeout: 15000 });

    // =========================================================================
    // Step 3 — Click into tournament
    // =========================================================================
    console.log('Step 3: Navigate into tournament');
    const tournamentCard = page
      .locator('[data-testid^="tournament-card-"]')
      .filter({ hasText: 'Demo CSV Import' })
      .first();
    const viewButton = tournamentCard.getByRole('button', { name: 'View' });
    await demoClick(page, viewButton, 150);

    await page.locator('[data-testid="tournamentDetailPage"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });
    await waitForHydration(page);
    await page.waitForTimeout(1000);

    // Grab tournament PK from URL for bracket generation later
    const urlMatch = page.url().match(/\/tournament\/(\d+)/);
    const tournamentPk = urlMatch ? parseInt(urlMatch[1]) : null;
    console.log(`Tournament PK: ${tournamentPk}`);

    // =========================================================================
    // Step 4 — Open CSV Import modal
    // =========================================================================
    console.log('Step 4: Open CSV Import modal');
    const importButton = page.getByTestId('tournament-csv-import-btn');
    await importButton.waitFor({ state: 'visible', timeout: 10000 });
    await demoClick(page, importButton, 125);

    await page.getByRole('heading', { name: 'Import CSV' }).waitFor({
      state: 'visible',
      timeout: 5000,
    });
    await page.waitForTimeout(500);

    // =========================================================================
    // Step 5 — Upload CSV
    // =========================================================================
    console.log('Step 5: Upload CSV');
    const dropZone = page.getByText('Drop a CSV file here');
    await moveTo(page, dropZone, 100);
    await page.waitForTimeout(300);

    // Upload via hidden input + drop event (file chooser unreliable in headless)
    await page.evaluate(() => {
      const input = document.createElement('input');
      input.type = 'file';
      input.id = 'pw-csv-upload';
      input.style.display = 'none';
      document.body.appendChild(input);
    });
    await page.locator('#pw-csv-upload').setInputFiles(CSV_FIXTURE);
    await page.evaluate(() => {
      const input = document.getElementById('pw-csv-upload') as HTMLInputElement;
      const file = input.files?.[0];
      if (!file) return;
      const dt = new DataTransfer();
      dt.items.add(file);
      const target = document.querySelector('[class*="border-dashed"]');
      if (target) {
        target.dispatchEvent(new DragEvent('drop', {
          dataTransfer: dt,
          bubbles: true,
          cancelable: true,
        }));
      }
      input.remove();
    });

    await page.getByText('40 valid').waitFor({ state: 'visible', timeout: 10000 });
    await page.waitForTimeout(2000);

    // =========================================================================
    // Step 6 — Import
    // =========================================================================
    console.log('Step 6: Import 40 rows');
    const importBtn = page.getByRole('button', { name: /Import 40 row/ });
    await demoClick(page, importBtn, 100);

    await page.getByRole('button', { name: 'Done' }).waitFor({ state: 'visible', timeout: 30000 });
    await page.waitForTimeout(3000);

    // =========================================================================
    // Step 7 — Close modal
    // =========================================================================
    console.log('Step 7: Close modal');
    const doneBtn = page.getByRole('button', { name: 'Done' });
    await demoClick(page, doneBtn, 80);
    await page.waitForTimeout(1500);

    // =========================================================================
    // Step 8 — Scroll through player list
    // =========================================================================
    console.log('Step 8: Scroll through players');
    await smoothScroll(page, 800, 1250);
    await page.waitForTimeout(1000);

    // =========================================================================
    // Step 9 — Teams tab (scroll to top instantly, then click)
    // =========================================================================
    console.log('Step 9: Show teams');
    await page.evaluate(() => {
      const root = document.getElementById('outlet_root');
      const el = root?.querySelector('[data-radix-scroll-area-viewport]');
      if (el) el.scrollTop = 0;
    });
    const teamsTab = page.locator('[data-testid="teamsTab"]');
    await demoClick(page, teamsTab, 125);
    await page.locator('[data-testid="teamsTabContent"]').waitFor({
      state: 'visible',
      timeout: 10000,
    });
    await page.waitForTimeout(1500);

    // Scroll through teams
    await smoothScroll(page, 800, 1250);
    await page.waitForTimeout(1000);

    // =========================================================================
    // Step 10 — Bracket
    // =========================================================================
    console.log('Step 10: Generate and show bracket');
    await page.evaluate(() => {
      const root = document.getElementById('outlet_root');
      const el = root?.querySelector('[data-radix-scroll-area-viewport]');
      if (el) el.scrollTop = 0;
    });
    const bracketTab = page.locator('[data-testid="bracketTab"]');
    await demoClick(page, bracketTab, 125);
    await page.locator('[data-testid="bracketTabContent"]').waitFor({
      state: 'visible',
      timeout: 10000,
    });
    await page.waitForTimeout(1000);

    // Click Generate Bracket dropdown, then select "Seed by Team MMR"
    const generateBtn = page.locator('[data-testid="generateBracketButton"]');
    if (await generateBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await demoClick(page, generateBtn, 125);
      // Wait for dropdown to open, then click "Seed by Team MMR"
      const seedOption = page.locator('[data-testid="seedByTeamMmrOption"]');
      await seedOption.waitFor({ state: 'visible', timeout: 5000 });
      await demoClick(page, seedOption, 100);
      // Wait for bracket nodes to render
      await page.waitForSelector('.react-flow__node', { timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(3000);
    } else if (tournamentPk) {
      // Fallback: generate via test API
      console.log('Generating bracket via API...');
      await context.request.post(
        `${API_URL}/tests/demo/bracket/${tournamentPk}/generate/`,
      );
      await page.reload();
      await waitForHydration(page);
      await page.locator('[data-testid="bracketTab"]').click();
      await page.waitForSelector('.react-flow__node', { timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(3000);
    }

    // =========================================================================
    // Step 11 — Save bracket + pick a winner
    // =========================================================================
    console.log('Step 11: Save bracket and pick a winner');

    // Click Save
    const saveBtn = page.locator('[data-testid="saveBracketButton"]');
    if (await saveBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await demoClick(page, saveBtn, 100);
      await page.waitForTimeout(1500);
    }

    // Scroll down to center the bracket
    await smoothScroll(page, 300, 1000);
    await page.waitForTimeout(1000);

    // Pick winner for first match (winners bracket)
    const matchNode1 = page.locator('[data-testid="bracket-match-node"]').first();
    if (await matchNode1.isVisible({ timeout: 3000 }).catch(() => false)) {
      await demoClick(page, matchNode1, 100);
      await page.locator('[data-testid="matchStatsModal"]').waitFor({
        state: 'visible',
        timeout: 5000,
      }).catch(() => {});
      await page.waitForTimeout(800);

      const radiantWinsBtn1 = page.locator('[data-testid="radiantWinsButton"]');
      if (await radiantWinsBtn1.isVisible({ timeout: 3000 }).catch(() => false)) {
        await demoClick(page, radiantWinsBtn1, 100);
        await page.waitForTimeout(1500);
      }
      await page.keyboard.press('Escape');
      await page.waitForTimeout(800);
    }

    // Pick winner for second match (winners bracket) — populates losers bracket
    const matchNode2 = page.locator('[data-testid="bracket-match-node"]').nth(1);
    if (await matchNode2.isVisible({ timeout: 3000 }).catch(() => false)) {
      await demoClick(page, matchNode2, 100);
      await page.locator('[data-testid="matchStatsModal"]').waitFor({
        state: 'visible',
        timeout: 5000,
      }).catch(() => {});
      await page.waitForTimeout(800);

      const direWinsBtn = page.locator('[data-testid="direWinsButton"]');
      if (await direWinsBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await demoClick(page, direWinsBtn, 100);
        await page.waitForTimeout(1500);
      }
      await page.keyboard.press('Escape');
      await page.waitForTimeout(800);
    }

    // Scroll down to losers bracket
    await smoothScroll(page, 600, 1500);
    await page.waitForTimeout(1000);

    // Find first losers bracket match that has 2 real teams (no TBD slots).
    const losersMatchIndex = await page.evaluate(() => {
      const nodes = document.querySelectorAll('[data-testid="bracket-match-node"]');
      for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];
        // Losers bracket nodes have red-tinted background
        if (!node.className.includes('red-950')) continue;
        // Check both team slots are filled (no "TBD" text)
        const tbdSlots = node.querySelectorAll('.italic');
        if (tbdSlots.length === 0) return i;
      }
      return -1;
    });

    if (losersMatchIndex >= 0) {
      const losersMatch = page.locator('[data-testid="bracket-match-node"]').nth(losersMatchIndex);
      await losersMatch.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);
      await demoClick(page, losersMatch, 100);
      await page.locator('[data-testid="matchStatsModal"]').waitFor({
        state: 'visible',
        timeout: 5000,
      }).catch(() => {});
      await page.waitForTimeout(2000);
      await page.keyboard.press('Escape');
      await page.waitForTimeout(1000);
    }

    // =========================================================================
    // Save video
    // =========================================================================
    console.log('Saving video...');
    await page.close();
    await context.close();

    const videoFiles = fs.readdirSync(videoDir).filter((f) => f.endsWith('.webm'));
    if (videoFiles.length > 0) {
      const sorted = videoFiles
        .map((f) => ({ name: f, time: fs.statSync(path.join(videoDir, f)).mtimeMs }))
        .sort((a, b) => b.time - a.time);
      const src = path.join(videoDir, sorted[0].name);
      const dest = path.join(videoDir, 'csv_import.webm');
      if (src !== dest) {
        fs.copyFileSync(src, dest);
        console.log(`Video saved: ${dest}`);
      }
    }

    await browser.close();
    console.log('CSV Import demo complete!');
  });
});
