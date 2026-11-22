import { create } from 'zustand';
import {
  addPending,
  applyChatAck,
  applyChatError,
  applyChatHistory,
  applyChatMessage,
  initialChatState,
  resetChatOnDisconnect,
  type ChatState,
} from '~/components/herodraft/chat/chatState';
import { parseChatInput } from '~/components/herodraft/chat/parseChatInput';
import { HeroDraftWebSocketMessageSchema } from '~/components/herodraft/schemas';
import type {
  DraftTeam,
  HeroDraft,
  HeroDraftEvent,
  HeroDraftTick,
} from '~/components/herodraft/types';
import type { UserType } from '~/components/user/types';
import {
  addClockOffsetSample,
  seedClockOffset,
  serverNowISO,
  startHeartbeatLoop,
} from '~/lib/draftClock';
import { getLogger } from '~/lib/logger';
import type { ConnectionStatus, Unsubscribe } from '~/lib/websocket';
import { getWebSocketManager } from '~/lib/websocket';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';

const log = getLogger('heroDraftStore');
const chatLog = getLogger('herodraft:chat');

export type HeroSuggestionKind = 'suggest_pick' | 'suggest_ban';

function ingestDraftUsers(draft: HeroDraft): void {
  const users = draft.draft_teams.flatMap((t) => [
    ...(t.captain ? [t.captain] : []),
    ...t.members,
  ]);
  if (users.length === 0) return;
  const orgId = draft.organization_pk ?? undefined;
  useUserCacheStore
    .getState()
    .upsert(users as UserType[], orgId ? { orgId } : undefined);
}

const DEBUG = false;
const debugLog = (...args: unknown[]) => {
  if (DEBUG) {
    console.log('[HeroDraft]', ...args);
  }
};

interface HeroDraftState {
  status: ConnectionStatus;
  error: string | null;
  reconnectAttempts: number;
  wasKicked: boolean;

  draft: HeroDraft | null;
  tick: HeroDraftTick | null;
  // Server minus local clock; 0 until the first tick. Used for outbound timestamps.
  serverClockOffsetMs: number;
  selectedHeroId: number | null;
  searchQuery: string;
  lastEvent: HeroDraftEvent | null;
  chat: ChatState;
  /** Pixels of the hero grid's bottom covered by the open desktop chat panel. */
  chatPanelInset: number;

  _connectionId: string | null;
  _unsubscribe: Unsubscribe | null;
  _currentDraftId: number | null;
  // Survives disconnect so a same-draft reconnect keeps its chat.
  _chatDraftId: number | null;
  _stopHeartbeat: (() => void) | null;
  // Client-side tick gap detection; complements the server's `tick_loop_stalled`.
  _lastTickReceivedAtMs: number | null;
  _offsetSamples: number[];

  connect: (draftId: number) => void;
  disconnect: () => void;
  reconnect: () => void;
  startHeartbeat: () => void;
  stopHeartbeat: () => void;
  setSelectedHeroId: (heroId: number | null) => void;
  setSearchQuery: (query: string) => void;
  sendChat: (raw: string) => string | null;
  suggestHero: (kind: HeroSuggestionKind, heroId: number) => string | null;
  unsuggestHero: (kind: HeroSuggestionKind, heroId: number) => string | null;
  setChatPanelOpen: (open: boolean) => void;
  setChatPanelInset: (px: number) => void;
  clearChatError: () => void;
  reset: () => void;

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
  chat: initialChatState,
  chatPanelInset: 0,
  _connectionId: null,
  _unsubscribe: null,
  _currentDraftId: null,
  _chatDraftId: null,
  _stopHeartbeat: null,
  _lastTickReceivedAtMs: null,
  _offsetSamples: [] as number[],
};

