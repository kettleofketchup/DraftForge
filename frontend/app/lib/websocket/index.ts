/**
 * WebSocket Manager - Public API
 *
 * Usage:
 *   import { getWebSocketManager } from '~/lib/websocket';
 *   const manager = getWebSocketManager();
 *   const connId = manager.connect(url, options);
 */

export type {
  ConnectionOptions,
  ConnectionState,
  ConnectionStatus,
  DisconnectReason,
  MessageHandler,
  ReconnectConfig,
  Unsubscribe,
  WebSocketTelemetry,
} from './types';
export { getWebSocketManager } from './WebSocketManager';
