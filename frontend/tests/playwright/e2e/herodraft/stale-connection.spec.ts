import { test, expect, chromium } from '@playwright/test';
import type { BrowserContext, Page, WebSocket as PWWebSocket, WebSocketRoute } from '@playwright/test';
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
    return browser.newContext({ ignoreHTTPSErrors: true });
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

      // Inline the spectator setup so we can install the WebSocket route
      // BEFORE navigating. page.routeWebSocket only intercepts WebSockets
      // opened *after* the route is installed, so it has to be in place
      // before page.goto triggers the app's connect.
      //
      // The route handler proxies to the real server (connectToServer),
      // so app behavior is identical to a direct connection. The handle
      // we capture is what we'll use later to force-close mid-test.
      await loginUser(context);
      const page = await context.newPage();

      const wsRoutes: WebSocketRoute[] = [];
      await page.routeWebSocket('**/api/herodraft/**', (ws) => {
        ws.connectToServer();
        wsRoutes.push(ws);
      });

      await page.goto(matchUrl);
      await waitForHydration(page);
      await page.getByTestId('view-draft-btn').click();

      const draftPage = new HeroDraftPage(page);
      await draftPage.waitForModal();
      await draftPage.waitForConnection();
      await draftPage.assertConnected();

      // Initial connection should now be in wsRoutes[0].
      expect(wsRoutes.length).toBeGreaterThanOrEqual(1);
      const initialRouteCount = wsRoutes.length;
      const initialRoute = wsRoutes[0];

      // Watch wsRoutes for a NEW entry (the reconnection). routeWebSocket
      // pushes a fresh handle for each new WebSocket the page opens, so a
      // length increase = the app constructed a reconnection WebSocket.
      const reconnectStart = Date.now();
      const waitForReconnectRoute = (async () => {
        while (Date.now() - reconnectStart < 15000) {
          if (wsRoutes.length > initialRouteCount) {
            return wsRoutes[initialRouteCount];
          }
          await new Promise((r) => setTimeout(r, 100));
        }
        throw new Error(
          `Reconnection WebSocket never opened within 15s — wsRoutes.length stayed at ${initialRouteCount}. ` +
            `App's WebSocketManager.scheduleReconnect either did not fire or did not reach new WebSocket(...). ` +
            `Likely causes: intentionalClose got set true, attempt count exceeded, or the close event handler ` +
            `did not run.`,
        );
      })();

      // Force-close the original WebSocket via the Playwright route handle.
      // Closing one side closes the other (per Playwright docs), so the page
      // sees a normal close event with code 4001 — same observable signal as
      // what Cloudflare/nginx would send during a stale-connection kill.
      // No app code changes, no test-only globals on window.
      console.log('Force-closing WebSocket via routeWebSocket handle...');
      await initialRoute.close({ code: 4001, reason: 'Simulated stale connection' });

      const reconnectedRoute = await waitForReconnectRoute;
      expect(reconnectedRoute).toBeDefined();
      console.log(`Reconnection WebSocket opened: ${reconnectedRoute.url()}`);

      // Wait for the app to mark the new connection as established.
      await draftPage.waitForConnection(15000);
      await draftPage.assertConnected();
      await draftPage.waitForModal();

      console.log('Client reconnected after simulated network kill');
    } finally {
      if (context) await context.close().catch(() => {});
      await browser.close();
    }
  });
});
