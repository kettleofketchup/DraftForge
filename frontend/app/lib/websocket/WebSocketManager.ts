/**
 * WebSocketManager - Singleton for managing WebSocket connections
 *
 * Handles connection lifecycle, reconnection with exponential backoff,
 * message routing to subscribers, and send queue management.
 */

import { getLogger } from '~/lib/logger';
import type {
  ConnectionOptions,
  ConnectionState,
  ConnectionStatus,
  DisconnectReason,
  MessageHandler,
  Unsubscribe,
  WebSocketConnection,
} from './types';

const log = getLogger('WebSocketManager');

// Reconnection defaults
const DEFAULT_MAX_ATTEMPTS = 10;
const DEFAULT_BASE_DELAY_MS = 1000;
const DEFAULT_MAX_DELAY_MS = 30000;

// StrictMode debounce delay
const CONNECT_DEBOUNCE_MS = 50;

// Send queue limits
const MAX_QUEUE_SIZE = 100;

class WebSocketManager {
  private connections = new Map<string, WebSocketConnection>();
  private globalConnectionId = 0;

  /**
   * Connect to a WebSocket URL.
   * Returns a connectionId for subsequent operations.
   */
  connect(url: string, options: ConnectionOptions = {}): string {
    // Check for existing connection
    const existing = this.connections.get(url);
    if (existing) {
      const status = existing.state.status;
      if (status === 'connected' || status === 'connecting') {
        log.debug(`Already ${status} to ${url}, reusing connection`);
        // Update options if provided
        existing.options = { ...existing.options, ...options };
        return url;
      }
    }

    // Create new connection entry
    const connectionId = ++this.globalConnectionId;
    const connection: WebSocketConnection = {
      url,
      ws: null,
      connectionId,
      state: {
        status: 'disconnected',
        error: null,
        reconnectAttempts: 0,
        connectedAt: null,
        lastMessageAt: null,
      },
      options,
      subscribers: new Set(),
      sendQueue: [],
      reconnectTimeout: null,
      connectTimeout: null,
      intentionalClose: false,
      connectStartTime: null,
    };

    this.connections.set(url, connection);

    // Debounce connection for React StrictMode
    connection.connectTimeout = setTimeout(() => {
      this.doConnect(url);
    }, CONNECT_DEBOUNCE_MS);

    return url;
  }

  /**
   * Disconnect from a WebSocket.
   */
  disconnect(connectionId: string, reason = 'Disconnect requested'): void {
    const conn = this.connections.get(connectionId);
    if (!conn) {
      log.debug(`No connection found for ${connectionId}`);
      return;
    }

    log.debug(`Disconnecting from ${connectionId}: ${reason}`);
    conn.intentionalClose = true;

    // Clear pending timeouts
    if (conn.connectTimeout) {
      clearTimeout(conn.connectTimeout);
      conn.connectTimeout = null;
    }
    if (conn.reconnectTimeout) {
      clearTimeout(conn.reconnectTimeout);
      conn.reconnectTimeout = null;
    }

    // Close WebSocket
    if (conn.ws) {
      conn.ws.close(1000, reason);
      conn.ws = null;
    }

    // Update state
    this.updateState(conn, {
      status: 'disconnected',
      error: null,
      reconnectAttempts: 0,
    });

    // Emit telemetry
    conn.options.telemetry?.onDisconnected?.(conn.url, {
      type: 'intentional',
      reason,
    });

    // Remove connection entry
    this.connections.delete(connectionId);
  }

  /**
   * Disconnect all connections (used for HMR cleanup).
   */
  disconnectAll(): void {
    for (const url of this.connections.keys()) {
      this.disconnect(url, 'Manager cleanup');
    }
  }

  /**
   * Subscribe to messages from a connection.
   * Returns an unsubscribe function.
   */
  subscribe(connectionId: string, handler: MessageHandler): Unsubscribe {
    const conn = this.connections.get(connectionId);
    if (!conn) {
      log.warn(`Cannot subscribe: no connection for ${connectionId}`);
      return () => {};
    }

    const subscriber = { id: Symbol(), handler };
    conn.subscribers.add(subscriber);

    log.debug(`Subscriber added for ${connectionId}, total: ${conn.subscribers.size}`);

    return () => {
      conn.subscribers.delete(subscriber);
      log.debug(`Subscriber removed for ${connectionId}, remaining: ${conn.subscribers.size}`);

      // Auto-disconnect when no subscribers remain
      if (conn.subscribers.size === 0) {
        log.debug(`No subscribers left for ${connectionId}, auto-disconnecting`);
        this.disconnect(connectionId, 'No subscribers');
      }
    };
  }

