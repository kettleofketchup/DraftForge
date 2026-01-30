/**
 * WebSocket Manager - Public API
 *
 * Usage:
 *   import { getWebSocketManager } from '~/lib/websocket';
 *   const manager = getWebSocketManager();
 *   const connId = manager.connect(url, options);
 */

export { getWebSocketManager } from './WebSocketManager';
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