export const useHeroDraftStore = create<HeroDraftState>((set, get) => ({
  ...initialState,

  connect: (draftId: number) => {
    const current = get();

    if (
      current._currentDraftId === draftId &&
      current.status !== 'disconnected'
    ) {
      log.debug('Already connected to same draft, skipping');
      return;
    }

    if (
      current._currentDraftId !== null &&
      current._currentDraftId !== draftId
    ) {
      log.debug(
        `Switching from draft ${current._currentDraftId} to ${draftId}`,
      );
      get().disconnect();
    }

    if (current._unsubscribe) {
      current._unsubscribe();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/api/herodraft/${draftId}/`;

    log.debug(`Connecting to HeroDraft WebSocket: ${url}`);

    const manager = getWebSocketManager();

    const connectionId = manager.connect(url, {
      onStateChange: (state) => {
        const prev = get();
        const lostConnection =
          prev.status === 'connected' && state.status !== 'connected';
        if (lostConnection && Object.keys(prev.chat.pending).length > 0) {
          chatLog.warn('chat_pending_lost_on_disconnect', {
            draft_id: draftId,
            pending: Object.keys(prev.chat.pending).length,
          });
        }
        set({
          status: state.status,
          error: state.error,
          reconnectAttempts: state.reconnectAttempts,
          ...(lostConnection ? { chat: resetChatOnDisconnect(prev.chat) } : {}),
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
          log.debug(
            `Reconnecting to ${connUrl}, attempt ${attempt}, backoff ${backoffMs}ms`,
          );
        },
        onStaleDetected: (connUrl, staleDurationMs) => {
          log.warn(
            `Stale connection: ${connUrl} (${staleDurationMs}ms without messages)`,
          );
        },
      },
    });

    const unsubscribe = manager.subscribe(connectionId, (rawMessage) => {
      const parseResult = HeroDraftWebSocketMessageSchema.safeParse(rawMessage);
      if (!parseResult.success) {
        log.warn('Invalid WebSocket message format:', parseResult.error.issues);
        debugLog(
          'Raw message that failed validation:',
          JSON.stringify(rawMessage, null, 2),
        );
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
          {
            const clock = seedClockOffset(
              get()._offsetSamples,
              message.server_time,
              Date.now(),
            );
            ingestDraftUsers(message.draft_state);
            set({
              draft: message.draft_state,
              _offsetSamples: clock.samples,
              serverClockOffsetMs: clock.offsetMs,
            });
          }
          break;

        case 'herodraft_event':
          debugLog('herodraft_event received', {
            event_type: message.event_type,
            draft_team_id: message.draft_team?.id,
            has_draft_state: !!message.draft_state,
          });

          if (message.draft_state) {
            debugLog(
              'Updating draft state:',
              message.draft_state.state,
              'current_round:',
              message.draft_state.current_round,
            );
            ingestDraftUsers(message.draft_state);
            set({ draft: message.draft_state });
          }

          // Patch the tick with the new round now; the next tick is up to 1s away
          // and the timer would linger on the previous team until then.
          if (message.event_type === 'hero_selected') {
            const prevTick = get().tick;
            const newDraft = message.draft_state;
            const newRoundIdx = newDraft?.current_round ?? null;
            const newRound =
              newRoundIdx !== null && newDraft?.rounds
                ? (newDraft.rounds[newRoundIdx] ?? null)
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

        case 'herodraft_tick': {
          debugLog('herodraft_tick received', {
            draft_state: message.draft_state,
            current_round: message.current_round,
            active_team_id: message.active_team_id,
            server_time: message.server_time,
            round_started_at: message.round_started_at,
          });

          // Offset from the least-delayed recent tick, so one tick stuck in a
          // queue can't shift this viewer's clock by its delay.
          const tickReceivedAtMs = Date.now();
          const clock = addClockOffsetSample(
            get()._offsetSamples,
            message.server_time,
            tickReceivedAtMs,
          );

          // Ticks are 1Hz; a >2s gap is a delivery problem the server can't see.
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
            _offsetSamples: clock.samples,
            serverClockOffsetMs: clock.offsetMs,
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
              timer_enabled: message.timer_enabled,
            },
          });
          break;
        }

        case 'herodraft_kicked': {
          log.warn('Kicked from draft:', message.reason);
          get().stopHeartbeat();
          // Disconnect ourselves so the manager doesn't auto-reconnect.
          const kickedConnId = get()._connectionId;
          const kickedUnsub = get()._unsubscribe;
          if (kickedUnsub) kickedUnsub();
          if (kickedConnId) {
            manager.disconnect(kickedConnId, 'Kicked by server');
          }
          // Keep wasKicked; `status` is the disconnected signal (isConnected is derived).
          set({
            _connectionId: null,
            _unsubscribe: null,
            wasKicked: true,
            error: 'Connection replaced by new tab',
            status: 'disconnected',
            chat: resetChatOnDisconnect(get().chat),
          });
          break;
        }

        case 'chat_history':
          set({
            chat: applyChatHistory(
              get().chat,
              message.viewer,
              message.messages,
              chatSelfId(),
            ),
          });
          break;

        case 'chat_message':
          set({
            chat: applyChatMessage(get().chat, message.message, chatSelfId()),
          });
          break;

        case 'chat_ack':
          if (message.client_msg_id !== undefined) {
            set({ chat: applyChatAck(get().chat, message.client_msg_id) });
          }
          break;

        case 'chat_error':
          chatLog.info('chat_rejected', {
            draft_id: get()._currentDraftId,
            code: message.code,
          });
          set({
            chat: applyChatError(
              get().chat,
              message.code,
              message.client_msg_id,
              message.viewer,
            ),
          });
          break;
      }
    });

    // 'connecting' now, so connect()'s guard holds during the manager's 50ms debounce.
    set({
      _connectionId: connectionId,
      _unsubscribe: unsubscribe,
      _currentDraftId: draftId,
      _chatDraftId: draftId,
      ...(get()._chatDraftId === draftId ? {} : { chat: initialChatState }),
      wasKicked: false,
      status: 'connecting',
    });
  },

  disconnect: () => {
    const { _connectionId, _unsubscribe, _chatDraftId, chat } = get();

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
      _chatDraftId,
      chat: resetChatOnDisconnect(chat),
    });
  },

  reconnect: () => {
    const { _currentDraftId, wasKicked } = get();
    // A kicked tab reconnecting would kick the other tab, forever.
    if (wasKicked) {
      log.warn('Reconnect blocked: was kicked from this draft');
      return;
    }
    if (_currentDraftId) {
      get().disconnect();
      setTimeout(() => {
        get().connect(_currentDraftId);
      }, 100);
    }
  },

  startHeartbeat: () => {
    if (get()._stopHeartbeat) return;
    if (!get()._connectionId) {
      log.warn('Cannot start heartbeat: not connected');
      return;
    }

    log.debug('Starting captain heartbeat');
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

  setSelectedHeroId: (heroId) => set({ selectedHeroId: heroId }),
  setSearchQuery: (query) => set({ searchQuery: query }),

  sendChat: (raw) => {
    if (parseChatInput(raw).body === '') return null;
    return sendChatFrame(raw, { type: 'chat_send', body: raw });
  },

  suggestHero: (kind, heroId) =>
    sendChatFrame('', { type: 'chat_suggest', kind, hero_id: heroId }),

  unsuggestHero: (kind, heroId) =>
    sendChatFrame('', { type: 'chat_unsuggest', kind, hero_id: heroId }),

  setChatPanelOpen: (open) => {
    const { chat } = get();
    set({
      chat: { ...chat, panelOpen: open, unread: open ? 0 : chat.unread },
    });
  },

  setChatPanelInset: (px) => {
    if (get().chatPanelInset !== px) set({ chatPanelInset: px });
  },

  clearChatError: () => set({ chat: { ...get().chat, lastError: null } }),

  reset: () => {
    get().disconnect();
    set({ chat: initialChatState, chatPanelInset: 0, _chatDraftId: null });
  },

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

function chatSelfId(): number | undefined {
  return useUserStore.getState().currentUser?.pk ?? undefined;
}

function sendChatFrame(
  raw: string,
  frame:
    | { type: 'chat_send'; body: string }
    | {
        type: 'chat_suggest' | 'chat_unsuggest';
        kind: HeroSuggestionKind;
        hero_id: number;
      },
): string | null {
  const { _connectionId, _currentDraftId, status, chat } =
    useHeroDraftStore.getState();
  if (!_connectionId || status !== 'connected') return null;
  const clientMsgId = crypto.randomUUID();
  const sent = getWebSocketManager().send(_connectionId, {
    ...frame,
    client_msg_id: clientMsgId,
  });
  if (!sent) {
    chatLog.warn('chat_send_refused', {
      draft_id: _currentDraftId,
      type: frame.type,
    });
    return null;
  }
  useHeroDraftStore.setState({
    chat: {
      ...addPending(chat, { clientMsgId, raw, sentAt: Date.now() }),
      lastError: null,
    },
  });
  return clientMsgId;
}

export const heroDraftSelectors = {
  isLoading: (s: HeroDraftState) =>
    s.status === 'connecting' || s.status === 'reconnecting',

  isConnected: (s: HeroDraftState) => s.status === 'connected',

  isActive: (s: HeroDraftState) =>
    s.draft?.state === 'drafting' || s.draft?.state === 'choosing',

  isCompleted: (s: HeroDraftState) => s.draft?.state === 'completed',

  isWaiting: (s: HeroDraftState) => s.draft?.state === 'waiting_for_captains',

  isPaused: (s: HeroDraftState) => s.draft?.state === 'paused',

  /** The 3-2-1 countdown before a resume. */
  isResuming: (s: HeroDraftState) => s.draft?.state === 'resuming',

  isMyTurn: (s: HeroDraftState, currentUserId: number | undefined) => {
    if (!currentUserId) return false;
    if (s.draft?.state !== 'drafting') return false;

    const activeTeamId =
      s.tick?.active_team_id ??
      (s.draft.current_round !== null
        ? s.draft.rounds[s.draft.current_round]?.draft_team
        : null);

    if (!activeTeamId) return false;

    const myTeam = s.draft.draft_teams.find(
      (t) =>
        t.captain?.pk === currentUserId ||
        t.members?.some((m) => m.pk === currentUserId),
    );

    return myTeam?.id === activeTeamId;
  },

  currentAction: (s: HeroDraftState) => {
    if (!s.draft || s.draft.current_round === null) return null;
    return s.draft.rounds[s.draft.current_round]?.action_type ?? null;
  },
};

/** Server-clock now, for timestamps the server compares to its own clock (e.g. `client_picked_at`). Local clock before the first tick. */
export function getServerNowISO(): string {
  return serverNowISO(useHeroDraftStore.getState().serverClockOffsetMs);
}