  /**
   * Send a message through the WebSocket.
   * Returns false if the queue is full.
   */
  send(connectionId: string, message: unknown): boolean {
    const conn = this.connections.get(connectionId);
    if (!conn) {
      log.warn(`Cannot send: no connection for ${connectionId}`);
      return false;
    }

    if (conn.state.status === 'connected' && conn.ws?.readyState === WebSocket.OPEN) {
      // Send immediately
      conn.ws.send(JSON.stringify(message));
      return true;
    }

    // Queue for later
    if (conn.sendQueue.length >= MAX_QUEUE_SIZE) {
      log.warn(`Send queue full for ${connectionId}, dropping oldest message`);
      conn.sendQueue.shift();
    }
    conn.sendQueue.push(message);
    return conn.sendQueue.length < MAX_QUEUE_SIZE;
  }

  /**
   * Get the current connection state.
   */
  getState(connectionId: string): ConnectionState | null {
    return this.connections.get(connectionId)?.state ?? null;
  }

  // ─────────────────────────────────────────────────────────────────
  // Private methods
  // ─────────────────────────────────────────────────────────────────

  private doConnect(url: string): void {
    const conn = this.connections.get(url);
    if (!conn) return;

    // Don't reconnect if already connected/connecting
    if (conn.ws?.readyState === WebSocket.OPEN || conn.ws?.readyState === WebSocket.CONNECTING) {
      log.debug(`WebSocket already ${conn.ws.readyState === WebSocket.OPEN ? 'open' : 'connecting'}`);
      return;
    }

    const thisConnectionId = conn.connectionId;
    conn.connectStartTime = Date.now();
    conn.intentionalClose = false;

    // Update state
    const isReconnect = conn.state.reconnectAttempts > 0;
    this.updateState(conn, {
      status: isReconnect ? 'reconnecting' : 'connecting',
      error: null,
    });

    // Emit telemetry
    conn.options.telemetry?.onConnecting?.(url, conn.state.reconnectAttempts);

    log.debug(`Connecting to ${url} (attempt ${conn.state.reconnectAttempts + 1})`);

    const ws = new WebSocket(url);
    conn.ws = ws;

    ws.onopen = () => {
      // Ignore stale connections
      if (conn.connectionId !== thisConnectionId) {
        log.debug('Ignoring stale WebSocket open');
        ws.close(1000, 'Stale connection');
        return;
      }

      const durationMs = conn.connectStartTime ? Date.now() - conn.connectStartTime : 0;
      log.debug(`WebSocket connected to ${url} in ${durationMs}ms`);

      this.updateState(conn, {
        status: 'connected',
        error: null,
        reconnectAttempts: 0,
        connectedAt: Date.now(),
      });

      // Emit telemetry
      conn.options.telemetry?.onConnected?.(url, durationMs);

      // Flush send queue
      this.flushQueue(conn);
    };

    ws.onmessage = (event) => {
      // Ignore stale connections
      if (conn.connectionId !== thisConnectionId) {
        log.debug('Ignoring stale WebSocket message');
        return;
      }

      // Check connection is still valid
      if (conn.ws !== ws || ws.readyState !== WebSocket.OPEN) {
        return;
      }

      let message: unknown;
      try {
        message = JSON.parse(event.data);
      } catch (err) {
        log.error('Failed to parse WebSocket message:', err);
        conn.options.telemetry?.onMessageParseError?.(url, err as Error);
        return;
      }

      // Update last message time
      conn.state.lastMessageAt = Date.now();

      // Emit telemetry
      const msgType = typeof message === 'object' && message !== null && 'type' in message
        ? String((message as { type: unknown }).type)
        : 'unknown';
      conn.options.telemetry?.onMessageReceived?.(url, msgType, event.data.length);

      // Route to subscribers
      for (const sub of conn.subscribers) {
        try {
          sub.handler(message);
        } catch (err) {
          log.error('Subscriber handler error:', err);
        }
      }
    };

    ws.onclose = (event) => {
      // Ignore stale connections
      if (conn.connectionId !== thisConnectionId) {
        log.debug('Ignoring stale WebSocket close');
        return;
      }

      log.debug(`WebSocket closed: ${event.code} ${event.reason}`);

      const wasIntentional = conn.intentionalClose;
      conn.intentionalClose = false;
      conn.ws = null;

      if (wasIntentional) {
        // Intentional close - already handled in disconnect()
        return;
      }

      // Emit telemetry
      conn.options.telemetry?.onDisconnected?.(url, {
        type: 'server_closed',
        code: event.code,
        reason: event.reason,
      });

      // Attempt reconnect
      this.scheduleReconnect(conn);
    };

    ws.onerror = (event) => {
      // Ignore stale connections
      if (conn.connectionId !== thisConnectionId) {
        log.debug('Ignoring stale WebSocket error');
        return;
      }

      log.error('WebSocket error:', event);
      this.updateState(conn, { error: 'Connection error' });

      // Emit telemetry
      conn.options.telemetry?.onDisconnected?.(url, {
        type: 'error',
        message: 'Connection error',
      });
    };
  }

