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
  // Computed from `tick.server_time - Date.now()` at receive — lets
  // outbound calls (e.g. submitPick) send timestamps in server-clock
  // reference. Defaults to 0 until the first tick arrives.
  serverClockOffsetMs: number;
  selectedHeroId: number | null;
  searchQuery: string;
  lastEvent: HeroDraftEvent | null;

  // Internal tracking
  _connectionId: string | null;
  _unsubscribe: Unsubscribe | null;
  _currentDraftId: number | null;
  _heartbeatInterval: ReturnType<typeof setInterval> | null;
  // Receive-side tick gap detection. Server logs `tick_loop_stalled`
  // when the broadcaster itself stalls; this catches the COMPLEMENTARY
  // case where the broadcast happened but didn't reach this client
  // (WS hiccup, browser tab throttled, channel-layer queue saturated).
  _lastTickReceivedAtMs: number | null;

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
  serverClockOffsetMs: 0,
  selectedHeroId: null,
  searchQuery: '',
  lastEvent: null,
  _connectionId: null,
  _unsubscribe: null,
  _currentDraftId: null,
  _heartbeatInterval: null,
  _lastTickReceivedAtMs: null,
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
      staleTimeoutMs: 3000, // Server pings every 1s; 3 missed pings = stale
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
        onStaleDetected: (connUrl, staleDurationMs) => {
          log.warn(`Stale connection: ${connUrl} (${staleDurationMs}ms without messages)`);
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

          // On hero_selected, patch the tick with the NEW round's anchors
          // immediately. The next 1Hz server tick would otherwise arrive up
          // to a second later, so without this patch the grace timer keeps
          // running against the previous round's `round_started_at` until
          // the new tick lands — the user sees the timer linger on the
          // previous team.
          if (message.event_type === 'hero_selected') {
            const prevTick = get().tick;
            const newDraft = message.draft_state;
            const newRoundIdx = newDraft?.current_round ?? null;
            const newRound =
              newRoundIdx !== null && newDraft?.rounds
                ? newDraft.rounds[newRoundIdx] ?? null
                : null;

            if (prevTick && newRound && newDraft) {
              // Match teams by ID order (matches server-side tick ordering).
              const teamsById = [...newDraft.draft_teams].sort(
                (a, b) => a.id - b.id,
              );
              const teamA = teamsById[0] ?? null;
              const teamB = teamsById[1] ?? null;
              set({
                selectedHeroId: null,
                tick: {
                  ...prevTick,
                  current_round: newRoundIdx,
                  active_team_id: newRound.draft_team,
                  round_started_at: newRound.started_at,
                  round_grace_time_ms: newRound.grace_time_ms,
                  team_a_id: teamA?.id ?? prevTick.team_a_id,
                  team_a_reserve_ms:
                    teamA?.reserve_time_remaining ?? prevTick.team_a_reserve_ms,
                  team_b_id: teamB?.id ?? prevTick.team_b_id,
                  team_b_reserve_ms:
                    teamB?.reserve_time_remaining ?? prevTick.team_b_reserve_ms,
                },
              });
            } else {
              // No new round (draft complete) — clear active team so the
              // previous picker's reserve stops burning.
              set({
                selectedHeroId: null,
                tick: prevTick
                  ? { ...prevTick, active_team_id: null }
                  : prevTick,
              });
            }
          }

          set({ lastEvent: message as HeroDraftEvent });
          break;

        case 'herodraft_tick':
          debugLog('herodraft_tick received', {
            draft_state: message.draft_state,
            current_round: message.current_round,
            active_team_id: message.active_team_id,
            server_time: message.server_time,
            round_started_at: message.round_started_at,
          });

          // Re-anchor clock offset on every tick. Includes one-way
          // network latency in the offset, which means submitPick's
          // outbound timestamp will be ~RTT/2 in the past relative to
          // server-receive — that's the desired behaviour (the server's
          // 2s sanity window absorbs it cleanly).
          const tickReceivedAtMs = Date.now();
          const serverTimeMs = new Date(message.server_time).getTime();
          const serverClockOffsetMs = Number.isFinite(serverTimeMs)
            ? serverTimeMs - tickReceivedAtMs
            : 0;

          // Gap detection — expected cadence is 1Hz. If we go >2s without
          // a tick, log it. This catches client-side delivery problems
          // the server can't see (WS hiccup, throttled tab, queue
          // saturation) and complements server's `tick_loop_stalled`.
          const lastTickAt = get()._lastTickReceivedAtMs;
          if (lastTickAt !== null) {
            const gapMs = tickReceivedAtMs - lastTickAt;
            if (gapMs > 2000) {
              log.warn('client_tick_gap', {
                draft_id: get()._currentDraftId,
                expected_gap_ms: 1000,
                actual_gap_ms: gapMs,
                stall_ms: gapMs - 1000,
              });
            }
          }

          set({
            _lastTickReceivedAtMs: tickReceivedAtMs,
            serverClockOffsetMs,
            tick: {
              type: 'herodraft_tick',
              draft_state: message.draft_state,
              server_time: message.server_time,
              current_round: message.current_round,
              active_team_id: message.active_team_id,
              round_started_at: message.round_started_at,
              round_grace_time_ms: message.round_grace_time_ms,
              team_a_id: message.team_a_id,
              team_a_reserve_ms: message.team_a_reserve_ms,
              team_b_id: message.team_b_id,
              team_b_reserve_ms: message.team_b_reserve_ms,
              resuming_until: message.resuming_until,
            },
          });
          break;

        case 'herodraft_kicked': {
          log.warn('Kicked from draft:', message.reason);
          get().stopHeartbeat();
          // Disconnect to prevent auto-reconnect loop
          // (server will close connection after sending kicked message)
          const kickedConnId = get()._connectionId;
          const kickedUnsub = get()._unsubscribe;
          if (kickedUnsub) kickedUnsub();
          if (kickedConnId) {
            manager.disconnect(kickedConnId, 'Kicked by server');
          }
          // Clear connection state but preserve wasKicked flag.
          // `isConnected` is a derived selector (line 353), not state — the
          // canonical disconnected signal is `status: 'disconnected'`.
          set({
            _connectionId: null,
            _unsubscribe: null,
            wasKicked: true,
            error: 'Connection replaced by new tab',
            status: 'disconnected',
          });
          break;
        }
      }
    });

    // Set status to 'connecting' immediately so the guard at the top of
    // connect() works during the WebSocketManager's 50ms StrictMode debounce.
    set({
      _connectionId: connectionId,
      _unsubscribe: unsubscribe,
      _currentDraftId: draftId,
      wasKicked: false,
      status: 'connecting',
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
    const { _currentDraftId, wasKicked } = get();
    // Don't reconnect if we were kicked - prevents infinite loop with multiple tabs
    if (wasKicked) {
      log.warn('Reconnect blocked: was kicked from this draft');
      return;
    }
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

  /** True when it's the current user's turn to pick/ban */
  isMyTurn: (s: HeroDraftState, currentUserId: number | undefined) => {
    if (!currentUserId) return false;
    if (s.draft?.state !== 'drafting') return false;

    // Get active team ID from tick first, then fall back to current round
    const activeTeamId = s.tick?.active_team_id
      ?? (s.draft.current_round !== null
        ? s.draft.rounds[s.draft.current_round]?.draft_team
        : null);

    if (!activeTeamId) return false;

    // Find user's team (as captain or member)
    const myTeam = s.draft.draft_teams.find(t =>
      t.captain?.pk === currentUserId ||
      t.members?.some(m => m.pk === currentUserId)
    );

    return myTeam?.id === activeTeamId;
  },

  /** Get the current action type (pick or ban) */
  currentAction: (s: HeroDraftState) => {
    if (!s.draft || s.draft.current_round === null) return null;
    return s.draft.rounds[s.draft.current_round]?.action_type ?? null;
  },
};

/**
 * Returns the current server time as an ISO string, derived from the
 * latest tick's server_time plus elapsed local time. Use this instead of
 * `new Date().toISOString()` for any timestamp the server will compare
 * against its own clock (e.g. `client_picked_at` on pick submission).
 * Falls back to local clock when no tick has arrived yet — the server's
 * 2s sanity window then degrades cleanly to receive-time.
 */
export function getServerNowISO(): string {
  const { serverClockOffsetMs } = useHeroDraftStore.getState();
  return new Date(Date.now() + serverClockOffsetMs).toISOString();
}
