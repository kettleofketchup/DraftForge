# WebSocket Manager + Zustand Store Architecture

**Date:** 2026-01-30
**Status:** Approved

## Overview

Replace per-component WebSocket hooks with a singleton WebSocketManager class and domain-specific Zustand stores. This provides:

- Centralized connection lifecycle management
- Consistent reconnection behavior with exponential backoff
- Telemetry hooks for observability
- Clean separation between connection logic and domain state

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Component Layer                     │
│  - Uses store hooks: useDraftWebSocketStore()       │
│  - Renders based on store state                      │
│  - No WebSocket awareness                            │
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│                  Store Layer                         │
│  - Holds domain state (draft, events, connection)   │
│  - Validates/transforms WebSocket messages (Zod)    │
│  - Exposes typed actions (connect, disconnect)      │
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│             WebSocketManager Layer                   │
│  - Connection lifecycle (connect, reconnect, close) │
│  - Raw message routing to subscribers               │
│  - Send queue management                            │
│  - Telemetry event emission                         │
│  - No domain knowledge                              │
└─────────────────────────────────────────────────────┘
```

## WebSocketManager (Singleton)

### Responsibilities

- Own WebSocket connections keyed by URL
- Handle reconnection with exponential backoff (1s → 30s, max 10 attempts)
- Track connection IDs to ignore stale callbacks
- Debounce connections for React StrictMode (50ms)
- Track intentional closes to prevent unwanted reconnects
- Manage send queue with backpressure (max 100 messages)
- Emit telemetry events

### Interface

```typescript
// frontend/app/lib/websocket/types.ts

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

interface ConnectionState {
  status: ConnectionStatus;
  error: string | null;
  reconnectAttempts: number;
  connectedAt: number | null;
  lastMessageAt: number | null;
}

interface ConnectionOptions {
  onStateChange?: (state: ConnectionState) => void;
  telemetry?: Partial<WebSocketTelemetry>;
  reconnect?: {
    maxAttempts?: number;      // default: 10
    baseDelayMs?: number;      // default: 1000
    maxDelayMs?: number;       // default: 30000
  };
}

interface WebSocketTelemetry {
  onConnecting?: (url: string, attempt: number) => void;
  onConnected?: (url: string, durationMs: number) => void;
  onDisconnected?: (url: string, reason: DisconnectReason) => void;
  onReconnecting?: (url: string, attempt: number, backoffMs: number) => void;
  onMessageReceived?: (url: string, type: string, sizeBytes: number) => void;
}

type DisconnectReason =
  | { type: 'intentional'; reason: string }
  | { type: 'server_closed'; code: number; reason: string }
  | { type: 'error'; message: string }
  | { type: 'max_retries_exceeded' };

type MessageHandler = (message: unknown) => void;
type Unsubscribe = () => void;

// frontend/app/lib/websocket/WebSocketManager.ts

class WebSocketManager {
  connect(url: string, options?: ConnectionOptions): string;  // returns connectionId
  disconnect(connectionId: string, reason?: string): void;
  subscribe(connectionId: string, handler: MessageHandler): Unsubscribe;
  send(connectionId: string, message: unknown): boolean;  // false if queue full
  getState(connectionId: string): ConnectionState | null;
}

// Singleton access with SSR guard and HMR cleanup
export function getWebSocketManager(): WebSocketManager;
```

### Implementation Details

**StrictMode Handling:**
- 50ms debounce before creating WebSocket
- Connection ID incremented on each attempt
- Stale callbacks ignored by checking current connection ID

**HMR Cleanup:**
```typescript
if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    instance?.disconnectAll();
    instance = null;
  });
}
```

**Reconnection Logic:**
- Exponential backoff: delay = min(baseDelay * 2^attempt, maxDelay)
- Only reconnect on unexpected closes (code !== 1000)
- Cancel pending reconnects on intentional disconnect
- Reset attempts on successful connection

**Send Queue:**
- Queue messages when status !== 'connected'
- Flush queue on connection in FIFO order
- Max 100 messages, drop oldest on overflow
- Return false from send() when queue full

## Zustand Stores

### DraftWebSocketStore

```typescript
// frontend/app/store/draftWebSocketStore.ts

interface DraftWebSocketState {
  // Connection state (synced from manager)
  status: ConnectionStatus;
  error: string | null;
  reconnectAttempts: number;

  // Domain state
  events: DraftEvent[];
  draftState: WebSocketDraftState | null;
  lastEventTimestamp: number | null;

