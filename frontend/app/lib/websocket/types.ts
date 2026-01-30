/**
 * WebSocket Manager Types
 *
 * Centralized type definitions for the WebSocket singleton manager
 * and Zustand store integration.
 */

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

export interface ConnectionState {
  status: ConnectionStatus;
  error: string | null;
  reconnectAttempts: number;
  connectedAt: number | null;
  lastMessageAt: number | null;
}

export type DisconnectReason =
  | { type: 'intentional'; reason: string }
  | { type: 'server_closed'; code: number; reason: string }
  | { type: 'error'; message: string }
  | { type: 'max_retries_exceeded' };

/**
 * Telemetry hooks for observability.
 * All callbacks are optional - only implement what you need.
 */
export interface WebSocketTelemetry {
  /** Called when starting a connection attempt */
  onConnecting?: (url: string, attempt: number) => void;
  /** Called when connection is established */
  onConnected?: (url: string, durationMs: number) => void;
  /** Called when connection is closed */
  onDisconnected?: (url: string, reason: DisconnectReason) => void;
  /** Called when starting a reconnection attempt */
  onReconnecting?: (url: string, attempt: number, backoffMs: number) => void;
  /** Called when a message is received */
  onMessageReceived?: (url: string, type: string, sizeBytes: number) => void;
  /** Called when a message fails to parse */
  onMessageParseError?: (url: string, error: Error) => void;
}

export interface ReconnectConfig {
  /** Maximum number of reconnection attempts (default: 10) */
  maxAttempts?: number;
  /** Base delay in ms for exponential backoff (default: 1000) */
  baseDelayMs?: number;
  /** Maximum delay in ms (default: 30000) */
  maxDelayMs?: number;
}

export interface ConnectionOptions {
  /** Callback when connection state changes */
  onStateChange?: (state: ConnectionState) => void;
  /** Telemetry hooks for observability */
  telemetry?: Partial<WebSocketTelemetry>;
  /** Reconnection configuration */
  reconnect?: ReconnectConfig;
}

export type MessageHandler = (message: unknown) => void;
export type Unsubscribe = () => void;

/**
 * Internal connection tracking structure.
 * Not exported - used only by WebSocketManager.
 */
export interface WebSocketConnection {
  url: string;
  ws: WebSocket | null;
  connectionId: number;
  state: ConnectionState;
  options: ConnectionOptions;
  subscribers: Set<{ id: symbol; handler: MessageHandler }>;
  sendQueue: unknown[];
  reconnectTimeout: NodeJS.Timeout | null;
  connectTimeout: NodeJS.Timeout | null;
  intentionalClose: boolean;
  connectStartTime: number | null;
}
