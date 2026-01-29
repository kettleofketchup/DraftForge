/**
 * Team Draft Store - State management for team draft (player picking).
 *
 * This store manages the state for team draft sessions where captains
 * pick players to form teams. It uses WebSocket for real-time updates
 * and references useTournamentDataStore for user/team data.
 *
 * Data flow:
 * - HTTP provides initial draft state
 * - WebSocket provides real-time pick updates
 * - useTournamentDataStore is the source of truth for users/teams
 */

import { create } from "zustand";
import { fetchDraft, fetchTournamentDraftState } from "~/components/api/api";
import type { DraftType, DraftRoundType, TieResolution } from "~/components/draft/types.d";
import type { UserType } from "~/components/user";
import type { DraftEvent, WebSocketMessage } from "~/types/draftEvent";
import { WebSocketManager, type ConnectionState } from "~/lib/websocket";
import { getLogger } from "~/lib/logger";

const log = getLogger("teamDraftStore");

interface TeamDraftState {
  // Draft being viewed
  draftId: number | null;
  tournamentId: number | null;

  // Draft data
  draft: DraftType | null;
  currentRoundIndex: number;
  events: DraftEvent[];

  // Tie resolution state (for shuffle draft)
  tieResolution: TieResolution | null;

  // Loading/Error states
  loading: boolean;
  error: string | null;

  // WebSocket state
  wsState: ConnectionState;
  lastSequence: number;

  // UI feedback - indicates new event received (for visual notifications)
  hasNewEvent: boolean;

  // Actions
  setDraftId: (draftId: number | null, tournamentId: number | null) => void;
  loadDraft: () => Promise<void>;
  loadDraftState: () => Promise<void>;

  // Round navigation
  setCurrentRoundIndex: (index: number) => void;
  nextRound: () => void;
  previousRound: () => void;
  goToLatestRound: () => void;

  // Get current round
  getCurrentRound: () => DraftRoundType | null;
  getLatestRoundIndex: () => number;

  // Get users remaining to be picked
  getUsersRemaining: () => UserType[];

  // Update from WebSocket
  updateFromWebSocket: (message: unknown) => void;

  // Tie resolution
  setTieResolution: (tie: TieResolution | null) => void;
  clearTieResolution: () => void;

  // UI feedback
  clearNewEvent: () => void;

  // WebSocket management
  connectWebSocket: () => void;
  disconnectWebSocket: () => void;

  // Reset
  reset: () => void;

  // Internal state (not for external use)
  _wsUnsubscribe: (() => void) | null;
}

