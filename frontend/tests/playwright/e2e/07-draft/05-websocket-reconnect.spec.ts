/**
 * WebSocket Reconnection Tests (Category 4 - Highest Priority)
 *
 * Tests that the team draft WebSocket automatically reconnects after
 * server-initiated disconnects, replays initial_events, and restores
 * draft state. Uses the kill-ws test endpoint to simulate WS drops.
 *
 * Uses serial execution because tests share WebSocket state and the
 * reconnect flow is order-dependent.
 *
 * Tournament: 'draft_captain_turn' (snake draft, in-progress, 0 picks)
 */

import {
  test,
  expect,
  getTournamentByKey,
  killDraftWebSocket,
  TournamentPage,
  DraftWebSocketHelper,
} from '../../fixtures';

// Extended tournament response that includes the draft field
interface TournamentWithDraft {
  pk: number;
  name: string;
  draft?: { pk: number };
  teams: Array<{
    pk: number;
    name: string;
    captain: number;
    draft_order: number;
  }>;
}

test.describe.serial('WebSocket Reconnection', () => {
  let tournamentPk: number;
  let draftPk: number;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });

    // Get tournament data (draft already in-progress from populate)
    const result = await getTournamentByKey(context, 'draft_captain_turn');
    if (!result) {
      throw new Error('Could not find draft_captain_turn tournament');
    }

    const tournament = result as unknown as TournamentWithDraft;
    tournamentPk = tournament.pk;
    draftPk = tournament.draft?.pk ?? 0;

    if (!draftPk) {
      throw new Error(
        `No draft PK in tournament response (keys: ${Object.keys(tournament).join(', ')})`
      );
    }

    console.log(`Tournament: pk=${tournamentPk}, Draft: pk=${draftPk}`);
    await context.close();
  });

  /**
   * Helper: navigate to draft modal, wait for WS connection and initial_events.
   */
  async function openDraftWithWS(
    page: Parameters<Parameters<typeof test>[2]>[0]['page'],
    wsHelper: DraftWebSocketHelper
  ): Promise<void> {
    const tournamentPage = new TournamentPage(page);
    await tournamentPage.goto(tournamentPk);
    await tournamentPage.clickTeamsTab();
    await tournamentPage.clickStartDraft();
    await tournamentPage.waitForDraftModal();
    await wsHelper.waitForConnection();
    // Wait for initial_events to be received (WS open != message received)
    await wsHelper.waitForMessage('initial_events');
  }

  // =========================================================================
  // Core Reconnection
  // =========================================================================

  test('reconnects automatically after server kills WebSocket', async ({
    page,
    context,
    loginAdmin,
  }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    await openDraftWithWS(page, wsHelper);

    // Verify initial connection
    wsHelper.assertSingleConnection();
    const initialCount = wsHelper.connectionCount;

    // Server-side kill
    const killed = await killDraftWebSocket(context, draftPk);
    expect(killed).toBe(true);

    // Client should reconnect automatically
    await wsHelper.waitForReconnect();

    // Verify: more connections created (original + reconnect)
    expect(wsHelper.connectionCount).toBeGreaterThan(initialCount);
    // Exactly one active connection after reconnect
    expect(wsHelper.activeConnectionCount).toBe(1);
  });

  test('receives initial_events with draft_state after reconnect', async ({
    page,
    context,
    loginAdmin,
  }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    await openDraftWithWS(page, wsHelper);

    // First connection: should have initial_events
    const firstInitial = wsHelper.messagesOfType('initial_events');
    expect(firstInitial.length).toBe(1);
    expect(firstInitial[0].draft_state).toBeDefined();

    // Kill and reconnect
    await killDraftWebSocket(context, draftPk);
    await wsHelper.waitForReconnect();

    // Wait for the reconnected socket's initial_events
    await expect
      .poll(() => wsHelper.messagesOfType('initial_events').length, {
        message: 'Expected 2 initial_events messages (connect + reconnect)',
        timeout: 10000,
      })
      .toBeGreaterThanOrEqual(2);

    // Second initial_events should also have draft_state
    const allInitial = wsHelper.messagesOfType('initial_events');
    const reconnectMsg = allInitial[allInitial.length - 1];
    expect(reconnectMsg.draft_state).toBeDefined();
  });

  test('draft state is consistent after reconnect', async ({
    page,
    context,
    loginAdmin,
  }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    await openDraftWithWS(page, wsHelper);

    // Capture draft state from first connection
    const firstInitial = wsHelper.messagesOfType('initial_events')[0];
    const firstDraftState = firstInitial.draft_state as Record<string, unknown>;
    expect(firstDraftState).toBeDefined();

    // Kill and reconnect
    await killDraftWebSocket(context, draftPk);
    await wsHelper.waitForReconnect();

    // Wait for reconnect initial_events
    await expect
      .poll(() => wsHelper.messagesOfType('initial_events').length, {
        timeout: 10000,
      })
      .toBeGreaterThanOrEqual(2);

    // Compare key fields of draft state
    const allInitial = wsHelper.messagesOfType('initial_events');
    const reconnectDraftState = allInitial[allInitial.length - 1]
      .draft_state as Record<string, unknown>;

    expect(reconnectDraftState).toBeDefined();

    // Same draft PK
    expect(reconnectDraftState.pk).toBe(firstDraftState.pk);
    // Same draft style
    expect(reconnectDraftState.draft_style).toBe(firstDraftState.draft_style);
    // Same number of draft rounds
    const firstRounds = firstDraftState.draft_rounds as unknown[];
    const reconnectRounds = reconnectDraftState.draft_rounds as unknown[];
    expect(reconnectRounds?.length).toBe(firstRounds?.length);
  });

  test('no toasts appear from initial_events on reconnect', async ({
    page,
    context,
    loginAdmin,
  }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    await openDraftWithWS(page, wsHelper);

    // Dismiss any existing toasts
    await page.locator('[data-sonner-toast]').all().then((toasts) =>
      Promise.all(toasts.map((t) => t.click().catch(() => {})))
    );
    await page.waitForTimeout(500);

    // Kill and reconnect
    await killDraftWebSocket(context, draftPk);
    await wsHelper.waitForReconnect();

    // Wait for initial_events to be processed
    await expect
      .poll(() => wsHelper.messagesOfType('initial_events').length, {
        timeout: 10000,
      })
      .toBeGreaterThanOrEqual(2);

    // No toasts should appear from replayed initial_events
    // (only live draft_event messages trigger toasts)
    await wsHelper.assertNoToast(2000);
  });

  // =========================================================================
  // Multiple disconnects
  // =========================================================================

  test('survives multiple consecutive disconnects', async ({
    page,
    context,
    loginAdmin,
  }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    await openDraftWithWS(page, wsHelper);

    // Kill and reconnect 3 times
    for (let i = 0; i < 3; i++) {
      const countBefore = wsHelper.connectionCount;
      const msgCountBefore = wsHelper.messagesOfType('initial_events').length;

      await killDraftWebSocket(context, draftPk);
      await wsHelper.waitForReconnect(20000);
      expect(wsHelper.connectionCount).toBeGreaterThan(countBefore);

      // Wait for the reconnected socket's initial_events before killing again
      await expect
        .poll(() => wsHelper.messagesOfType('initial_events').length, {
          timeout: 10000,
        })
        .toBeGreaterThan(msgCountBefore);
    }

    // After 3 reconnects, should still have exactly 1 active connection
    expect(wsHelper.activeConnectionCount).toBe(1);

    // And the connection should still deliver initial_events
    const initialMessages = wsHelper.messagesOfType('initial_events');
    // At least 4: 1 initial + 3 reconnects
    expect(initialMessages.length).toBeGreaterThanOrEqual(4);
  });

  // =========================================================================
  // Close event tracking
  // =========================================================================

  test('close events recorded for each disconnect', async ({
    page,
    context,
    loginAdmin,
  }) => {
    await loginAdmin();

    const wsHelper = new DraftWebSocketHelper(page);
    await openDraftWithWS(page, wsHelper);

    expect(wsHelper.closeCount).toBe(0);

    // Kill connection
    await killDraftWebSocket(context, draftPk);
    await wsHelper.waitForReconnect();

    // Should have recorded at least one close event
    expect(wsHelper.closeCount).toBeGreaterThanOrEqual(1);
  });
});
