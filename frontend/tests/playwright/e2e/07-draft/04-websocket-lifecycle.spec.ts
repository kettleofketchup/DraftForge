/**
 * WebSocket Connection Lifecycle Tests (Category 1)
 *
 * Tests that team draft WebSocket connections are properly managed:
 * - Connect on modal open
 * - Disconnect on modal close
 * - No duplicate connections from StrictMode
 * - Clean disconnect on page navigation
 * - Fresh connection on modal reopen
 *
 * Tournament: 'draft_captain_turn' (snake draft, in-progress)
 */

import type { Page } from '@playwright/test';
import { BASE_URL } from '../../fixtures/base-url';
import {
  test,
  expect,
  getTournamentByKey,
  TournamentPage,
  DraftWebSocketHelper,
} from '../../fixtures';

// Client-side route change to "/": the app must close the socket on unmount. A page.goto()
// unloads the document instead, which closes sockets without Playwright emitting 'close'.
async function navigateAwayInApp(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.history.pushState(null, '', '/');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(`${BASE_URL}/`);
}

interface TournamentWithDraft {
  pk: number;
  draft?: { pk: number };
}

test.describe('WebSocket Connection Lifecycle', () => {
  let tournamentPk: number;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const result = await getTournamentByKey(context, 'draft_captain_turn');
    if (!result) throw new Error('Could not find draft_captain_turn tournament');
    const tournament = result as unknown as TournamentWithDraft;
    tournamentPk = tournament.pk;
    await context.close();
  });

  // Force navigation off the draft route so any lingering WS from the
  // previous test is closed before the next one starts measuring. Playwright
  // closes the page between tests on its own, but the close handler
  // back-pressures on the server's group_discard + redis cleanup, which
  // gets slow late in the suite. Navigating away first lets useEffect
  // cleanup run synchronously while the page is still alive.
  test.afterEach(async ({ page }) => {
    if (!page.isClosed()) {
      await page.goto('about:blank').catch(() => {});
    }
  });

  test('@cicd connects on modal open', async ({ page, loginAdmin }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    const tournamentPage = new TournamentPage(page);

    await tournamentPage.goto(tournamentPk);
    await tournamentPage.clickTeamsTab();
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();

    await wsHelper.waitForConnection();
    wsHelper.assertSingleConnection();
  });

  test('@cicd disconnects on modal close', async ({ page, loginAdmin }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    const tournamentPage = new TournamentPage(page);

    await tournamentPage.goto(tournamentPk);
    await tournamentPage.clickTeamsTab();
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();
    await wsHelper.waitForConnection();

    // Close the modal
    await page.keyboard.press('Escape');

    // WS should disconnect
    await wsHelper.waitForDisconnect();
    wsHelper.assertNoConnections();
  });

  test('@cicd no duplicate connections from StrictMode', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    const tournamentPage = new TournamentPage(page);

    await tournamentPage.goto(tournamentPk);
    await tournamentPage.clickTeamsTab();
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();
    await wsHelper.waitForConnection();

    // Wait a bit for any StrictMode double-mount effects
    await page.waitForTimeout(1000);

    // Should have exactly 1 active connection (StrictMode may create 2 then close 1)
    expect(wsHelper.activeConnectionCount).toBe(1);
  });

  test('@cicd clean disconnect on page navigation', async ({
    page,
    loginAdmin,
  }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    const tournamentPage = new TournamentPage(page);

    await tournamentPage.goto(tournamentPk);
    await tournamentPage.clickTeamsTab();
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();
    await wsHelper.waitForConnection();

    await navigateAwayInApp(page);

    // All WS connections should be closed
    await wsHelper.waitForDisconnect();
    wsHelper.assertNoConnections();
  });

  test('@cicd fresh connection on revisit', async ({ page, loginAdmin }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    const tournamentPage = new TournamentPage(page);

    // Open modal - first connection
    await tournamentPage.goto(tournamentPk);
    await tournamentPage.clickTeamsTab();
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();
    await wsHelper.waitForConnection();
    expect(wsHelper.connectionCount).toBe(1);

    await navigateAwayInApp(page);
    await wsHelper.waitForDisconnect();

    // Navigate back and reopen
    await tournamentPage.goto(tournamentPk);
    await tournamentPage.clickTeamsTab();
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();

    // Wait for new connection
    await expect
      .poll(() => wsHelper.connectionCount, { timeout: 10000 })
      .toBeGreaterThanOrEqual(2);

    expect(wsHelper.activeConnectionCount).toBe(1);
  });
});
