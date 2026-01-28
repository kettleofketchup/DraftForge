/**
 * Hero Draft Store - State management for Captain's Mode hero draft.
 *
 * This store manages the state for hero draft sessions (ban/pick phase).
 * It uses WebSocket for real-time updates including tick (timer) messages.
 *
 * Enhanced with:
 * - WebSocketManager integration for connection management
 * - Loading/error states
 * - Sequence tracking for message ordering
 * - Event history
 */

import { create } from "zustand";
import type { HeroDraft, HeroDraftTick, DraftTeam, HeroDraftEvent } from "~/components/herodraft/types";
import { HeroDraftWebSocketMessageSchema } from "~/components/herodraft/schemas";
import { WebSocketManager, type ConnectionState } from "~/lib/websocket";
import { getLogger } from "~/lib/logger";

const log = getLogger("heroDraftStore");

// API endpoint for fetching hero draft
async function fetchHeroDraft(draftId: number): Promise<HeroDraft> {
  const response = await fetch(`/api/herodraft/${draftId}/`);
  if (!response.ok) {
    throw new Error(`Failed to fetch hero draft: ${response.statusText}`);
  }
  return response.json();
}

interface HeroDraftState {
  // Draft being viewed
  draftId: number | null;

  // Draft data
  draft: HeroDraft | null;
  tick: HeroDraftTick | null;
  events: HeroDraftEvent[];

  // UI state
  selectedHeroId: number | null;
  searchQuery: string;

  // Loading/Error states
  loading: boolean;
  error: string | null;

  // WebSocket state
  wsState: ConnectionState;
  lastSequence: number;

  // Actions
  setDraftId: (draftId: number | null) => void;
  loadDraft: () => Promise<void>;
  setDraft: (draft: HeroDraft) => void;
  setTick: (tick: HeroDraftTick) => void;
  setSelectedHeroId: (heroId: number | null) => void;
  setSearchQuery: (query: string) => void;

  // Update from WebSocket
  updateFromWebSocket: (message: unknown) => void;

  // WebSocket management
  connectWebSocket: () => void;
  disconnectWebSocket: () => void;

  // Computed helpers
  getCurrentTeam: () => DraftTeam | null;
  getOtherTeam: () => DraftTeam | null;
  isMyTurn: (userId: number) => boolean;
  getUsedHeroIds: () => number[];
  getBannedHeroIds: () => number[];
  getPickedHeroIds: (teamId: number) => number[];

  // Reset
  reset: () => void;

  // Internal state (not for external use)
  _wsUnsubscribe: (() => void) | null;
}

