/**
 * Draft WebSocket Store
 *
 * Zustand store for team draft WebSocket state.
 * Manages connection lifecycle via WebSocketManager singleton.
 */

import { create } from 'zustand';
import { toast } from 'sonner';
import type { UserType } from '~/components/user/types';
import { captureClockOffset, serverNowISO, startHeartbeatLoop } from '~/lib/draftClock';
import { getLogger } from '~/lib/logger';
import { getWebSocketManager } from '~/lib/websocket';
import type { ConnectionStatus, Unsubscribe } from '~/lib/websocket';
import { useUserStore } from '~/store/userStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import type { DraftEvent, DraftPausedPayload, PlayerPickedPayload, TieRollPayload, WebSocketDraftState, WebSocketMessage } from '~/types/draftEvent';
import type { TieResolution } from '~/components/teamdraft/types';
import { DraftTickSchema } from '~/components/teamdraft/schemas';
import type { DraftTick, TeamDraftState } from '~/components/teamdraft/schemas';
import { getEventToast } from '~/components/teamdraft/eventMessages';
import { PlayerPickedToast } from '~/components/teamdraft/DraftToasts';

const log = getLogger('draftWebSocketStore');

function showEventToast(event: DraftEvent): void {
  if (event.event_type === 'player_picked') {
    toast(PlayerPickedToast({ payload: event.payload as PlayerPickedPayload }));
    return;
  }
  const message = getEventToast(event);
  if (message !== null) toast(message);
}

const EMPTY_TEAMS: DraftTick['teams'] = [];

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
  pendingTieResolution: TieResolution | null;
  tick: DraftTick | null;
  serverClockOffsetMs: number;
  captainFresh: Record<number, boolean>;
  forceJumpToRoundPk: number | null;

  // Internal tracking
  _connectionId: string | null;
  _unsubscribe: Unsubscribe | null;
  _currentDraftId: number | null;
  _stopHeartbeat: (() => void) | null;
  _lastTickReceivedAtMs: number | null;
  _lastStateEventPk: number | null;

  // Actions
  connect: (draftId: number) => void;
  disconnect: () => void;
  clearNewEventFlag: () => void;
  setPendingTieResolution: (tr: TieResolution) => void;
  clearPendingTieResolution: () => void;
  startHeartbeat: () => void;
  stopHeartbeat: () => void;
  jumpToPickNumber: (pickNumber: number) => boolean;
  getServerNowISO: () => string;
  clearForceJump: () => void;
  /** Apply draft events buffered since the last flush (normally runs on a short timer). */
  flushDraftEvents: () => void;
  reset: () => void;
}

function numericKeys(fresh: Record<string, boolean> | undefined): Record<number, boolean> {
  const out: Record<number, boolean> = {};
  for (const [k, v] of Object.entries(fresh ?? {})) out[Number(k)] = v;
  return out;
}

// The tick loop flips resuming -> drafting without an event; only its ticks report it.
function resumeEndedBy(tick: DraftTick, draftState: WebSocketDraftState | null): boolean {
  if (draftState?.state !== 'resuming' || tick.draft_state !== 'drafting') return false;
  const until = draftState.resuming_until ? Date.parse(draftState.resuming_until) : NaN;
  return !Number.isNaN(until) && Date.parse(tick.server_time) >= until;
}

/** Ingest _users dict from WS draft state into entity cache. */
function ingestDraftStateUsers(draftState: WebSocketDraftState): void {
  if (draftState._users) {
    const users = Object.values(draftState._users) as UserType[];
    const orgId = useOrgStore.getState().currentOrg?.pk;
    useUserCacheStore.getState().upsert(users, { orgId });
  }
}

/**
 * Hydrate slim WS draft state (pk-only user references) back to full user
 * objects using the _users dict. This ensures downstream consumers that
 * access .mmr, .username, .pk on users_remaining, draft_rounds.captain/choice,
 * and tournament.teams.members continue to work correctly.
 */
function hydrateSlimDraftState(slim: WebSocketDraftState): WebSocketDraftState {
  const usersMap = slim._users;
  if (!usersMap) return slim;

  const resolve = (ref: unknown): unknown => {
    if (typeof ref === 'number') return usersMap[ref] ?? { pk: ref };
    return ref;
  };

  const resolveArray = (refs: unknown): unknown[] => {
    if (!Array.isArray(refs)) return [];
    return refs.map((r) => (typeof r === 'number' ? (usersMap[r] ?? { pk: r }) : r));
  };

  return {
    ...slim,
    users_remaining: resolveArray(slim.users_remaining) as WebSocketDraftState['users_remaining'],
    draft_rounds: (slim.draft_rounds ?? []).map((round) => ({
      ...round,
      captain: resolve(round.captain),
      choice: resolve(round.choice),
      // Hydrate nested team if present
      ...(round.team && typeof round.team === 'object'
        ? {
            team: {
              ...(round.team as Record<string, unknown>),
              members: resolveArray((round.team as Record<string, unknown>).members),
              captain: resolve((round.team as Record<string, unknown>).captain),
              deputy_captain: resolve((round.team as Record<string, unknown>).deputy_captain),
            },
          }
        : {}),
    })),
    tournament: slim.tournament
      ? {
          ...slim.tournament,
          teams: (slim.tournament.teams ?? []).map((team) => ({
            ...team,
            members: resolveArray((team as Record<string, unknown>).members),
            captain: resolve((team as Record<string, unknown>).captain),
            deputy_captain: resolve((team as Record<string, unknown>).deputy_captain),
          })),
        }
      : undefined,
  };
}

