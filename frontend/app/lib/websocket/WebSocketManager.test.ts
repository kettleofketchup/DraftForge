/**
 * WebSocketManager stale connection detection tests.
 *
 * Tests the client-side stale detection logic: when no messages arrive
 * within staleTimeoutMs, the connection is closed (code 4001) and
 * reconnection is scheduled automatically.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Mock Sentry before importing WebSocketManager
vi.mock('~/lib/sentry', () => ({
  Sentry: {
    captureMessage: vi.fn(),
    captureException: vi.fn(),
  },
}));

// Mock logger
vi.mock('~/lib/logger', () => ({
  getLogger: () => ({
    debug: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  }),
}));

// --- Mock WebSocket ---

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  static instances: MockWebSocket[] = [];

  url: string;
  readyState: number;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  send = vi.fn();
  close = vi.fn((code?: number, reason?: string) => {
    if (this.readyState === MockWebSocket.CLOSED) return;
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code: code ?? 1000, reason: reason ?? '' } as unknown as CloseEvent);
  });

  constructor(url: string) {
    this.url = url;
    this.readyState = MockWebSocket.CONNECTING;
    MockWebSocket.instances.push(this);
  }

  /** Test helper: simulate server accepting connection */
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({} as Event);
  }

  /** Test helper: simulate receiving a message */
  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

vi.stubGlobal('WebSocket', MockWebSocket);
// Provide window global so getWebSocketManager() doesn't throw SSR guard
vi.stubGlobal('window', globalThis);

import { Sentry } from '~/lib/sentry';
import { getWebSocketManager } from './WebSocketManager';

// ─────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 50; // CONNECT_DEBOUNCE_MS in WebSocketManager
const STALE_CHECK_MS = 1000; // STALE_CHECK_INTERVAL_MS in WebSocketManager

/** Connect to a URL and simulate the WebSocket opening. */
function connectAndOpen(
  url: string,
  options: {
    staleTimeoutMs?: number;
    onStaleDetected?: (url: string, staleDurationMs: number) => void;
    onStateChange?: (state: unknown) => void;
    onDisconnected?: (url: string, reason: unknown) => void;
    onReconnecting?: (url: string, attempt: number, backoffMs: number) => void;
  } = {},
) {
  const manager = getWebSocketManager();
  manager.connect(url, {
    staleTimeoutMs: options.staleTimeoutMs,
    onStateChange: options.onStateChange,
    telemetry: {
      onStaleDetected: options.onStaleDetected,
      onDisconnected: options.onDisconnected,
      onReconnecting: options.onReconnecting,
    },
  });

  // Advance past connect debounce
  vi.advanceTimersByTime(DEBOUNCE_MS);

  const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
  ws.simulateOpen();
  return ws;
}

// ─────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────

