/**
 * Roll Call Demo - Video Recording
 *
 * Records a demo of a 20-player roll call flow for an event.
 * Shows the full flow:
 *   1. View event with signups
 *   2. Browse through signed-up players
 *   3. Start roll call
 *   4. Confirm 10 players
 *   5. Start tournament from confirmed players
 *
 * Output: roll_call.webm (1000x800)
 * Pipeline: just demo::rollcall → just demo::trim → just demo::gifs
 */

import { test, chromium, type Page, type Locator } from '@playwright/test';
import { loginAdmin, waitForHydration, DOCKER_HOST, API_URL } from '../fixtures/auth';
import { waitForDemoReady } from '../fixtures/demo-utils';
import * as path from 'path';
import * as fs from 'fs';

const BASE_URL = `https://${DOCKER_HOST}`;
const VIDEO_OUTPUT_DIR = 'demo-results/videos';
const DEMO_METADATA_FILE = path.join(VIDEO_OUTPUT_DIR, 'roll_call.demo.yaml');

const PLAYER_PKS = Array.from({ length: 20 }, (_, i) => 1081 + i);

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
        const fromX = parseFloat(cursor.style.left) || 500;
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

test.describe('Roll Call Demo', () => {
  test('20-player roll call flow', async ({}) => {
    test.setTimeout(300_000);

    const width = 1000;
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
    // Step 0 — Reset and prepare event data (all in recording context)
    // =========================================================================
    console.log('Step 0: Reset events data and bulk RSVP');

    // Reset events data
    const resetResponse = await context.request.post(
      `${API_URL}/tests/events/reset/`,
      { failOnStatusCode: false },
    );
    console.log(`Step 0: Reset response: ${resetResponse.status()}`);

    // Find the Events Test Org dynamically
    const orgsResp = await context.request.get(`${API_URL}/organizations/`);
    const orgs = await orgsResp.json();
    const eventsOrg = orgs.find((o: { name: string }) => o.name === 'Events Test Org');
    if (!eventsOrg) throw new Error('Events Test Org not found — run just db::populate::all');
    const orgPk = eventsOrg.pk;

    // Get the E2E Signup Event
    const eventsResponse = await context.request.get(
      `${API_URL}/events/?organization=${orgPk}`,
      { failOnStatusCode: false },
    );
    console.log(`Step 0: Events response: ${eventsResponse.status()}`);

    const eventsData = await eventsResponse.json();
    const signupEvent = Array.isArray(eventsData)
      ? eventsData.find((e: { name?: string }) => e.name === 'E2E Signup Event')
      : eventsData.results?.find((e: { name?: string }) => e.name === 'E2E Signup Event');

    if (!signupEvent) {
      throw new Error(`Could not find "E2E Signup Event" in organization ${orgPk}`);
    }

    const eventPk = signupEvent.pk || signupEvent.id;
    console.log(`Step 0: Found E2E Signup Event (pk=${eventPk})`);

    // Bulk RSVP all 20 players
    const bulkRsvpResponse = await context.request.post(
      `${API_URL}/tests/events/${eventPk}/bulk-rsvp/`,
      {
        data: { user_pks: PLAYER_PKS },
        failOnStatusCode: false,
      },
    );
    console.log(`Step 0: Bulk RSVP response: ${bulkRsvpResponse.status()}`);

    // =========================================================================
    // Step 1 — Navigate to the E2E Signup Event
    // =========================================================================
    console.log('Step 1: Navigate to event page');
    await page.goto(`${BASE_URL}/events/${eventPk}`);
    await waitForHydration(page);
    await waitForDemoReady(page, { timeout: 15000 });

    // Trim metadata — start video right when the page is ready
    const trimStartSeconds = (Date.now() - recordingStartTime) / 1000;
    console.log(`Video: trim first ${trimStartSeconds.toFixed(2)}s`);
    const metadataPath = path.resolve(process.cwd(), DEMO_METADATA_FILE);
    fs.writeFileSync(
      metadataPath,
      `# Auto-generated by roll call demo\n` +
        `roll_call:\n` +
        `  video: roll_call.webm\n` +
        `  trim_start_seconds: ${trimStartSeconds.toFixed(2)}\n` +
        `recorded_at: ${new Date().toISOString()}\n`,
    );

    // =========================================================================
    // Step 2 — Pause to show event header with "Signups Open" badge
    // =========================================================================
    console.log('Step 2: Show event header');
    await page.waitForTimeout(1500);

    // =========================================================================
    // Step 3 — Click Signups tab
    // =========================================================================
    console.log('Step 3: Click Signups tab');
    const signupsTab = page.locator('[data-testid="event-tab-signups"]');
    await signupsTab.waitFor({ state: 'visible', timeout: 10000 });
    await demoClick(page, signupsTab, 250);
    await page.waitForTimeout(1000);

    // =========================================================================
    // Step 4 — Scroll down to show UserStrips with avatars, positions, MMR
    // =========================================================================
    console.log('Step 4: Scroll through signups');
    await smoothScroll(page, 600, 2000);
    await page.waitForTimeout(500);

    // =========================================================================
    // Step 5 — Scroll back up
    // =========================================================================
    console.log('Step 5: Scroll back up');
    await smoothScroll(page, -600, 1500);
    await page.waitForTimeout(500);

    // =========================================================================
    // Step 6 — Click "Start Roll Call" button
    // =========================================================================
    console.log('Step 6: Click Start Roll Call');
    const startRollCallBtn = page.locator('[data-testid="event-start-rollcall-btn"]');
    await startRollCallBtn.waitFor({ state: 'visible', timeout: 10000 });
    await demoClick(page, startRollCallBtn, 300);

    // =========================================================================
    // Step 7 — Wait for confirmation dialog
    // =========================================================================
    console.log('Step 7: Confirmation dialog');
    const dialog = page.locator('[role="alertdialog"]');
    await dialog.waitFor({ state: 'visible', timeout: 10000 });
    await page.waitForTimeout(500);

    // =========================================================================
    // Step 8 — Click confirm button in dialog
    // =========================================================================
    console.log('Step 8: Confirm start roll call');
    const confirmBtn = dialog.locator('button', { hasText: /confirm|continue|yes|start/i });
    await confirmBtn.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, confirmBtn, 200);

    // =========================================================================
    // Step 9 — Wait for navigation to /rollcall/{eventPk}
    // =========================================================================
    console.log('Step 9: Wait for roll call page');
    await page.waitForURL(`**/rollcall/${eventPk}`, { timeout: 15000 });
    await waitForHydration(page);
    await waitForDemoReady(page, { timeout: 15000 });

    // =========================================================================
    // Step 10 — Pause to show roll call page header with player count
    // =========================================================================
    console.log('Step 10: Show roll call page header');
    await page.waitForTimeout(1500);

    // =========================================================================
    // Step 11 — Scroll through "Awaiting Confirmation" section
    // =========================================================================
    console.log('Step 11: Scroll through awaiting confirmation');
    await smoothScroll(page, 500, 2000);
    await page.waitForTimeout(500);
    await smoothScroll(page, -500, 1000);
    await page.waitForTimeout(500);

    // =========================================================================
    // Step 12 — Confirm 10 players (click "Confirm" buttons with pause)
    // =========================================================================
    console.log('Step 12: Confirm 10 players');
    for (let i = 0; i < 10; i++) {
      // Each iteration picks the first visible "Confirm" button in the awaiting section
      const confirmPlayerBtn = page
        .locator('[data-testid="rollcall-confirm-btn"]')
        .first();

      try {
        await confirmPlayerBtn.waitFor({ state: 'visible', timeout: 5000 });
        await demoClick(page, confirmPlayerBtn, 200);
        await page.waitForTimeout(300);
      } catch {
        console.log(`Could not find confirm button for player ${i + 1}, skipping`);
        break;
      }
    }

    // =========================================================================
    // Step 13 — Pause to show "Confirmed" section with count
    // =========================================================================
    console.log('Step 13: Show confirmed section');
    await page.waitForTimeout(1000);

    // =========================================================================
    // Step 14 — Scroll up to see the "Start Tournament" button
    // =========================================================================
    console.log('Step 14: Scroll to Start Tournament');
    await page.evaluate(() => {
      const root = document.getElementById('outlet_root');
      const el = root?.querySelector('[data-radix-scroll-area-viewport]');
      if (el) el.scrollTop = 0;
    });
    await page.waitForTimeout(500);

    // =========================================================================
    // Step 15 — Click "Start Tournament"
    // =========================================================================
    console.log('Step 15: Click Start Tournament');
    const startTournamentBtn = page.locator('[data-testid="rollcall-start-btn"]');
    await startTournamentBtn.waitFor({ state: 'visible', timeout: 10000 });
    await demoClick(page, startTournamentBtn, 300);

    // =========================================================================
    // Step 16 — Wait for confirmation dialog
    // =========================================================================
    console.log('Step 16: Start Tournament confirmation dialog');
    const tournamentDialog = page.locator('[role="alertdialog"]');
    await tournamentDialog.waitFor({ state: 'visible', timeout: 10000 });
    await page.waitForTimeout(500);

    // =========================================================================
    // Step 17 — Click confirm
    // =========================================================================
    console.log('Step 17: Confirm start tournament');
    const tournamentConfirmBtn = tournamentDialog.locator(
      'button',
      { hasText: /confirm|continue|yes|start/i },
    );
    await tournamentConfirmBtn.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, tournamentConfirmBtn, 200);

    // =========================================================================
    // Step 18 — App auto-navigates to tournament page, show it with players
    // =========================================================================
    console.log('Step 18: Show tournament page with players');
    await page.waitForURL(/\/tournament\//, { timeout: 10000 });
    await page.waitForTimeout(3000); // Show the tournament with confirmed players

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
      const dest = path.join(videoDir, 'roll_call.webm');
      if (src !== dest) {
        fs.copyFileSync(src, dest);
        console.log(`Video saved: ${dest}`);
      }
    }

    await browser.close();
    console.log('Roll Call demo complete!');
  });
});
