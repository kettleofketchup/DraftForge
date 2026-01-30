/**
 * Draft WebSocket Store
 *
 * Zustand store for team draft WebSocket state.
 * Manages connection lifecycle via WebSocketManager singleton.
 */

import { create } from 'zustand';
import { toast } from 'sonner';
import { getLogger } from '~/lib/logger';
import { getWebSocketManager } from '~/lib/websocket';
import type { ConnectionStatus, Unsubscribe } from '~/lib/websocket';
import type { DraftEvent, WebSocketDraftState, WebSocketMessage } from '~/types/draftEvent';

const log = getLogger('draftWebSocketStore');

// Events that trigger toast notifications
const SIGNIFICANT_EVENTS: DraftEvent['event_type'][] = [
  'draft_started',
  'draft_completed',
  'player_picked',
  'tie_roll',
];

function getEventMessage(event: DraftEvent): string {
  switch (event.event_type) {
    case 'draft_started':
      return 'Draft has started!';
    case 'draft_completed':
      return 'Draft completed!';
    case 'player_picked': {
      const payload = event.payload as { captain_name: string; picked_name: string; pick_number: number };
      return `${payload.captain_name} picked ${payload.picked_name} (Pick ${payload.pick_number})`;
    }
    case 'tie_roll': {
      const payload = event.payload as { winner_name: string; roll_rounds: { captain_id: number; roll: number }[][] };
      const lastRound = payload.roll_rounds[payload.roll_rounds.length - 1];
      const rolls = lastRound.map((r) => r.roll).join(' vs ');
      return `Tie resolved! ${payload.winner_name} wins (${rolls})`;
    }
    case 'captain_assigned': {
      const payload = event.payload as { captain_name: string };
      return `${payload.captain_name} is picking next`;
    }
    case 'pick_undone': {
      const payload = event.payload as { undone_player_name: string; pick_number: number };
      return `Pick ${payload.pick_number} undone (${payload.undone_player_name})`;
    }
    default:
      return 'Draft event occurred';
  }
}

interface DraftWebSocketState {
  // Connection state (synced from manager)
  status: ConnectionStatus;
  error: string | null;
  reconnectAttempts: number;

  // Domain state
  events: DraftEvent[];
  draftState: WebSocketDraftState | null;
  lastEventTimestamp: number | null;
  hasNewEvent: boolean;

  // Internal tracking
  _connectionId: string | null;
  _unsubscribe: Unsubscribe | null;
  _currentDraftId: number | null;

  // Actions
  connect: (draftId: number) => void;
  disconnect: () => void;
  clearNewEventFlag: () => void;
  reset: () => void;
}

const initialState = {
  status: 'disconnected' as ConnectionStatus,
  error: null,
  reconnectAttempts: 0,
  events: [],
  draftState: null,
  lastEventTimestamp: null,
  hasNewEvent: false,
  _connectionId: null,
  _unsubscribe: null,
  _currentDraftId: null,
};

export const useDraftWebSocketStore = create<DraftWebSocketState>((set, get) => ({
  ...initialState,

  connect: (draftId: number) => {
    const current = get();

    // Already connected to same draft
    if (current._currentDraftId === draftId && current.status !== 'disconnected') {
      log.debug('Already connected to same draft, skipping');
      return;
    }

    // Different draft - disconnect first
    if (current._currentDraftId !== null && current._currentDraftId !== draftId) {
      log.debug(`Switching from draft ${current._currentDraftId} to ${draftId}`);
      get().disconnect();
    }

    // Clean up any existing connection
    if (current._unsubscribe) {
      current._unsubscribe();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/api/draft/${draftId}/`;

    log.debug(`Connecting to draft WebSocket: ${url}`);

    const manager = getWebSocketManager();

    const connectionId = manager.connect(url, {
      onStateChange: (state) => {
        set({
          status: state.status,
          error: state.error,
          reconnectAttempts: state.reconnectAttempts,
        });
      },
      telemetry: {
        onConnected: (connUrl, durationMs) => {
          log.debug(`Connected to ${connUrl} in ${durationMs}ms`);
        },
        onDisconnected: (connUrl, reason) => {
          log.debug(`Disconnected from ${connUrl}:`, reason);
        },
        onReconnecting: (connUrl, attempt, backoffMs) => {
          log.debug(`Reconnecting to ${connUrl}, attempt ${attempt}, backoff ${backoffMs}ms`);
        },
      },
    });

    const unsubscribe = manager.subscribe(connectionId, (rawMessage) => {
      const message = rawMessage as WebSocketMessage;

      if (message.type === 'initial_events' && message.events) {
        log.debug(`Received ${message.events.length} initial events`);
        set({ events: message.events });
      } else if (message.type === 'draft_event' && message.event) {
        const newEvent = message.event;
        log.debug('Received draft event:', newEvent.event_type);

        // Add to events list (newest first)
        set((state) => ({
          events: [newEvent, ...state.events],
          lastEventTimestamp: Date.now(),
          hasNewEvent: true,
        }));

        // Show toast for significant events
        if (SIGNIFICANT_EVENTS.includes(newEvent.event_type)) {
          toast(getEventMessage(newEvent));
        }

        // Update draft state if included
        if (message.draft_state) {
          log.debug('Updating draft state from WebSocket');
          set({ draftState: message.draft_state });
        }
      }
    });

    set({
      _connectionId: connectionId,
      _unsubscribe: unsubscribe,
      _currentDraftId: draftId,
    });
  },

  clearNewEventFlag: () => {
    set({ hasNewEvent: false });
  },

  disconnect: () => {
    const { _connectionId, _unsubscribe } = get();

    if (_unsubscribe) {
      _unsubscribe();
    }

    if (_connectionId) {
      const manager = getWebSocketManager();
      manager.disconnect(_connectionId, 'Store disconnect');
    }

    set({
      ...initialState,
    });
  },

  reset: () => {
    get().disconnect();
  },
}));

// ─────────────────────────────────────────────────────────────────
// Selectors (for derived state - use with useDraftWebSocketStore)
// ─────────────────────────────────────────────────────────────────

export const draftWsSelectors = {
  /** True when connecting or reconnecting */
  isLoading: (s: DraftWebSocketState) =>
    s.status === 'connecting' || s.status === 'reconnecting',

  /** True when there's a recent event (within 3 seconds) */
  hasRecentEvent: (s: DraftWebSocketState) =>
    s.lastEventTimestamp !== null && Date.now() - s.lastEventTimestamp < 3000,

  /** True when WebSocket is connected */
  isConnected: (s: DraftWebSocketState) => s.status === 'connected',

  /** Number of remaining players in draft */
  usersRemainingCount: (s: DraftWebSocketState) =>
    s.draftState?.users_remaining?.length ?? 0,

  /** True when draft is completed (no users remaining) */
  isDraftCompleted: (s: DraftWebSocketState) =>
    s.draftState !== null && (s.draftState.users_remaining?.length ?? -1) === 0,
};