export const useHeroDraftStore = create<HeroDraftState>((set, get) => ({
  // Initial state
  draftId: null,
  draft: null,
  tick: null,
  events: [],
  selectedHeroId: null,
  searchQuery: "",
  loading: false,
  error: null,
  wsState: "disconnected",
  lastSequence: 0,
  _wsUnsubscribe: null,

  // Set draft ID and connect
  setDraftId: (draftId) => {
    const currentId = get().draftId;
    if (currentId === draftId) return;

    // Disconnect from previous draft
    if (currentId !== null) {
      get().disconnectWebSocket();
    }

    // Reset state
    set({
      draftId,
      draft: null,
      tick: null,
      events: [],
      selectedHeroId: null,
      searchQuery: "",
      loading: false,
      error: null,
      lastSequence: 0,
    });

    // Connect to new draft
    if (draftId !== null) {
      get().connectWebSocket();
    }
  },

  // Load draft via HTTP
  loadDraft: async () => {
    const id = get().draftId;
    if (id === null) return;

    set({ loading: true, error: null });

    try {
      const draft = await fetchHeroDraft(id);
      set({ draft, loading: false });
      log.debug(`Loaded hero draft ${id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load draft";
      set({ loading: false, error: message });
      log.error(`Failed to load hero draft ${id}:`, err);
    }
  },

  // Direct setters
  setDraft: (draft) => set({ draft }),
  setTick: (tick) => set({ tick }),
  setSelectedHeroId: (heroId) => set({ selectedHeroId: heroId }),
  setSearchQuery: (query) => set({ searchQuery: query }),

  // Handle WebSocket message
  updateFromWebSocket: (message: unknown) => {
    if (typeof message !== "object" || message === null) return;

    // Parse with Zod for type safety
    const parseResult = HeroDraftWebSocketMessageSchema.safeParse(message);
    if (!parseResult.success) {
      log.warn("Invalid WebSocket message:", parseResult.error.issues);
      return;
    }

    const data = parseResult.data;

    // Track sequence number
    if ("sequence" in data && typeof data.sequence === "number" && data.sequence > 0) {
      const lastSeq = get().lastSequence;
      if (data.sequence <= lastSeq) {
        log.warn(`Out-of-order message: got ${data.sequence}, have ${lastSeq}`);
      }
      set({ lastSequence: data.sequence });
    }

    switch (data.type) {
      case "initial_state":
        set({ draft: data.draft_state });
        log.debug("Received initial state");
        break;

      case "herodraft_event":
        // Update draft state if included
        if (data.draft_state) {
          set({ draft: data.draft_state });
        }

        // Add event to history
        if (data.event_type) {
          const event: HeroDraftEvent = {
            type: data.type,
            event_type: data.event_type,
            event_id: data.event_id,
            draft_team: data.draft_team,
            timestamp: data.timestamp,
            metadata: data.metadata,
          };
          set((state) => ({
            events: [event, ...state.events.slice(0, 99)], // Keep last 100 events
          }));
        }

        log.debug(`Received event: ${data.event_type}`);
        break;

      case "herodraft_tick":
        // NOTE: data.draft_state in tick messages is a string enum (e.g., "drafting"),
        // NOT a full HeroDraft object. Do NOT set draft from tick messages.
        set({
          tick: {
            type: "herodraft_tick",
            current_round: data.current_round,
            active_team_id: data.active_team_id,
            grace_time_remaining_ms: data.grace_time_remaining_ms,
            team_a_id: data.team_a_id,
            team_a_reserve_ms: data.team_a_reserve_ms,
            team_b_id: data.team_b_id,
            team_b_reserve_ms: data.team_b_reserve_ms,
            draft_state: data.draft_state,
          },
        });
        break;
    }
  },

  // Connect WebSocket
  connectWebSocket: () => {
    const id = get().draftId;
    if (id === null) return;

    const channel = `herodraft/${id}`;

    const unsubscribe = WebSocketManager.subscribe(
      channel,
      (data) => get().updateFromWebSocket(data),
      (state) => set({ wsState: state })
    );

    set({ _wsUnsubscribe: unsubscribe });
    log.debug(`Subscribed to herodraft WebSocket: ${channel}`);
  },

  // Disconnect WebSocket
  disconnectWebSocket: () => {
    const unsubscribe = get()._wsUnsubscribe;
    if (unsubscribe) {
      unsubscribe();
      set({ _wsUnsubscribe: null, wsState: "disconnected" });
      log.debug("Unsubscribed from herodraft WebSocket");
    }
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

  getBannedHeroIds: () => {
    const { draft } = get();
    if (!draft) return [];
    return draft.rounds
      .filter((r) => r.action_type === "ban" && r.hero_id !== null)
      .map((r) => r.hero_id as number);
  },

  getPickedHeroIds: (teamId: number) => {
    const { draft } = get();
    if (!draft) return [];
    return draft.rounds
      .filter((r) => r.action_type === "pick" && r.hero_id !== null && r.draft_team_id === teamId)
      .map((r) => r.hero_id as number);
  },

  // Reset
  reset: () => {
    get().disconnectWebSocket();
    set({
      draftId: null,
      draft: null,
      tick: null,
      events: [],
      selectedHeroId: null,
      searchQuery: "",
      loading: false,
      error: null,
      wsState: "disconnected",
      lastSequence: 0,
      _wsUnsubscribe: null,
    });
  },
}));