describe('WebSocketManager stale connection detection', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.mocked(Sentry.captureMessage).mockClear();
  });

  afterEach(() => {
    getWebSocketManager().disconnectAll();
    vi.useRealTimers();
  });

  it('closes connection with code 4001 when no messages arrive within staleTimeoutMs', () => {
    const ws = connectAndOpen('ws://test/api/herodraft/1/', {
      staleTimeoutMs: 3000,
    });

    // Advance time past the stale timeout
    // Stale check runs every 1s. After 4s, staleDuration = 4000 > 3000.
    vi.advanceTimersByTime(4000);

    expect(ws.close).toHaveBeenCalledWith(4001, 'Stale connection');
  });

  it('does not close connection while messages keep arriving', () => {
    const ws = connectAndOpen('ws://test/api/herodraft/1/', {
      staleTimeoutMs: 3000,
    });

    // Send a message every 2s (within the 3s timeout)
    vi.advanceTimersByTime(2000);
    ws.simulateMessage({ type: 'ping' });

    vi.advanceTimersByTime(2000);
    ws.simulateMessage({ type: 'ping' });

    vi.advanceTimersByTime(2000);
    ws.simulateMessage({ type: 'herodraft_tick', current_round: 1 });

    // Connection should still be open — never went 3s without a message
    expect(ws.close).not.toHaveBeenCalled();
  });

  it('resets stale timer on any message type, not just ping', () => {
    const ws = connectAndOpen('ws://test/api/herodraft/1/', {
      staleTimeoutMs: 3000,
    });

    // Wait 2.5s (close to timeout), then send a non-ping message
    vi.advanceTimersByTime(2500);
    ws.simulateMessage({ type: 'herodraft_event', event_type: 'hero_picked' });

    // Wait another 2.5s — would be 5s total, but timer was reset at 2.5s
    vi.advanceTimersByTime(2500);
    expect(ws.close).not.toHaveBeenCalled();

    // Wait 1 more second — now 3.5s since last message
    vi.advanceTimersByTime(1000);
    expect(ws.close).toHaveBeenCalledWith(4001, 'Stale connection');
  });

  it('fires onStaleDetected telemetry callback with URL and duration', () => {
    const onStaleDetected = vi.fn();
    connectAndOpen('ws://test/api/herodraft/1/', {
      staleTimeoutMs: 3000,
      onStaleDetected,
    });

    vi.advanceTimersByTime(4000);

    expect(onStaleDetected).toHaveBeenCalledOnce();
    expect(onStaleDetected).toHaveBeenCalledWith(
      'ws://test/api/herodraft/1/',
      expect.any(Number),
    );
    // Duration should be > staleTimeoutMs
    const staleDuration = onStaleDetected.mock.calls[0][1];
    expect(staleDuration).toBeGreaterThan(3000);
  });

  it('reports stale connection to Sentry', () => {
    connectAndOpen('ws://test/api/herodraft/1/', {
      staleTimeoutMs: 3000,
    });

    vi.advanceTimersByTime(4000);

    expect(Sentry.captureMessage).toHaveBeenCalledWith(
      'WebSocket stale connection detected: ws://test/api/herodraft/1/',
      'warning',
    );
  });

  it('triggers reconnection after stale close', () => {
    const onReconnecting = vi.fn();
    connectAndOpen('ws://test/api/herodraft/1/', {
      staleTimeoutMs: 3000,
      onReconnecting,
    });

    const initialWsCount = MockWebSocket.instances.length;

    // Trigger stale detection
    vi.advanceTimersByTime(4000);

    // Advance past the reconnect backoff (1s base delay for attempt 1)
    vi.advanceTimersByTime(1000);

    // A new WebSocket should have been created for reconnection
    expect(MockWebSocket.instances.length).toBe(initialWsCount + 1);

    const newWs = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    expect(newWs.url).toBe('ws://test/api/herodraft/1/');
    expect(newWs).not.toBe(MockWebSocket.instances[0]);
  });

  it('does not check connections without staleTimeoutMs', () => {
    const ws = connectAndOpen('ws://test/api/herodraft/1/');

    // Advance well past any reasonable timeout
    vi.advanceTimersByTime(60000);

    expect(ws.close).not.toHaveBeenCalled();
  });

  it('only closes stale connections, not healthy ones', () => {
    const staleWs = connectAndOpen('ws://test/api/herodraft/1/', {
      staleTimeoutMs: 3000,
    });
    const healthyWs = connectAndOpen('ws://test/api/herodraft/2/', {
      staleTimeoutMs: 3000,
    });

    // Send messages to the healthy connection but not the stale one
    vi.advanceTimersByTime(2000);
    healthyWs.simulateMessage({ type: 'ping' });

    vi.advanceTimersByTime(2000);
    healthyWs.simulateMessage({ type: 'ping' });

    // Stale connection should be closed, healthy one should not
    expect(staleWs.close).toHaveBeenCalledWith(4001, 'Stale connection');
    expect(healthyWs.close).not.toHaveBeenCalled();
  });

  it('stops stale checks when all stale-enabled connections disconnect', () => {
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval');

    connectAndOpen('ws://test/api/herodraft/1/', {
      staleTimeoutMs: 3000,
    });

    const manager = getWebSocketManager();
    manager.disconnect('ws://test/api/herodraft/1/', 'test cleanup');

    // clearInterval should have been called to stop the stale check loop
    expect(clearIntervalSpy).toHaveBeenCalled();
    clearIntervalSpy.mockRestore();
  });

  it('reconnected connection resumes stale detection', () => {
    connectAndOpen('ws://test/api/herodraft/1/', {
      staleTimeoutMs: 3000,
    });

    // First stale detection
    vi.advanceTimersByTime(4000);
    const firstWs = MockWebSocket.instances[0];
    expect(firstWs.close).toHaveBeenCalledWith(4001, 'Stale connection');

    // Advance past reconnect backoff
    vi.advanceTimersByTime(1000);

    // New WebSocket created — simulate it connecting
    const secondWs = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    secondWs.simulateOpen();

    // The reconnected connection should also be subject to stale detection
    // Advance past stale timeout again without sending messages
    vi.advanceTimersByTime(4000);
    expect(secondWs.close).toHaveBeenCalledWith(4001, 'Stale connection');
  });

  it('does not fire stale detection for connections in reconnecting state', () => {
    const ws = connectAndOpen('ws://test/api/herodraft/1/', {
      staleTimeoutMs: 3000,
    });

    // Trigger stale detection (closes connection, enters reconnecting state)
    vi.advanceTimersByTime(4000);
    expect(ws.close).toHaveBeenCalledOnce();

    // While in reconnecting state, stale check should not trigger again
    // (status is 'reconnecting', not 'connected')
    vi.advanceTimersByTime(4000);

    // close should still have been called only once on the original WS
    expect(ws.close).toHaveBeenCalledOnce();
  });
});
