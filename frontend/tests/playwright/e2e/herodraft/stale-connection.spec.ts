import { test, expect, chromium, BrowserContext, Page, WebSocket as PWWebSocket } from '@playwright/test';
import { loginAsDiscordId, loginUser, waitForHydration } from '../../fixtures/auth';
import { HeroDraftPage } from '../../helpers/HeroDraftPage';

const API_URL = 'https://localhost/api';
const BASE_URL = 'https://localhost';

/**
 * Stale WebSocket Connection Detection Tests
 *
 * Verifies the defense-in-depth solution for WebSocket connections dying
 * during PAUSED state:
 *
 * 1. Server sends ping messages every 1s to keep connections alive
 * 2. Client detects stale connections (3s without messages) and reconnects
 *
 * Root cause: During PAUSED state, the tick broadcaster stops sending timer
 * updates. With no messages flowing, Cloudflare's ~100s idle timeout silently
 * kills the WebSocket. The browser still thinks it's connected, so when the
 * draft resumes, the pick timer never updates.
 */
test.describe('HeroDraft Stale Connection Detection', () => {
  test.setTimeout(60000);

  async function createContext(
    browser: Awaited<ReturnType<typeof chromium.launch>>,
  ): Promise<BrowserContext> {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    // Track all WebSocket instances so tests can force-close them
    await context.addInitScript(() => {
      const OriginalWebSocket = window.WebSocket;
      (window as any).__wsInstances = [] as WebSocket[];
      (window as any).WebSocket = new Proxy(OriginalWebSocket, {
        construct(target, args) {
          const ws = new target(...(args as [string, string | string[] | undefined]));
          (window as any).__wsInstances.push(ws);
          return ws;
        },
      });
    });
    return context;
  }

  async function getTestDraft(context: BrowserContext) {
    const response = await context.request.get(
      `${API_URL}/tests/herodraft-by-key/waiting_phase/`,
      { failOnStatusCode: false, timeout: 10000 },
    );
    if (!response.ok()) {
      throw new Error(`Failed to get test data: ${response.status()}`);
    }
    return response.json();
  }

  /**
   * Connect a spectator (non-captain) to the draft and return the page,
   * HeroDraftPage helper, and the captured Playwright WebSocket handle.
   */
  async function setupSpectator(
    context: BrowserContext,
    matchUrl: string,
  ): Promise<{ page: Page; draftPage: HeroDraftPage; ws: PWWebSocket }> {
    await loginUser(context);
    const page = await context.newPage();

    const wsPromise = page.waitForEvent('websocket', {
      predicate: (ws) => ws.url().includes('/api/herodraft/'),
      timeout: 15000,
    });

    await page.goto(matchUrl);
    await waitForHydration(page);

    const startBtn = page.getByTestId('view-draft-btn');
    await startBtn.click();

    const draftPage = new HeroDraftPage(page);
    await draftPage.waitForModal();
    await draftPage.waitForConnection();

    const ws = await wsPromise;
    return { page, draftPage, ws };
  }

  test('server sends ping messages during PAUSED state', async () => {
    const browser = await chromium.launch({
      headless: true,
      args: ['--disable-web-security', '--ignore-certificate-errors', '--no-sandbox'],
    });

    let context: BrowserContext | null = null;

    try {
      context = await createContext(browser);
      const testInfo = await getTestDraft(context);
      const draftPk = testInfo.pk;
      const tournamentPk = testInfo.game.tournament_pk;
      const gamePk = testInfo.game.pk;
      const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

      // Reset draft to waiting_for_captains (no tick messages — only pings)
      await context.request.post(`${API_URL}/tests/herodraft/${draftPk}/reset/`);

      const { draftPage, ws } = await setupSpectator(context, matchUrl);

      // Collect ping frames over 5 seconds
      const pings: number[] = [];
      ws.on('framereceived', (frame) => {
        try {
          const data = JSON.parse(frame.payload as string);
          if (data.type === 'ping') {
            pings.push(Date.now());
          }
        } catch {
          // ignore non-JSON frames
        }
      });

      await new Promise((r) => setTimeout(r, 5000));

      console.log(`Received ${pings.length} ping frames in 5 seconds`);

      // Server sends every 1s, expect at least 3 pings in 5 seconds
      expect(pings.length).toBeGreaterThanOrEqual(3);
      await draftPage.assertConnected();
    } finally {
      if (context) await context.close().catch(() => {});
      await browser.close();
    }
  });

  test('connection stays alive during extended PAUSED period', async () => {
    const browser = await chromium.launch({
      headless: true,
      args: ['--disable-web-security', '--ignore-certificate-errors', '--no-sandbox'],
    });

    let context: BrowserContext | null = null;

    try {
      context = await createContext(browser);
      const testInfo = await getTestDraft(context);
      const draftPk = testInfo.pk;
      const tournamentPk = testInfo.game.tournament_pk;
      const gamePk = testInfo.game.pk;
      const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

      await context.request.post(`${API_URL}/tests/herodraft/${draftPk}/reset/`);

      const { draftPage, ws } = await setupSpectator(context, matchUrl);

      // Track whether the connection drops at any point
      let connectionDropped = false;
      ws.on('close', () => {
        connectionDropped = true;
      });

      // Wait 15 seconds — well past the 3s stale timeout.
      // Without server pings, stale detection would fire at 3s.
      // With pings every 1s, connection should stay alive indefinitely.
      console.log('Waiting 15 seconds to verify connection stays alive...');
      await new Promise((r) => setTimeout(r, 15000));

      expect(connectionDropped).toBe(false);
      await draftPage.assertConnected();

      console.log('Connection stayed alive for 15s during PAUSED state');
    } finally {
      if (context) await context.close().catch(() => {});
      await browser.close();
    }
  });

  test('client reconnects after WebSocket is force-closed', async () => {
    const browser = await chromium.launch({
      headless: true,
      args: ['--disable-web-security', '--ignore-certificate-errors', '--no-sandbox'],
    });

    let context: BrowserContext | null = null;

    try {
      context = await createContext(browser);
      const testInfo = await getTestDraft(context);
      const draftPk = testInfo.pk;
      const tournamentPk = testInfo.game.tournament_pk;
      const gamePk = testInfo.game.pk;
      const matchUrl = `${BASE_URL}/tournament/${tournamentPk}/bracket/match/${gamePk}`;

      await context.request.post(`${API_URL}/tests/herodraft/${draftPk}/reset/`);

      const { page, draftPage } = await setupSpectator(context, matchUrl);

      // Verify initial connection is working
      await draftPage.assertConnected();

      // Track new WebSocket connections (reconnection)
      let reconnectedWs: PWWebSocket | null = null;
      page.on('websocket', (newWs) => {
        if (newWs.url().includes('/api/herodraft/')) {
          reconnectedWs = newWs;
          console.log('New WebSocket connection created (reconnection)');
        }
      });

      // Force-close the raw WebSocket to simulate a network-level kill.
      // This mimics what happens when Cloudflare/Nginx silently drops the connection,
      // or what the stale detector does when it calls ws.close(4001).
      // The close is NOT through the manager's disconnect(), so intentionalClose stays false,
      // triggering scheduleReconnect in the onclose handler.
      console.log('Force-closing WebSocket to simulate network kill...');
      await page.evaluate(() => {
        const instances = (window as any).__wsInstances || [];
        for (const ws of instances) {
          if (
            ws.url.includes('/api/herodraft/') &&
            ws.readyState === WebSocket.OPEN
          ) {
            ws.close(4001, 'Simulated stale connection');
          }
        }
      });

      // Reconnecting indicator should appear
      await page
        .locator('[data-testid="herodraft-reconnecting"]')
        .waitFor({ state: 'visible', timeout: 5000 });
      console.log('Reconnecting indicator visible');

      // Wait for reconnection to complete
      await draftPage.waitForConnection(15000);
      console.log('Reconnected successfully');

      // Verify a new WebSocket was created
      expect(reconnectedWs).not.toBeNull();

      // Verify the draft UI is still functional after reconnection
      await draftPage.assertConnected();
      await draftPage.waitForModal();

      console.log('Client reconnected after simulated network kill');
    } finally {
      if (context) await context.close().catch(() => {});
      await browser.close();
    }
  });
});
