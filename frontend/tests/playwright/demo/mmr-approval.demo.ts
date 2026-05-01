/**
 * MMR Approval Demo - Video Recording
 *
 * Records a short 5-10s demo of the admin MMR approval workflow:
 *   1. Navigate to event page with signups
 *   2. Click Signups tab
 *   3. Click Approve on a player → modal opens
 *   4. Review profile data + screenshot
 *   5. Set MMR and approve
 *
 * Output: mmr_approval.webm (1200x800)
 * Pipeline: just demo::mmr-approval → just demo::trim → just demo::gifs
 */

import { test, chromium, type Page, type Locator } from '@playwright/test';
import { loginAdmin, waitForHydration, DOCKER_HOST, API_URL } from '../fixtures/auth';
import { waitForDemoReady } from '../fixtures/demo-utils';
import { postWithCsrf, getCsrfToken } from '../fixtures/events';
import * as path from 'path';
import * as fs from 'fs';

const BASE_URL = `https://${DOCKER_HOST}`;
const VIDEO_OUTPUT_DIR = 'demo-results/videos/mmr_approval';
const FINAL_VIDEO_DIR = '../docs/assets/videos';

// ---------------------------------------------------------------------------
// Cursor helpers (same pattern as other demos)
// ---------------------------------------------------------------------------

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

async function moveTo(page: Page, locator: Locator, durationMs = 400) {
  const box = await locator.boundingBox();
  if (!box) return;
  const tx = box.x + box.width / 2;
  const ty = box.y + box.height / 2;
  await page.evaluate(
    ({ tx, ty, ms }) => {
      return new Promise<void>((resolve) => {
        const cursor = document.getElementById('demo-cursor');
        if (!cursor) { resolve(); return; }
        const fromX = parseFloat(cursor.style.left) || 600;
        const fromY = parseFloat(cursor.style.top) || 400;
        const steps = Math.max(12, Math.round(ms / 16));
        let i = 0;
        const tick = () => {
          i++;
          const t = i / steps;
          const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
          cursor.style.left = (fromX + (tx - fromX) * ease) + 'px';
          cursor.style.top = (fromY + (ty - fromY) * ease) + 'px';
          if (i < steps) requestAnimationFrame(tick);
          else resolve();
        };
        requestAnimationFrame(tick);
      });
    },
    { tx, ty, ms: durationMs },
  );
  await page.mouse.move(tx, ty);
}

async function demoClick(page: Page, locator: Locator, moveMs = 400) {
  await moveTo(page, locator, moveMs);
  await page.waitForTimeout(100);
  await locator.click();
}

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

