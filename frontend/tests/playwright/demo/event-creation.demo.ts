/**
 * Event Creation Demo - Video Recording
 *
 * Records a demo of creating a social event via the org Events tab.
 * Shows the full flow:
 *   1. Navigate to Events Test Org
 *   2. Click Events tab
 *   3. Create Event with name, tournament, league
 *   4. Configure Discord settings
 *   5. Set up recurring schedule (weekly)
 *   6. Submit and show the new repeater
 *
 * Output: event_creation.webm (800x800)
 * Pipeline: just demo::events → just demo::trim → just demo::gifs
 */

import { test, chromium, type Page, type Locator } from '@playwright/test';
import { loginAdmin, waitForHydration, DOCKER_HOST, API_URL } from '../fixtures/auth';
import { waitForDemoReady } from '../fixtures/demo-utils';
import * as path from 'path';
import * as fs from 'fs';

const BASE_URL = `https://${DOCKER_HOST}`;
const VIDEO_OUTPUT_DIR = 'demo-results/videos/event_creation';
const FINAL_VIDEO_DIR = '../docs/assets/videos';
const DEMO_METADATA_FILE = path.join('demo-results/videos', 'event_creation.demo.yaml');

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
// Helper: get today's date formatted as YYYY-MM-DD
// ---------------------------------------------------------------------------
function getTodayFormatted(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

test.describe('Event Creation Demo', () => {
  test('Create a recurring weekly event', async ({}) => {
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
    // Step 0 — Reset demo data (login already done in recording context)
    // =========================================================================
    console.log('Step 0: Reset events data and find org');
    // Use demo-reset to wipe ALL events/repeaters for a clean org page
    await context.request.post(`${API_URL}/tests/events/demo-reset/`);

    // Find the Events Test Org dynamically (PK may differ across environments)
    const orgsResp = await context.request.get(`${API_URL}/organizations/`);
    const orgs = await orgsResp.json();
    const eventsOrg = orgs.find((o: { name: string }) => o.name === 'Events Test Org');
    if (!eventsOrg) throw new Error('Events Test Org not found — run just db::populate::all');
    const orgPk = eventsOrg.pk;
    // Find the league for this org (events were wiped, so get from leagues API)
    const leaguesResp = await context.request.get(`${API_URL}/leagues/?organization=${orgPk}`);
    const leagues = await leaguesResp.json();
    const leaguePk = leagues[0]?.pk ?? orgPk;
    console.log(`Found Events Test Org: pk=${orgPk}, league=${leaguePk}`);

    // =========================================================================
    // Step 1 — Navigate to Events Test Org
    // =========================================================================
    console.log('Step 1: Navigate to Events Test Org');
    await page.goto(`${BASE_URL}/organizations/${orgPk}`);
    await waitForHydration(page);
    await waitForDemoReady(page, { timeout: 15000 });

    // Trim metadata — start video right when the page is ready
    const trimStartSeconds = (Date.now() - recordingStartTime) / 1000;
    console.log(`Video: trim first ${trimStartSeconds.toFixed(2)}s`);
    const metadataPath = path.resolve(process.cwd(), DEMO_METADATA_FILE);
    fs.writeFileSync(
      metadataPath,
      `# Auto-generated by event creation demo\n` +
        `event_creation:\n` +
        `  video: event_creation.webm\n` +
        `  trim_start_seconds: ${trimStartSeconds.toFixed(2)}\n` +
        `recorded_at: ${new Date().toISOString()}\n`,
    );

    // Pause to show the organization page before clicking Events tab
    await page.waitForTimeout(2000);

    // =========================================================================
    // Step 2 — Click Events tab
    // =========================================================================
    console.log('Step 2: Click Events tab');
    const eventsTab = page.locator('[data-testid="org-tab-events"]');
    await eventsTab.waitFor({ state: 'visible', timeout: 10000 });
    await demoClick(page, eventsTab, 250);
    await page.waitForTimeout(1000);

    // =========================================================================
    // Step 3 — Click "Create Event" button → modal opens
    // =========================================================================
    console.log('Step 3: Click Create Event button');
    const createEventBtn = page.locator('[data-testid="create-event-btn"]');
    await createEventBtn.waitFor({ state: 'visible', timeout: 10000 });
    await demoClick(page, createEventBtn, 250);

    // Wait for modal to appear
    const dialog = page.locator('[role="dialog"]');
    await dialog.waitFor({ state: 'visible', timeout: 10000 });

    // =========================================================================
    // Step 4 — Wait 3s for org defaults to load
    // =========================================================================
    console.log('Step 4: Wait for org defaults to load');
    await page.waitForTimeout(3000);

    // =========================================================================
    // Step 5 — Fill Event Name: "Wednesday Inhouse"
    // =========================================================================
    console.log('Step 5: Fill event name');
    const eventNameInput = page.locator('[data-testid="event-name-input"]');
    await eventNameInput.waitFor({ state: 'visible', timeout: 5000 });
    await moveTo(page, eventNameInput, 300);
    await eventNameInput.click();
    await eventNameInput.fill('');
    await page.keyboard.type('Wednesday Inhouse', { delay: 35 });
    await page.waitForTimeout(300);

    // =========================================================================
    // Step 6 — Fill Tournament Name: "Inhouse #42"
    // =========================================================================
    console.log('Step 6: Fill tournament name');
    const tournamentNameInput = page.locator('[data-testid="event-tournament-name-input"]');
    await tournamentNameInput.waitFor({ state: 'visible', timeout: 5000 });
    await moveTo(page, tournamentNameInput, 300);
    await tournamentNameInput.click();
    await tournamentNameInput.fill('');
    await page.keyboard.type('Inhouse #42', { delay: 35 });
    await page.waitForTimeout(300);

    // =========================================================================
    // Step 7 — Select League: "Events Test League"
    // =========================================================================
    console.log('Step 7: Select league');
    const leagueSelect = page.locator('[data-testid="event-league-select"]');
    await leagueSelect.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, leagueSelect, 300);
    await page.waitForTimeout(300);

    const leagueOption = page.getByRole('option', { name: 'Events Test League' });
    await leagueOption.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, leagueOption, 200);
    await page.waitForTimeout(300);

    // =========================================================================
    // Step 8 — Pause 1s to show filled form
    // =========================================================================
    console.log('Step 8: Pause to show filled form');
    await page.waitForTimeout(1000);

    // =========================================================================
    // Step 9 — Click Discord tab → pause 2s to show Discord config
    // =========================================================================
    console.log('Step 9: Click Discord tab');
    const discordTab = page.locator('[data-testid="event-modal-tab-discord"]');
    await discordTab.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, discordTab, 300);
    await page.waitForTimeout(2000);

    // =========================================================================
    // Step 10 — Click back to Event tab
    // =========================================================================
    console.log('Step 10: Click back to Event tab');
    const eventTab = page.locator('[data-testid="event-modal-tab-event"]');
    await eventTab.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, eventTab, 300);
    await page.waitForTimeout(500);

    // =========================================================================
    // Step 11 — Click Recurring checkbox → show fields
    // =========================================================================
    console.log('Step 11: Enable recurring');
    const recurringCheckbox = page.locator('[data-testid="event-recurring-checkbox"]');
    await recurringCheckbox.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, recurringCheckbox, 300);
    await page.waitForTimeout(500);

    // =========================================================================
    // Step 12 — Select Frequency → "Weekly"
    // =========================================================================
    console.log('Step 12: Select frequency Weekly');
    const frequencySelect = page.locator('[data-testid="event-frequency-select"]');
    await frequencySelect.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, frequencySelect, 300);
    await page.waitForTimeout(300);

    const weeklyOption = page.getByRole('option', { name: 'Weekly' });
    await weeklyOption.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, weeklyOption, 200);
    await page.waitForTimeout(300);

    // =========================================================================
    // Step 13 — Select Day → "Wednesday"
    // =========================================================================
    console.log('Step 13: Select day Wednesday');
    const daySelect = page.locator('[data-testid="event-day-select"]');
    await daySelect.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, daySelect, 300);
    await page.waitForTimeout(300);

    const wednesdayOption = page.getByRole('option', { name: 'Wednesday' });
    await wednesdayOption.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, wednesdayOption, 200);
    await page.waitForTimeout(300);

    // =========================================================================
    // Step 14 — Fill Time: "20:00"
    // =========================================================================
    console.log('Step 14: Fill time');
    const timeInput = page.locator('[data-testid="event-time-input"]');
    await timeInput.waitFor({ state: 'visible', timeout: 5000 });
    await moveTo(page, timeInput, 300);
    await timeInput.click();
    await page.keyboard.type('20:00', { delay: 35 });
    await page.waitForTimeout(300);

    // =========================================================================
    // Step 15 — Fill Start date: today
    // =========================================================================
    console.log('Step 15: Fill start date');
    const startsInput = page.locator('[data-testid="event-starts-input"]');
    await startsInput.waitFor({ state: 'visible', timeout: 5000 });
    await moveTo(page, startsInput, 300);
    await startsInput.click();
    await page.keyboard.type(getTodayFormatted(), { delay: 35 });
    await page.waitForTimeout(300);

    // =========================================================================
    // Step 16 — Pause 1.5s to show completed form
    // =========================================================================
    console.log('Step 16: Pause to show completed form');
    await page.waitForTimeout(1500);

    // =========================================================================
    // Step 17 — Submit → wait for modal close
    // =========================================================================
    console.log('Step 17: Submit form');
    const submitBtn = page.locator('[data-testid="form-dialog-submit"]');
    await submitBtn.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, submitBtn, 300);

    // Wait for modal to close
    await dialog.waitFor({ state: 'hidden', timeout: 15000 });
    console.log('Step 17b: Modal closed');

    // =========================================================================
    // Step 18 — Pause 2s to show org page with new repeater
    // =========================================================================
    console.log('Step 18: Show org page with new repeater');
    await page.waitForTimeout(2000);

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
      // Copy to docs/assets/videos/ which is OUTSIDE Playwright's outputDir
      // (Playwright cleans outputDir between test runs, so demo-results/ is unsafe)
      const finalDir = path.resolve(process.cwd(), FINAL_VIDEO_DIR);
      if (!fs.existsSync(finalDir)) fs.mkdirSync(finalDir, { recursive: true });
      const dest = path.join(finalDir, 'event_creation.webm');
      fs.copyFileSync(src, dest);
      console.log(`Video saved: ${dest}`);
    }

    await browser.close();
    console.log('Event Creation demo complete!');
  });
});
