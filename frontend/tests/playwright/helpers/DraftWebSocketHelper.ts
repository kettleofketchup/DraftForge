import { type Page, type WebSocket, type Locator, expect } from '@playwright/test';

/**
 * WebSocket monitoring helper for team draft E2E tests.
 *
 * Complements TournamentPage (which handles navigation, tabs, draft modal).
 * This helper focuses on WS connection tracking, message interception,
 * and toast assertions.
 *
 * Usage:
 *   const wsHelper = new DraftWebSocketHelper(page);
 *   // ... open draft modal ...
 *   await wsHelper.waitForConnection();
 *   expect(wsHelper.connectionCount).toBe(1);
 */
export class DraftWebSocketHelper {
  private _connections: WebSocket[] = [];
  private _messages: Array<{ type: string; [key: string]: unknown }> = [];
  private _closeEvents: Array<{ ws: WebSocket; code: number }> = [];

  constructor(private page: Page) {
    this._registerListener();
  }

  private _registerListener(): void {
    this.page.on('websocket', (ws) => {
      if (!ws.url().includes('/api/draft/')) return;

      this._connections.push(ws);

      ws.on('framereceived', (frame) => {
        try {
          const data = JSON.parse(frame.payload as string);
          this._messages.push(data);
        } catch {
          // Ignore non-JSON frames
        }
      });

      ws.on('close', () => {
        this._closeEvents.push({ ws, code: 0 });
      });
    });
  }

  // ===========================================================================
  // Connection monitoring
  // ===========================================================================

  /** Total number of WS connections opened (including closed ones). */
  get connectionCount(): number {
    return this._connections.length;
  }

  /** Currently open connections. */
  get activeConnections(): WebSocket[] {
    return this._connections.filter((ws) => !ws.isClosed());
  }

  /** Number of currently open connections. */
  get activeConnectionCount(): number {
    return this.activeConnections.length;
  }

  /** All received WS messages. */
  get messages(): Array<{ type: string; [key: string]: unknown }> {
    return [...this._messages];
  }

  /** Messages of a specific type. */
  messagesOfType(type: string): Array<{ type: string; [key: string]: unknown }> {
    return this._messages.filter((m) => m.type === type);
  }

  /** Number of close events recorded. */
  get closeCount(): number {
    return this._closeEvents.length;
  }

  // ===========================================================================
  // Wait methods
  // ===========================================================================

  /**
   * Wait for the first WS connection to be established.
   * Resolves immediately if a connection already exists.
   */
  async waitForConnection(timeout = 10000): Promise<void> {
    if (this.activeConnectionCount > 0) return;

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`No WS connection within ${timeout}ms`)),
        timeout
      );

      const handler = (ws: WebSocket) => {
        if (ws.url().includes('/api/draft/')) {
          clearTimeout(timer);
          this.page.removeListener('websocket', handler);
          resolve();
        }
      };

      this.page.on('websocket', handler);
    });
  }

  /**
   * Wait for all active connections to close.
   *
   * Default 20s tolerates accumulated load late in the full suite; in
   * isolation a clean disconnect completes in well under 5s. The flake
   * we're guarding against is a long-tail timing when the test runner
   * has been going for >15 minutes and React's useEffect cleanup races
   * other queued work — not a regression in the disconnect logic.
   */
  async waitForDisconnect(timeout = 20000): Promise<void> {
    if (this.activeConnectionCount === 0) return;

    const active = this.activeConnections;
    await Promise.all(
      active.map(
        (ws) =>
          new Promise<void>((resolve, reject) => {
            if (ws.isClosed()) {
              resolve();
              return;
            }
            const timer = setTimeout(
              () => reject(new Error(`WS did not close within ${timeout}ms`)),
              timeout
            );
            ws.on('close', () => {
              clearTimeout(timer);
              resolve();
            });
          })
      )
    );
  }

  /**
   * Wait for a reconnection: a close event followed by a new open.
   * Returns when the new connection's initial_events message is received.
   */
  async waitForReconnect(timeout = 15000): Promise<void> {
    const countBefore = this.connectionCount;

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(
        () =>
          reject(
            new Error(
              `No reconnection within ${timeout}ms (connections: ${this.connectionCount}, before: ${countBefore})`
            )
          ),
        timeout
      );

      const checkReconnect = () => {
        // New connection opened after the ones we had before
        if (this.connectionCount > countBefore && this.activeConnectionCount > 0) {
          clearTimeout(timer);
          resolve();
        }
      };

      // Check on each new WS connection
      const handler = (ws: WebSocket) => {
        if (ws.url().includes('/api/draft/')) {
          checkReconnect();
        }
      };

      this.page.on('websocket', handler);

      // Also resolve if already reconnected
      checkReconnect();
    });
  }

  /**
   * Wait for a specific message type to arrive via WS.
   */
  async waitForMessage(
    type: string,
    timeout = 10000
  ): Promise<{ type: string; [key: string]: unknown }> {
    // Check if already received
    const existing = this._messages.find((m) => m.type === type);
    if (existing) return existing;

    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`No WS message of type "${type}" within ${timeout}ms`)),
        timeout
      );

      // Poll messages array (framereceived events are async)
      const interval = setInterval(() => {
        const found = this._messages.find((m) => m.type === type);
        if (found) {
          clearTimeout(timer);
          clearInterval(interval);
          resolve(found);
        }
      }, 100);
    });
  }

  // ===========================================================================
  // Assertions
  // ===========================================================================

  /** Assert exactly one active WS connection. */
  assertSingleConnection(): void {
    expect(
      this.activeConnectionCount,
      `Expected 1 active WS connection, got ${this.activeConnectionCount}`
    ).toBe(1);
  }

  /** Assert no active WS connections. */
  assertNoConnections(): void {
    expect(
      this.activeConnectionCount,
      `Expected 0 active WS connections, got ${this.activeConnectionCount}`
    ).toBe(0);
  }

  // ===========================================================================
  // Toast helpers (Sonner)
  // ===========================================================================

  /**
   * Wait for a toast notification containing the given text.
   */
  async waitForToast(text: string | RegExp, timeout = 5000): Promise<Locator> {
    const toast = this.page.locator('[data-sonner-toast]').filter({
      hasText: text,
    });
    await expect(toast.first()).toBeVisible({ timeout });
    return toast.first();
  }

  /**
   * Assert no toast is visible after waiting for a duration.
   * Useful for verifying initial_events don't trigger toasts.
   */
  async assertNoToast(waitMs = 2000): Promise<void> {
    // Wait a bit to give any toasts time to appear
    await this.page.waitForTimeout(waitMs);
    const toasts = this.page.locator('[data-sonner-toast]');
    const count = await toasts.count();
    expect(count, `Expected no toasts, found ${count}`).toBe(0);
  }

  // ===========================================================================
  // Reset
  // ===========================================================================

  /** Clear all tracked state. Useful between test steps. */
  reset(): void {
    this._connections = [];
    this._messages = [];
    this._closeEvents = [];
  }
}
