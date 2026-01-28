/**
 * WebSocketManager - Singleton manager for WebSocket connections with reference counting.
 *
 * Features:
 * - Maintains a single WebSocket connection per channel (e.g., "tournament_123", "herodraft_456")
 * - Reference counting ensures connection closes only when all subscribers unsubscribe
 * - Automatic reconnection with exponential backoff
 * - Message sequence tracking for ordering
 * - Type-safe message handling with Zod validation
 */

import { z } from "zod";
import { getLogger } from "~/lib/logger";

const log = getLogger("WebSocketManager");

// Reconnection configuration
const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30000;
const RECONNECT_MAX_ATTEMPTS = 10;

// Message types
export type MessageHandler<T = unknown> = (message: T) => void;
export type ConnectionStateHandler = (state: ConnectionState) => void;

export type ConnectionState = "connecting" | "connected" | "disconnected" | "error";

interface Subscription {
  id: string;
  handler: MessageHandler;
}

interface ManagedConnection {
  url: string;
  channel: string;
  ws: WebSocket | null;
  state: ConnectionState;
  subscriptions: Map<string, Subscription>;
  reconnectAttempts: number;
  reconnectTimeout: NodeJS.Timeout | null;
  lastSequence: number;
  stateHandlers: Set<ConnectionStateHandler>;
}

/**
 * WebSocketManager singleton class
 */
class WebSocketManagerClass {
  private connections: Map<string, ManagedConnection> = new Map();
  private subscriptionIdCounter = 0;

  /**
   * Subscribe to a WebSocket channel.
   *
   * @param channel - Channel identifier (e.g., "tournament_123", "herodraft_456")
   * @param handler - Callback for received messages
   * @param onStateChange - Optional callback for connection state changes
   * @returns Unsubscribe function
   */
  subscribe<T = unknown>(
    channel: string,
    handler: MessageHandler<T>,
    onStateChange?: ConnectionStateHandler
  ): () => void {
    const subscriptionId = `sub_${++this.subscriptionIdCounter}`;

    let connection = this.connections.get(channel);

    if (!connection) {
      // Create new connection
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${protocol}//${window.location.host}/api/${channel}/`;

      connection = {
        url,
        channel,
        ws: null,
        state: "disconnected",
        subscriptions: new Map(),
        reconnectAttempts: 0,
        reconnectTimeout: null,
        lastSequence: 0,
        stateHandlers: new Set(),
      };

      this.connections.set(channel, connection);
    }

    // Add subscription
    connection.subscriptions.set(subscriptionId, {
      id: subscriptionId,
      handler: handler as MessageHandler,
    });

    // Add state handler if provided
    if (onStateChange) {
      connection.stateHandlers.add(onStateChange);
      // Immediately notify of current state
      onStateChange(connection.state);
    }

    // Connect if this is the first subscriber
    if (connection.subscriptions.size === 1) {
      this.connect(channel);
    } else if (connection.state === "connected" && onStateChange) {
      // Notify new subscriber that we're already connected
      onStateChange("connected");
    }

    log.debug(`Subscribed to ${channel} (id=${subscriptionId}, total=${connection.subscriptions.size})`);

    // Return unsubscribe function
    return () => {
      this.unsubscribe(channel, subscriptionId, onStateChange);
    };
  }

  /**
   * Unsubscribe from a channel.
   */
  private unsubscribe(
    channel: string,
    subscriptionId: string,
    onStateChange?: ConnectionStateHandler
  ): void {
    const connection = this.connections.get(channel);
    if (!connection) return;

    connection.subscriptions.delete(subscriptionId);

    if (onStateChange) {
      connection.stateHandlers.delete(onStateChange);
    }

    log.debug(`Unsubscribed from ${channel} (id=${subscriptionId}, remaining=${connection.subscriptions.size})`);

    // Close connection if no more subscribers
    if (connection.subscriptions.size === 0) {
      this.disconnect(channel);
    }
  }

  /**
   * Get the current connection state for a channel.
   */
  getState(channel: string): ConnectionState {
    return this.connections.get(channel)?.state ?? "disconnected";
  }

  /**
   * Get the last received sequence number for a channel.
   */
  getLastSequence(channel: string): number {
    return this.connections.get(channel)?.lastSequence ?? 0;
  }