  // Actions
  connect: (draftId: number) => void;
  disconnect: () => void;
}

// Selectors (exported separately for memoization)
export const draftWsSelectors = {
  isLoading: (s: DraftWebSocketState) =>
    s.status === 'connecting' || s.status === 'reconnecting',
  hasRecentEvent: (s: DraftWebSocketState) =>
    s.lastEventTimestamp !== null && Date.now() - s.lastEventTimestamp < 3000,
  isConnected: (s: DraftWebSocketState) => s.status === 'connected',
};
```

**Message Handling:**
- Validate incoming messages with Zod schemas
- Transform to domain types
- Update store state atomically
- Show toasts for significant events

### HeroDraftWebSocketStore

```typescript
// frontend/app/store/heroDraftWebSocketStore.ts

interface HeroDraftWebSocketState {
  // Connection state
  status: ConnectionStatus;
  error: string | null;
  reconnectAttempts: number;

  // Domain state (merged from existing heroDraftStore)
  draft: HeroDraft | null;
  tick: HeroDraftTick | null;

  // Actions
  connect: (draftId: number) => void;
  disconnect: () => void;

  // Computed helpers (from existing store)
  getCurrentTeam: () => DraftTeam | null;
  getOtherTeam: () => DraftTeam | null;
  isMyTurn: (userId: number) => boolean;
}
```

## Component Integration

### Before (with hooks)

```typescript
function DraftModal({ tournament, open }) {
  const {
    isConnected: wsConnected,
    events: draftEvents,
  } = useDraftWebSocket({
    draftId: draft?.pk ?? null,
    onDraftStateUpdate: handleDraftStateUpdate,
  });
  // ...
}
```

### After (with store)

```typescript
function DraftModal({ tournament, open }) {
  const draftId = tournament?.draft?.pk;

  // Subscribe to store state
  const status = useDraftWebSocketStore(s => s.status);
  const draftState = useDraftWebSocketStore(s => s.draftState);
  const events = useDraftWebSocketStore(s => s.events);
  const connect = useDraftWebSocketStore(s => s.connect);
  const disconnect = useDraftWebSocketStore(s => s.disconnect);

  // Selectors for derived state
  const isConnected = useDraftWebSocketStore(draftWsSelectors.isConnected);

  // Connect/disconnect based on modal state
  useEffect(() => {
    if (open && draftId) {
      connect(draftId);
    }
    return () => disconnect();
  }, [open, draftId, connect, disconnect]);

  // React to draftState changes
  useEffect(() => {
    if (draftState) {
      setDraft(draftState);
      if (draftState.tournament) {
        setTournament(prev => ({ ...prev, ...draftState.tournament }));
      }
    }
  }, [draftState]);
}
```

## Files to Create

| File | Purpose |
|------|---------|
| `frontend/app/lib/websocket/types.ts` | Type definitions |
| `frontend/app/lib/websocket/WebSocketManager.ts` | Singleton manager class |
| `frontend/app/lib/websocket/index.ts` | Public exports |
| `frontend/app/store/draftWebSocketStore.ts` | Team draft WebSocket store |
| `frontend/app/store/heroDraftWebSocketStore.ts` | Hero draft WebSocket store |

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/app/components/draft/draftModal.tsx` | Use store instead of hook |
| `frontend/app/components/herodraft/HeroDraftModal.tsx` | Use store instead of hook |
| `frontend/app/components/draft/hooks/useAutoRefreshDraft.tsx` | Read from store |

## Files to Delete

| File | Reason |
|------|--------|
| `frontend/app/components/draft/hooks/useDraftWebSocket.ts` | Replaced by store |
| `frontend/app/components/herodraft/hooks/useHeroDraftWebSocket.ts` | Replaced by store |

## Migration Strategy

1. Create WebSocketManager and types
2. Create draftWebSocketStore
3. Update draftModal.tsx to use store
4. Update useAutoRefreshDraft to read from store
5. Delete useDraftWebSocket hook
6. Repeat for herodraft (store, modal, delete hook)
7. Merge existing heroDraftStore into heroDraftWebSocketStore

## Testing

- Unit tests for WebSocketManager reconnection logic
- Integration tests for store message handling
- E2E tests via existing Playwright demos (snake, shuffle, herodraft)

## Future Enhancements

- Heartbeat/ping-pong for half-open connection detection
- Latency measurement and reporting
- Connection health status in UI
- Telemetry integration with monitoring service