test.describe('MMR Approval Demo', () => {
  test('Approve signup with MMR modal', async ({}) => {
    test.setTimeout(120_000);

    const width = 1200;
    const height = 800;

    const videoDir = path.resolve(process.cwd(), VIDEO_OUTPUT_DIR);
    if (!fs.existsSync(videoDir)) fs.mkdirSync(videoDir, { recursive: true });

    let executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined;
    if (executablePath === '/usr/bin/chromium-browser') {
      executablePath = '/usr/lib/chromium/chromium';
    }

    const browser = await chromium.launch({
      headless: true,
      ...(executablePath && { executablePath }),
      slowMo: 80,
      args: [
        '--no-sandbox', '--disable-setuid-sandbox',
        '--disable-dev-shm-usage', '--disable-gpu',
        `--window-size=${width},${height}`,
      ],
    });

    const recordingStartTime = Date.now();

    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width, height },
      recordVideo: { dir: videoDir, size: { width, height } },
    });

    await context.addInitScript(cursorInitScript);
    await context.addInitScript(() => {
      (window as Window & { playwright?: boolean }).playwright = true;
    });

    // Login as admin (pk=5000)
    await context.request.post(`${API_URL}/tests/login-as/`, {
      data: { user_pk: 5000 },
      headers: { 'Content-Type': 'application/json' },
    });

    const page = await context.newPage();

    // =========================================================================
    // Setup: Create event with signups + player profiles already populated
    // =========================================================================
    console.log('Setup: Reset events and create event with signups');
    await context.request.post(`${API_URL}/tests/events/reset/`);

    // Create event with manual approval
    const csrfToken = await getCsrfToken(context);
    const createResp = await context.request.post(`${API_URL}/events/?open_signups=true`, {
      data: {
        organization: 7, // Events Test Org
        name: 'Wednesday Inhouse #42',
        description: 'Weekly inhouse — manual MMR approval required',
        scheduled_at: new Date(Date.now() + 86400000).toISOString(),
        tournament_name: 'Inhouse Tournament',
        tournament_league: 7, // Events Test League
        tournament_type: 'single_elimination',
        game_type: 1,
        draft_type: 'shuffle',
        people_per_team: 5,
        number_of_teams: 2,
        max_players: 10,
        auto_approve: false,
        timezone: 'America/New_York',
      },
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    });
    const event = await createResp.json();
    const eventId = event.id;

    // RSVP as player 1 (pk=5001, has DotaProfile with Legend 3, screenshot)
    await context.request.post(`${API_URL}/tests/login-as/`, {
      data: { user_pk: 5001 },
      headers: { 'Content-Type': 'application/json' },
    });
    const csrf2 = (await context.cookies()).find(c => c.name === 'csrftoken')?.value || '';
    await context.request.post(`${API_URL}/events/${eventId}/rsvp/`, {
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf2 },
    });

    // RSVP as player 2 (pk=5002, has DotaProfile with Ancient 1)
    await context.request.post(`${API_URL}/tests/login-as/`, {
      data: { user_pk: 5002 },
      headers: { 'Content-Type': 'application/json' },
    });
    const csrf3 = (await context.cookies()).find(c => c.name === 'csrftoken')?.value || '';
    await context.request.post(`${API_URL}/events/${eventId}/rsvp/`, {
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf3 },
    });

    // Switch back to admin
    await context.request.post(`${API_URL}/tests/login-as/`, {
      data: { user_pk: 5000 },
      headers: { 'Content-Type': 'application/json' },
    });

    // =========================================================================
    // Step 1 — Navigate to event page (video starts here)
    // =========================================================================
    console.log('Step 1: Navigate to event page');
    await page.goto(`${BASE_URL}/events/${eventId}`);
    await waitForHydration(page);
    await waitForDemoReady(page, { timeout: 10000 });

    const trimStartSeconds = (Date.now() - recordingStartTime) / 1000;
    console.log(`Video: trim first ${trimStartSeconds.toFixed(2)}s`);

    await page.waitForTimeout(800);

    // =========================================================================
    // Step 2 — Click Signups tab
    // =========================================================================
    console.log('Step 2: Click Signups tab');
    const signupsTab = page.getByTestId('event-tab-signups');
    await signupsTab.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, signupsTab, 300);
    await page.waitForTimeout(800);

    // =========================================================================
    // Step 3 — Click Approve on first player → modal opens
    // =========================================================================
    console.log('Step 3: Click Approve button');
    // Find the first Approve button in the signups list
    const approveBtn = page.getByText('Approve').first();
    await approveBtn.waitFor({ state: 'visible', timeout: 5000 });
    await demoClick(page, approveBtn, 300);

    // Wait for modal
    const modal = page.locator('[role="dialog"]');
    await modal.waitFor({ state: 'visible', timeout: 5000 });
    await page.waitForTimeout(1000);

    // =========================================================================
    // Step 4 — Review profile data in modal (pause to show)
    // =========================================================================
    console.log('Step 4: Review profile data');
    await page.waitForTimeout(1500);

    // =========================================================================
    // Step 5 — Set MMR and approve
    // =========================================================================
    console.log('Step 5: Set MMR and approve');
    const mmrInput = modal.locator('input[type="number"]');
    await mmrInput.waitFor({ state: 'visible', timeout: 3000 });
    await moveTo(page, mmrInput, 300);
    await mmrInput.click();
    await mmrInput.fill('');
    await page.keyboard.type('3500', { delay: 60 });
    await page.waitForTimeout(500);

    // Click approve button in modal
    const confirmBtn = modal.getByTestId('mmr-modal-approve');
    await demoClick(page, confirmBtn, 300);

    // Wait for modal to close
    await modal.waitFor({ state: 'hidden', timeout: 10000 });
    console.log('Step 5b: Modal closed, signup approved');

    // =========================================================================
    // Step 6 — Show result (approved status)
    // =========================================================================
    await page.waitForTimeout(1500);

    // =========================================================================
    // Save video
    // =========================================================================
    console.log('Saving video...');
    await page.close();
    await context.close();

    const videoFiles = fs.readdirSync(videoDir).filter(f => f.endsWith('.webm'));
    if (videoFiles.length > 0) {
      const sorted = videoFiles
        .map(f => ({ name: f, time: fs.statSync(path.join(videoDir, f)).mtimeMs }))
        .sort((a, b) => b.time - a.time);
      const src = path.join(videoDir, sorted[0].name);
      const finalDir = path.resolve(process.cwd(), FINAL_VIDEO_DIR);
      if (!fs.existsSync(finalDir)) fs.mkdirSync(finalDir, { recursive: true });
      const dest = path.join(finalDir, 'mmr_approval.webm');
      fs.copyFileSync(src, dest);
      console.log(`Video saved: ${dest}`);

      // Write trim metadata
      const metaDir = path.resolve(process.cwd(), 'demo-results/videos');
      if (!fs.existsSync(metaDir)) fs.mkdirSync(metaDir, { recursive: true });
      fs.writeFileSync(
        path.join(metaDir, 'mmr_approval.demo.yaml'),
        `mmr_approval:\n  video: mmr_approval.webm\n  trim_start_seconds: ${trimStartSeconds.toFixed(2)}\nrecorded_at: ${new Date().toISOString()}\n`,
      );
    }

    await browser.close();
    console.log('MMR Approval demo complete!');
  });
});
