/**
 * HeroDraft Store
 *
 * Zustand store for hero draft state with WebSocket integration.
 * Manages draft state, UI state, and real-time updates via WebSocket.
 */

import { create } from 'zustand';
import { getLogger } from '~/lib/logger';
import { getWebSocketManager } from '~/lib/websocket';
import type { ConnectionStatus, Unsubscribe } from '~/lib/websocket';
import type { HeroDraft, HeroDraftTick, HeroDraftEvent, DraftTeam } from '~/components/herodraft/types';
import { HeroDraftWebSocketMessageSchema } from '~/components/herodraft/schemas';

const log = getLogger('heroDraftStore');

// Debug logging
const DEBUG = false;
const debugLog = (...args: unknown[]) => {
  if (DEBUG) {
    console.log('[HeroDraft]', ...args);
  }
};

interface HeroDraftState {
  // Connection state (synced from manager)
  status: ConnectionStatus;
  error: string | null;
  reconnectAttempts: number;
  wasKicked: boolean;

  // Domain state
  draft: HeroDraft | null;
  tick: HeroDraftTick | null;
  selectedHeroId: number | null;
  searchQuery: string;
  lastEvent: HeroDraftEvent | null;

  // Internal tracking
  _connectionId: string | null;
  _unsubscribe: Unsubscribe | null;
  _currentDraftId: number | null;
  _heartbeatInterval: ReturnType<typeof setInterval> | null;

  // Actions
  connect: (draftId: number) => void;
  disconnect: () => void;
  reconnect: () => void;
  startHeartbeat: () => void;
  stopHeartbeat: () => void;
  setSelectedHeroId: (heroId: number | null) => void;
  setSearchQuery: (query: string) => void;
  reset: () => void;

  // Computed helpers
  getCurrentTeam: () => DraftTeam | null;
  getOtherTeam: () => DraftTeam | null;
  isMyTurn: (userId: number) => boolean;
  getUsedHeroIds: () => number[];
}

const initialState = {
  status: 'disconnected' as ConnectionStatus,
  error: null,
  reconnectAttempts: 0,
  wasKicked: false,
  draft: null,
  tick: null,
  selectedHeroId: null,
  searchQuery: '',
  lastEvent: null,
  _connectionId: null,
  _unsubscribe: null,
  _currentDraftId: null,
  _heartbeatInterval: null,
};