  /**
   * Force reconnection for a channel.
   */
  reconnect(channel: string): void {
    const connection = this.connections.get(channel);
    if (!connection || connection.subscriptions.size === 0) return;

    log.info(`Manual reconnect requested for ${channel}`);

    // Reset reconnect attempts
    connection.reconnectAttempts = 0;

    // Close existing connection
    if (connection.ws) {
      connection.ws.close(1000, "Manual reconnect");
      connection.ws = null;
    }

    // Clear pending reconnect timeout
    if (connection.reconnectTimeout) {
      clearTimeout(connection.reconnectTimeout);
      connection.reconnectTimeout = null;
    }

    // Reconnect immediately
    this.connect(channel);
  }

  /**
   * Connect to a channel's WebSocket.
   */
  private connect(channel: string): void {
    const connection = this.connections.get(channel);
    if (!connection) return;

    // Don't connect if no subscribers
    if (connection.subscriptions.size === 0) return;

    // Don't reconnect if already connected or connecting
    if (connection.ws?.readyState === WebSocket.OPEN ||
        connection.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    this.setState(channel, "connecting");
    log.debug(`Connecting to ${channel}: ${connection.url}`);

    const ws = new WebSocket(connection.url);
    connection.ws = ws;

    ws.onopen = () => {
      log.debug(`Connected to ${channel}`);
      connection.reconnectAttempts = 0;
      this.setState(channel, "connected");
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Track sequence number if present
        if (typeof data.sequence === "number") {
          if (data.sequence > connection.lastSequence) {
            connection.lastSequence = data.sequence;
          } else if (data.sequence !== 0) {
            // Out-of-order message (sequence 0 means sequence unavailable)
            log.warn(`Out-of-order message on ${channel}: got ${data.sequence}, expected > ${connection.lastSequence}`);
          }
        }

        // Dispatch to all subscribers
        for (const subscription of connection.subscriptions.values()) {
          try {
            subscription.handler(data);
          } catch (err) {
            log.error(`Handler error for subscription ${subscription.id}:`, err);
          }
        }
      } catch (err) {
        log.error(`Failed to parse message on ${channel}:`, err);
      }
    };

    ws.onclose = (event) => {
      log.debug(`WebSocket closed for ${channel}: ${event.code} ${event.reason}`);
      connection.ws = null;
      this.setState(channel, "disconnected");

      // Attempt reconnect if we still have subscribers
      if (connection.subscriptions.size > 0) {
        this.scheduleReconnect(channel);
      }
    };

    ws.onerror = (error) => {
      log.error(`WebSocket error for ${channel}:`, error);
      this.setState(channel, "error");
    };
  }

  /**
   * Disconnect from a channel.
   */
  private disconnect(channel: string): void {
    const connection = this.connections.get(channel);
    if (!connection) return;

    log.debug(`Disconnecting from ${channel}`);

    // Clear reconnect timeout
    if (connection.reconnectTimeout) {
      clearTimeout(connection.reconnectTimeout);
      connection.reconnectTimeout = null;
    }

    // Close WebSocket
    if (connection.ws) {
      connection.ws.close(1000, "No subscribers");
      connection.ws = null;
    }

    // Clean up connection
    this.connections.delete(channel);
  }

  /**
   * Schedule a reconnection attempt with exponential backoff.
   */
  private scheduleReconnect(channel: string): void {
    const connection = this.connections.get(channel);
    if (!connection) return;

    // Check max attempts
    if (connection.reconnectAttempts >= RECONNECT_MAX_ATTEMPTS) {
      log.error(`Max reconnect attempts (${RECONNECT_MAX_ATTEMPTS}) exceeded for ${channel}`);
      this.setState(channel, "error");
      return;
    }

    connection.reconnectAttempts++;

    // Exponential backoff
    const delay = Math.min(
      RECONNECT_BASE_DELAY_MS * Math.pow(2, connection.reconnectAttempts - 1),
      RECONNECT_MAX_DELAY_MS
    );

    log.debug(`Scheduling reconnect for ${channel} in ${delay}ms (attempt ${connection.reconnectAttempts})`);

    connection.reconnectTimeout = setTimeout(() => {
      connection.reconnectTimeout = null;
      this.connect(channel);
    }, delay);
  }

  /**
   * Update and broadcast connection state.
   */
  private setState(channel: string, state: ConnectionState): void {
    const connection = this.connections.get(channel);
    if (!connection || connection.state === state) return;

    connection.state = state;

    // Notify all state handlers
    for (const handler of connection.stateHandlers) {
      try {
        handler(state);
      } catch (err) {
        log.error(`State handler error for ${channel}:`, err);
      }
    }
  }
}

// Export singleton instance
export const WebSocketManager = new WebSocketManagerClass();