export const useTeamDraftStore = create<TeamDraftState>((set, get) => ({
  // Initial state
  draftId: null,
  tournamentId: null,
  draft: null,
  currentRoundIndex: 0,
  events: [],
  tieResolution: null,
  loading: false,
  error: null,
  wsState: "disconnected",
  lastSequence: 0,
  hasNewEvent: false,
  _wsUnsubscribe: null,

  // Set draft ID and connect
  setDraftId: (draftId, tournamentId) => {
    const currentId = get().draftId;
    if (currentId === draftId) return;

    // Disconnect from previous draft
    if (currentId !== null) {
      get().disconnectWebSocket();
    }

    // Reset state
    set({
      draftId,
      tournamentId,
      draft: null,
      currentRoundIndex: 0,
      events: [],
      tieResolution: null,
      loading: false,
      error: null,
      lastSequence: 0,
      hasNewEvent: false,
    });

    // Connect to new draft
    if (draftId !== null) {
      get().connectWebSocket();
      get().loadDraft();
    }
  },

  // Load full draft data
  loadDraft: async () => {
    const id = get().draftId;
    if (id === null) return;

    set({ loading: true, error: null });

    try {
      const data = await fetchDraft(id);
      const draft = data as DraftType;

      // RACE CONDITION FIX: If WebSocket has already sent events with draft_state,
      // don't overwrite with potentially stale HTTP data. WebSocket is authoritative
      // for real-time updates. Only use HTTP data if we haven't received WS updates yet.
      const state = get();
      if (state.lastSequence > 0 && state.draft !== null) {
        log.debug(`Skipping HTTP draft update - WebSocket already provided data (seq: ${state.lastSequence})`);
        set({ loading: false });
        return;
      }

      // Set current round to latest active round
      let roundIndex = 0;
      if (draft.draft_rounds && draft.latest_round !== null) {
        roundIndex = Math.max(0, (draft.latest_round ?? 1) - 1);
      }

      set({
        draft,
        currentRoundIndex: roundIndex,
        loading: false,
      });

      log.debug(`Loaded draft ${id}, current round: ${roundIndex + 1}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load draft";
      set({ loading: false, error: message });
      log.error(`Failed to load draft ${id}:`, err);
    }
  },

  // Load just draft state (for refresh)
  loadDraftState: async () => {
    const tournamentId = get().tournamentId;
    if (tournamentId === null) return;

    try {
      const data = await fetchTournamentDraftState(tournamentId);
      // Update draft state from lightweight endpoint
      const state = get();
      if (state.draft) {
        set({
          draft: { ...state.draft, ...(data as Partial<DraftType>) },
        });
      }
    } catch (err) {
      log.error("Failed to load draft state:", err);
    }
  },

  // Round navigation
  setCurrentRoundIndex: (index) => {
    const draft = get().draft;
    if (!draft?.draft_rounds) return;

    const maxIndex = draft.draft_rounds.length - 1;
    const clampedIndex = Math.max(0, Math.min(index, maxIndex));
    set({ currentRoundIndex: clampedIndex });
  },

  nextRound: () => {
    const state = get();
    state.setCurrentRoundIndex(state.currentRoundIndex + 1);
  },

  previousRound: () => {
    const state = get();
    state.setCurrentRoundIndex(state.currentRoundIndex - 1);
  },

  goToLatestRound: () => {
    const state = get();
    const latestIndex = state.getLatestRoundIndex();
    state.setCurrentRoundIndex(latestIndex);
  },

  // Get current round
  getCurrentRound: () => {
    const { draft, currentRoundIndex } = get();
    if (!draft?.draft_rounds || draft.draft_rounds.length === 0) return null;
    return draft.draft_rounds[currentRoundIndex] ?? null;
  },

  getLatestRoundIndex: () => {
    const { draft } = get();
    if (!draft?.draft_rounds || draft.draft_rounds.length === 0) return 0;
    if (draft.latest_round === null) return 0;

    // Find index of the latest round by pk
    const index = draft.draft_rounds.findIndex(r => r.pk === draft.latest_round);
    return index >= 0 ? index : Math.max(0, draft.draft_rounds.length - 1);
  },

  // Get users remaining
  getUsersRemaining: () => {
    const draft = get().draft;
    return draft?.users_remaining ?? [];
  },

  // Handle WebSocket message
  updateFromWebSocket: (message: unknown) => {
    if (typeof message !== "object" || message === null) return;

    const msg = message as WebSocketMessage;

    // Track sequence number
    if ("sequence" in msg && typeof msg.sequence === "number" && msg.sequence > 0) {
      const lastSeq = get().lastSequence;
      if (msg.sequence <= lastSeq) {
        log.warn(`Out-of-order message: got ${msg.sequence}, have ${lastSeq}`);
      }
      set({ lastSequence: msg.sequence });
    }

    if (msg.type === "initial_events" && msg.events) {
      set({ events: msg.events });
      log.debug(`Received ${msg.events.length} initial events`);
    } else if (msg.type === "draft_event" && msg.event) {
      const event = msg.event;

      // Add event to list (newest first) and mark as new
      set((state) => ({
        events: [event, ...state.events],
        hasNewEvent: true,
      }));

      // Update draft state if included
      // Note: Backend sends full DraftType but WebSocketMessage types it as WebSocketDraftState
      if (msg.draft_state) {
        const draft = msg.draft_state as unknown as DraftType;
        let roundIndex = get().currentRoundIndex;

        // Auto-advance to latest round on new pick
        if (draft.latest_round !== null && draft.draft_rounds) {
          roundIndex = Math.max(0, (draft.latest_round ?? 1) - 1);
        }

        set({
          draft,
          currentRoundIndex: roundIndex,
        });

        log.debug(`Updated draft state from WebSocket, round: ${roundIndex + 1}`);
      } else {
        // Fallback: reload draft data
        get().loadDraft();
      }

      // Handle tie resolution events
      if (event.event_type === "tie_roll") {
        const payload = event.payload as unknown as TieResolution;
        set({ tieResolution: payload });
      }
    }
  },

  // Tie resolution
  setTieResolution: (tie) => set({ tieResolution: tie }),
  clearTieResolution: () => set({ tieResolution: null }),

  // UI feedback
  clearNewEvent: () => set({ hasNewEvent: false }),

  // Connect WebSocket
  connectWebSocket: () => {
    const id = get().draftId;
    if (id === null) return;

    const channel = `draft/${id}`;

    const unsubscribe = WebSocketManager.subscribe(
      channel,
      (data) => get().updateFromWebSocket(data),
      (state) => set({ wsState: state })
    );

    set({ _wsUnsubscribe: unsubscribe });
    log.debug(`Subscribed to draft WebSocket: ${channel}`);
  },

  // Disconnect WebSocket
  disconnectWebSocket: () => {
    const unsubscribe = get()._wsUnsubscribe;
    if (unsubscribe) {
      unsubscribe();
      set({ _wsUnsubscribe: null, wsState: "disconnected" });
      log.debug("Unsubscribed from draft WebSocket");
    }
  },

  // Reset store
  reset: () => {
    get().disconnectWebSocket();
    set({
      draftId: null,
      tournamentId: null,
      draft: null,
      currentRoundIndex: 0,
      events: [],
      tieResolution: null,
      loading: false,
      error: null,
      wsState: "disconnected",
      lastSequence: 0,
      hasNewEvent: false,
      _wsUnsubscribe: null,
    });
  },
}));