  private scheduleReconnect(conn: WebSocketConnection): void {
    const config = conn.options.reconnect ?? {};
    const maxAttempts = config.maxAttempts ?? DEFAULT_MAX_ATTEMPTS;
    const baseDelay = config.baseDelayMs ?? DEFAULT_BASE_DELAY_MS;
    const maxDelay = config.maxDelayMs ?? DEFAULT_MAX_DELAY_MS;

    const attempts = conn.state.reconnectAttempts + 1;

    if (attempts > maxAttempts) {
      log.error(`Max reconnect attempts (${maxAttempts}) exceeded for ${conn.url}`);
      this.updateState(conn, {
        status: 'disconnected',
        error: `Connection lost. Max reconnection attempts exceeded.`,
      });
      conn.options.telemetry?.onDisconnected?.(conn.url, { type: 'max_retries_exceeded' });
      return;
    }

    // Exponential backoff: baseDelay * 2^(attempt-1), capped at maxDelay
    const delay = Math.min(baseDelay * Math.pow(2, attempts - 1), maxDelay);

    log.debug(`Scheduling reconnect attempt ${attempts}/${maxAttempts} in ${delay}ms`);

    this.updateState(conn, {
      status: 'reconnecting',
      error: `Connection lost. Reconnecting in ${Math.round(delay / 1000)}s...`,
      reconnectAttempts: attempts,
    });

    // Emit telemetry
    conn.options.telemetry?.onReconnecting?.(conn.url, attempts, delay);

    conn.reconnectTimeout = setTimeout(() => {
      conn.reconnectTimeout = null;
      this.doConnect(conn.url);
    }, delay);
  }

  private flushQueue(conn: WebSocketConnection): void {
    if (conn.sendQueue.length === 0) return;
    if (!conn.ws || conn.ws.readyState !== WebSocket.OPEN) return;

    log.debug(`Flushing ${conn.sendQueue.length} queued messages for ${conn.url}`);

    const messages = [...conn.sendQueue];
    conn.sendQueue = [];

    for (const msg of messages) {
      conn.ws.send(JSON.stringify(msg));
    }
  }

  private updateState(conn: WebSocketConnection, updates: Partial<ConnectionState>): void {
    conn.state = { ...conn.state, ...updates };
    conn.options.onStateChange?.(conn.state);
  }
}

// ─────────────────────────────────────────────────────────────────
// Singleton instance with SSR guard and HMR cleanup
// ─────────────────────────────────────────────────────────────────

let instance: WebSocketManager | null = null;

/**
 * Get the WebSocketManager singleton.
 * Throws if called server-side (SSR).
 */
export function getWebSocketManager(): WebSocketManager {
  if (typeof window === 'undefined') {
    throw new Error('WebSocketManager cannot be used server-side');
  }
  if (!instance) {
    instance = new WebSocketManager();
  }
  return instance;
}

// HMR cleanup for Vite
if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    log.debug('HMR: Cleaning up WebSocketManager');
    instance?.disconnectAll();
    instance = null;
  });
}