const initialState = {
  status: 'disconnected' as ConnectionStatus,
  error: null,
  reconnectAttempts: 0,
  events: [],
  draftState: null,
  lastEventTimestamp: null,
  hasNewEvent: false,
  pendingTieResolution: null,
  tick: null,
  serverClockOffsetMs: 0,
  captainFresh: {},
  forceJumpToRoundPk: null,
  _connectionId: null,
  _unsubscribe: null,
  _currentDraftId: null,
  _stopHeartbeat: null,
  _lastTickReceivedAtMs: null,
  _lastStateEventPk: null,
};

/** Events that arrive within this window render together (one store update per burst). */
export const DRAFT_EVENT_FLUSH_MS = 50;

interface PendingDraftEvents {
  events: DraftEvent[];
  state: WebSocketDraftState | null;
  statePk: number | null;
  jump: boolean;
  tie: TieResolution | null;
  staleCaptains: number[];
}

let pending: PendingDraftEvents | null = null;
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function clearPending(): void {
  if (flushTimer !== null) clearTimeout(flushTimer);
  flushTimer = null;
  pending = null;
}

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
      staleTimeoutMs: 3000,
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

      if (message.type !== 'draft_event' && message.type !== 'ping') get().flushDraftEvents();

      if (message.type === 'initial_state') {
        if (message.draft_state) {
          log.debug('Updating draft state from initial_state');
          ingestDraftStateUsers(message.draft_state);
          set({
            draftState: hydrateSlimDraftState(message.draft_state),
            captainFresh: numericKeys(message.captain_fresh),
          });
        }
      } else if (message.type === 'initial_events' && message.events) {
        log.debug(`Received ${message.events.length} initial events`);
        set({ events: message.events });
      } else if (message.type === 'draft_event' && message.event) {
        const newEvent = message.event;
        log.debug('Received draft event:', newEvent.event_type);
        showEventToast(newEvent);

        const buf: PendingDraftEvents = pending ?? {
          events: [],
          state: null,
          statePk: null,
          jump: false,
          tie: null,
          staleCaptains: [],
        };
        pending = buf;
        buf.events.push(newEvent);
        if (newEvent.event_type === 'tie_roll') {
          const trPayload = newEvent.payload as TieRollPayload;
          buf.tie = {
            tied_teams: trPayload.tied_teams,
            roll_rounds: trPayload.roll_rounds,
            winner_id: trPayload.winner_id,
          };
        }
        if (
          newEvent.event_type === 'draft_paused' &&
          (newEvent.payload as DraftPausedPayload).reason === 'captain_disconnected'
        ) {
          buf.staleCaptains.push((newEvent.payload as DraftPausedPayload).captain_id);
        }
        // A state built for an older event never replaces a newer one.
        const lastPk = Math.max(buf.statePk ?? -Infinity, get()._lastStateEventPk ?? -Infinity);
        if (message.draft_state && newEvent.pk > lastPk) {
          buf.state = message.draft_state;
          buf.statePk = newEvent.pk;
          buf.jump ||= newEvent.event_type === 'pick_skipped' || newEvent.event_type === 'round_started';
        }
        if (flushTimer === null) {
          flushTimer = setTimeout(() => get().flushDraftEvents(), DRAFT_EVENT_FLUSH_MS);
        }
      } else if (message.type === 'draft_tick') {
        const parsed = DraftTickSchema.safeParse(message);
        if (!parsed.success) {
          log.warn('draft_tick_invalid', { issues: parsed.error.issues.length });
          return;
        }
        const tick = parsed.data;
        const receivedAtMs = Date.now();
        const lastAt = get()._lastTickReceivedAtMs;
        if (lastAt !== null && receivedAtMs - lastAt > 2000) {
          const gapMs = receivedAtMs - lastAt;
          log.warn('client_tick_gap', {
            draft_id: get()._currentDraftId,
            expected_gap_ms: 1000,
            actual_gap_ms: gapMs,
            stall_ms: gapMs - 1000,
          });
        }
        const fresh: Record<number, boolean> = {};
        for (const team of tick.teams) {
          if (team.captain_id != null) fresh[team.captain_id] = team.is_connected;
        }
        set((state) => ({
          tick,
          serverClockOffsetMs: captureClockOffset(tick.server_time, receivedAtMs),
          _lastTickReceivedAtMs: receivedAtMs,
          captainFresh: { ...state.captainFresh, ...fresh },
          ...(resumeEndedBy(tick, state.draftState)
            ? { draftState: { ...state.draftState!, state: 'drafting', resuming_until: null } }
            : {}),
        }));
      } else if (message.type === 'captain_heartbeat') {
        set((state) => ({ captainFresh: { ...state.captainFresh, [message.captain_id]: message.fresh } }));
      }
    });

    // Set status to 'connecting' immediately so the guard at the top of
    // connect() works during the WebSocketManager's 50ms StrictMode debounce.
    // Without this, status stays 'disconnected' and a StrictMode re-run
    // bypasses the guard, tears down the pending connection, and creates a new one.
    set({
      _connectionId: connectionId,
      _unsubscribe: unsubscribe,
      _currentDraftId: draftId,
      status: 'connecting',
    });
  },

  clearNewEventFlag: () => {
    set({ hasNewEvent: false });
  },

  setPendingTieResolution: (tr: TieResolution) => {
    set({ pendingTieResolution: tr });
  },

  clearPendingTieResolution: () => {
    set({ pendingTieResolution: null });
  },

  startHeartbeat: () => {
    if (get()._stopHeartbeat) return;
    const connectionId = get()._connectionId;
    if (!connectionId) {
      log.warn('Cannot start heartbeat: not connected');
      return;
    }
    const manager = getWebSocketManager();
    set({
      _stopHeartbeat: startHeartbeatLoop(() => {
        const cur = get()._connectionId;
        if (cur) manager.send(cur, { type: 'heartbeat' });
      }),
    });
  },

  stopHeartbeat: () => {
    const stop = get()._stopHeartbeat;
    if (stop) {
      stop();
      set({ _stopHeartbeat: null });
    }
  },

  jumpToPickNumber: (pickNumber: number) => {
    const round = get().draftState?.draft_rounds?.find((r) => r.pick_number === pickNumber);
    if (!round) return false;
    useUserStore.getState().setCurDraftRound(round as never);
    return true;
  },

  getServerNowISO: () => serverNowISO(get().serverClockOffsetMs),

  clearForceJump: () => set({ forceJumpToRoundPk: null }),

  flushDraftEvents: () => {
    const buf = pending;
    clearPending();
    if (!buf) return;
    if (buf.state) ingestDraftStateUsers(buf.state);
    set((state) => {
      const captainFresh = buf.staleCaptains.length
        ? { ...state.captainFresh, ...Object.fromEntries(buf.staleCaptains.map((id) => [id, false])) }
        : state.captainFresh;
      return {
        events: [...buf.events.slice().reverse(), ...state.events],
        lastEventTimestamp: Date.now(),
        hasNewEvent: true,
        captainFresh,
        ...(buf.tie ? { pendingTieResolution: buf.tie } : {}),
        ...(buf.state
          ? {
              draftState: hydrateSlimDraftState(buf.state),
              _lastStateEventPk: buf.statePk,
              ...(buf.jump ? { forceJumpToRoundPk: buf.state.latest_round } : {}),
            }
          : {}),
      };
    });
  },

  disconnect: () => {
    clearPending();
    get().stopHeartbeat();
    const { _unsubscribe } = get();

    // Unsubscribe only - manager auto-disconnects when no subscribers remain
    // (debounced to survive React StrictMode unmount/remount cycles)
    if (_unsubscribe) {
      _unsubscribe();
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

  /** True when draft is completed */
  isDraftCompleted: (s: DraftWebSocketState) => {
    if (s.draftState?.state) return s.draftState.state === 'completed';
    const rounds = s.draftState?.draft_rounds;
    return (
      s.draftState !== null &&
      (rounds?.length ?? 0) > 0 &&
      rounds?.every((r) => r.choice != null) === true
    );
  },

  draftStatus: (s: DraftWebSocketState): TeamDraftState | null => s.draftState?.state ?? null,

  timerEnabled: (s: DraftWebSocketState) => s.draftState?.draft_options?.timer_enabled === true,

  clockArmed: (s: DraftWebSocketState) => s.draftState?.clock_armed === true,

  // draftState.latest_round is authoritative; the tick lags each pick by up to 1 s.
  activeRoundPk: (s: DraftWebSocketState): number | null =>
    s.draftState ? (s.draftState.latest_round ?? null) : (s.tick?.active_round_pk ?? null),

  activeCaptainId: (s: DraftWebSocketState): number | null => {
    if (!s.draftState) return s.tick?.active_captain_id ?? null;
    const r = s.draftState.draft_rounds?.find((x) => x.pk === s.draftState!.latest_round);
    return (r?.captain as { pk?: number } | undefined)?.pk ?? null;
  },

  isMyTurn: (s: DraftWebSocketState, userPk: number | undefined) =>
    userPk != null && draftWsSelectors.activeCaptainId(s) === userPk,

  /** Heartbeat freshness, never Team.draft_is_connected. */
  isActiveCaptainDisconnected: (s: DraftWebSocketState) => {
    const id = draftWsSelectors.activeCaptainId(s);
    return id != null && s.captainFresh[id] === false;
  },

  teamTiming: (s: DraftWebSocketState) => s.tick?.teams ?? EMPTY_TEAMS,
};