export const useHeroDraftStore = create<HeroDraftState>((set, get) => ({
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

    // Clean up any existing subscription
    if (current._unsubscribe) {
      current._unsubscribe();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/api/herodraft/${draftId}/`;

    log.debug(`Connecting to HeroDraft WebSocket: ${url}`);

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
      // Validate message with Zod schema
      const parseResult = HeroDraftWebSocketMessageSchema.safeParse(rawMessage);
      if (!parseResult.success) {
        log.warn('Invalid WebSocket message format:', parseResult.error.issues);
        debugLog('Raw message that failed validation:', JSON.stringify(rawMessage, null, 2));
        return;
      }

      const message = parseResult.data;
      debugLog('Message received:', message.type, message);

      switch (message.type) {
        case 'initial_state':
          debugLog('initial_state received', {
            state: message.draft_state.state,
            current_round: message.draft_state.current_round,
            rounds_count: message.draft_state.rounds.length,
          });
          set({ draft: message.draft_state });
          break;

        case 'herodraft_event':
          debugLog('herodraft_event received', {
            event_type: message.event_type,
            draft_team_id: message.draft_team?.id,
            has_draft_state: !!message.draft_state,
          });

          if (message.draft_state) {
            debugLog('Updating draft state:', message.draft_state.state, 'current_round:', message.draft_state.current_round);
            set({ draft: message.draft_state });
          }

          set({ lastEvent: message as HeroDraftEvent });
          break;

        case 'herodraft_tick':
          debugLog('herodraft_tick received', {
            draft_state: message.draft_state,
            current_round: message.current_round,
            active_team_id: message.active_team_id,
            grace_time_remaining_ms: message.grace_time_remaining_ms,
            countdown_remaining_ms: message.countdown_remaining_ms,
          });

          set({
            tick: {
              type: 'herodraft_tick',
              draft_state: message.draft_state,
              current_round: message.current_round,
              active_team_id: message.active_team_id,
              grace_time_remaining_ms: message.grace_time_remaining_ms,
              team_a_id: message.team_a_id,
              team_a_reserve_ms: message.team_a_reserve_ms,
              team_b_id: message.team_b_id,
              team_b_reserve_ms: message.team_b_reserve_ms,
              countdown_remaining_ms: message.countdown_remaining_ms,
            },
          });
          break;

        case 'herodraft_kicked':
          log.warn('Kicked from draft:', message.reason);
          get().stopHeartbeat();
          set({ wasKicked: true, error: 'Connection replaced by new tab' });
          break;
      }
    });

    set({
      _connectionId: connectionId,
      _unsubscribe: unsubscribe,
      _currentDraftId: draftId,
      wasKicked: false,
    });
  },

  disconnect: () => {
    const { _connectionId, _unsubscribe } = get();

    // Stop heartbeat first
    get().stopHeartbeat();

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

  reconnect: () => {
    const { _currentDraftId } = get();
    if (_currentDraftId) {
      get().disconnect();
      // Small delay before reconnecting
      setTimeout(() => {
        get().connect(_currentDraftId);
      }, 100);
    }
  },

  startHeartbeat: () => {
    const { _connectionId, _heartbeatInterval } = get();

    // Already running
    if (_heartbeatInterval) return;

    if (!_connectionId) {
      log.warn('Cannot start heartbeat: not connected');
      return;
    }

    log.debug('Starting captain heartbeat');
    const manager = getWebSocketManager();

    // Send immediate heartbeat
    manager.send(_connectionId, { type: 'heartbeat' });

    // Send heartbeat every 3 seconds
    const interval = setInterval(() => {
      const currentConnId = get()._connectionId;
      if (currentConnId) {
        manager.send(currentConnId, { type: 'heartbeat' });
      }
    }, 3000);

    set({ _heartbeatInterval: interval });
  },

  stopHeartbeat: () => {
    const { _heartbeatInterval } = get();
    if (_heartbeatInterval) {
      clearInterval(_heartbeatInterval);
      set({ _heartbeatInterval: null });
    }
  },

  setSelectedHeroId: (heroId) => set({ selectedHeroId: heroId }),
  setSearchQuery: (query) => set({ searchQuery: query }),

  reset: () => {
    get().disconnect();
  },

  // Computed helpers
  getCurrentTeam: () => {
    const { draft, tick } = get();
    if (!draft || !tick) return null;
    return draft.draft_teams.find((t) => t.id === tick.active_team_id) || null;
  },

  getOtherTeam: () => {
    const { draft, tick } = get();
    if (!draft || !tick) return null;
    return draft.draft_teams.find((t) => t.id !== tick.active_team_id) || null;
  },

  isMyTurn: (userId: number) => {
    const currentTeam = get().getCurrentTeam();
    return currentTeam?.captain?.pk === userId;
  },

  getUsedHeroIds: () => {
    const { draft } = get();
    if (!draft) return [];
    return draft.rounds
      .filter((r) => r.hero_id !== null)
      .map((r) => r.hero_id as number);
  },
}));

// ─────────────────────────────────────────────────────────────────
// Selectors
// ─────────────────────────────────────────────────────────────────

export const heroDraftSelectors = {
  /** True when connecting or reconnecting */
  isLoading: (s: HeroDraftState) =>
    s.status === 'connecting' || s.status === 'reconnecting',

  /** True when WebSocket is connected */
  isConnected: (s: HeroDraftState) => s.status === 'connected',

  /** True when draft is in an active state */
  isActive: (s: HeroDraftState) =>
    s.draft?.state === 'drafting' || s.draft?.state === 'choosing',

  /** True when draft is completed */
  isCompleted: (s: HeroDraftState) => s.draft?.state === 'completed',

  /** True when waiting for captains */
  isWaiting: (s: HeroDraftState) => s.draft?.state === 'waiting_for_captains',

  /** True when draft is paused */
  isPaused: (s: HeroDraftState) => s.draft?.state === 'paused',

  /** True when draft is in resuming countdown (3-2-1 before resume) */
  isResuming: (s: HeroDraftState) => s.draft?.state === 'resuming',
};
