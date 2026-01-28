/**
 * Tournament Data Store - Source of truth for tournament, users, and teams.
 *
 * This store manages the authoritative state for tournament-related data.
 * Other stores (useTeamDraftStore, useBracketStore) should reference this
 * data rather than maintaining their own copies.
 *
 * Data flow:
 * - HTTP endpoints provide initial/refreshed data
 * - WebSocket provides real-time updates
 * - This store is the single source of truth
 */

import { create } from "zustand";
import {
  fetchTournament,
  fetchTournamentMetadata,
  fetchTournamentUsers,
  fetchTournamentTeams,
  fetchTournamentGames,
} from "~/components/api/api";
import type { TournamentType, TeamType } from "~/components/tournament/types";
import type { UserType } from "~/components/user";
import type { GameType } from "~/components/game/types";
import { WebSocketManager, type ConnectionState } from "~/lib/websocket";
import { getLogger } from "~/lib/logger";

const log = getLogger("tournamentDataStore");

// Loading states for progressive loading
interface LoadingState {
  metadata: boolean;
  users: boolean;
  teams: boolean;
  games: boolean;
  full: boolean;
}

// Error states
interface ErrorState {
  metadata: string | null;
  users: string | null;
  teams: string | null;
  games: string | null;
  full: string | null;
}

// Lightweight tournament metadata (from /metadata/ endpoint)
interface TournamentMetadata {
  pk: number;
  name: string;
  state: string;
  date_played: string;
  timezone: string;
  tournament_type: string;
  winning_team: number | null;
  draft_id: number | null;
  bracket_exists: boolean;
  user_count: number;
  team_count: number;
  league_id: number | null;
  league_name: string | null;
}

interface TournamentDataState {
  // Current tournament ID being viewed
  tournamentId: number | null;

  // Data - users/teams are arrays, metadata is lightweight object
  metadata: TournamentMetadata | null;
  users: UserType[];
  teams: TeamType[];
  games: GameType[];

  // Full tournament (legacy - for components that need the full object)
  tournament: TournamentType | null;

  // Loading states
  loading: LoadingState;

  // Error states
  errors: ErrorState;

  // WebSocket connection state
  wsState: ConnectionState;

  // Last sequence number received via WebSocket
  lastSequence: number;

  // Actions
  setTournamentId: (id: number | null) => void;
  loadMetadata: () => Promise<void>;
  loadUsers: () => Promise<void>;
  loadTeams: () => Promise<void>;
  loadGames: () => Promise<void>;
  loadFull: () => Promise<void>;
  loadAll: () => Promise<void>;

  // Update actions (for WebSocket updates)
  updateMetadata: (metadata: Partial<TournamentMetadata>) => void;
  updateUsers: (users: UserType[]) => void;
  updateTeams: (teams: TeamType[]) => void;
  updateGames: (games: GameType[]) => void;
  updateFromWebSocket: (data: unknown) => void;

  // User helpers
  getUserById: (id: number) => UserType | undefined;
  getTeamById: (id: number) => TeamType | undefined;

  // WebSocket management
  connectWebSocket: () => void;
  disconnectWebSocket: () => void;

  // Cleanup
  reset: () => void;
}

// Initial states
const initialLoadingState: LoadingState = {
  metadata: false,
  users: false,
  teams: false,
  games: false,
  full: false,
};

const initialErrorState: ErrorState = {
  metadata: null,
  users: null,
  teams: null,
  games: null,
  full: null,
};

// WebSocket unsubscribe function holder
let wsUnsubscribe: (() => void) | null = null;

export const useTournamentDataStore = create<TournamentDataState>((set, get) => ({
  // Initial state
  tournamentId: null,
  metadata: null,
  users: [],
  teams: [],
  games: [],
  tournament: null,
  loading: { ...initialLoadingState },
  errors: { ...initialErrorState },
  wsState: "disconnected",
  lastSequence: 0,

  // Set tournament ID and trigger initial load
  setTournamentId: (id) => {
    const currentId = get().tournamentId;
    if (currentId === id) return;

    // Disconnect from previous tournament's WebSocket
    if (currentId !== null) {
      get().disconnectWebSocket();
    }

    // Reset state
    set({
      tournamentId: id,
      metadata: null,
      users: [],
      teams: [],
      games: [],
      tournament: null,
      loading: { ...initialLoadingState },
      errors: { ...initialErrorState },
      lastSequence: 0,
    });

    // Connect to new tournament's WebSocket
    if (id !== null) {
      get().connectWebSocket();
    }
  },

  // Load lightweight metadata
  loadMetadata: async () => {
    const id = get().tournamentId;
    if (id === null) return;

    set((state) => ({
      loading: { ...state.loading, metadata: true },
      errors: { ...state.errors, metadata: null },
    }));

    try {
      const data = await fetchTournamentMetadata(id);
      set((state) => ({
        metadata: data as TournamentMetadata,
        loading: { ...state.loading, metadata: false },
      }));
      log.debug(`Loaded metadata for tournament ${id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load metadata";
      set((state) => ({
        loading: { ...state.loading, metadata: false },
        errors: { ...state.errors, metadata: message },
      }));
      log.error(`Failed to load metadata for tournament ${id}:`, err);
    }
  },

  // Load users
  loadUsers: async () => {
    const id = get().tournamentId;
    if (id === null) return;

    set((state) => ({
      loading: { ...state.loading, users: true },
      errors: { ...state.errors, users: null },
    }));

    try {
      const data = await fetchTournamentUsers(id);
      set((state) => ({
        users: data as UserType[],
        loading: { ...state.loading, users: false },
      }));
      log.debug(`Loaded ${data.length} users for tournament ${id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load users";
      set((state) => ({
        loading: { ...state.loading, users: false },
        errors: { ...state.errors, users: message },
      }));
      log.error(`Failed to load users for tournament ${id}:`, err);
    }
  },

  // Load teams
  loadTeams: async () => {
    const id = get().tournamentId;
    if (id === null) return;

    set((state) => ({
      loading: { ...state.loading, teams: true },
      errors: { ...state.errors, teams: null },
    }));

    try {
      const data = await fetchTournamentTeams(id);
      set((state) => ({
        teams: data as TeamType[],
        loading: { ...state.loading, teams: false },
      }));
      log.debug(`Loaded ${data.length} teams for tournament ${id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load teams";
      set((state) => ({
        loading: { ...state.loading, teams: false },
        errors: { ...state.errors, teams: message },
      }));
      log.error(`Failed to load teams for tournament ${id}:`, err);
    }
  },

  // Load games
  loadGames: async () => {
    const id = get().tournamentId;
    if (id === null) return;

    set((state) => ({
      loading: { ...state.loading, games: true },
      errors: { ...state.errors, games: null },
    }));

    try {
      const data = await fetchTournamentGames(id);
      set((state) => ({
        games: data as GameType[],
        loading: { ...state.loading, games: false },
      }));
      log.debug(`Loaded ${data.length} games for tournament ${id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load games";
      set((state) => ({
        loading: { ...state.loading, games: false },
        errors: { ...state.errors, games: message },
      }));
      log.error(`Failed to load games for tournament ${id}:`, err);
    }
  },

  // Load full tournament (legacy, for backward compatibility)
  loadFull: async () => {
    const id = get().tournamentId;
    if (id === null) return;

    set((state) => ({
      loading: { ...state.loading, full: true },
      errors: { ...state.errors, full: null },
    }));

    try {
      const data = await fetchTournament(id);
      set((state) => ({
        tournament: data as TournamentType,
        // Also populate arrays from full tournament data
        users: data.users ?? state.users,
        teams: data.teams ?? state.teams,
        games: data.games ?? state.games,
        loading: { ...state.loading, full: false },
      }));
      log.debug(`Loaded full tournament ${id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load tournament";
      set((state) => ({
        loading: { ...state.loading, full: false },
        errors: { ...state.errors, full: message },
      }));
      log.error(`Failed to load tournament ${id}:`, err);
    }
  },

  // Load all data progressively
  loadAll: async () => {
    const state = get();

    // Load metadata first (fast)
    await state.loadMetadata();

    // Then load users and teams in parallel
    await Promise.all([state.loadUsers(), state.loadTeams()]);

    // Finally load games (can be larger)
    await state.loadGames();
  },

  // Update metadata (partial update)
  updateMetadata: (metadata) => {
    set((state) => ({
      metadata: state.metadata ? { ...state.metadata, ...metadata } : null,
    }));
  },

  // Update users
  updateUsers: (users) => {
    set({ users });
  },

  // Update teams
  updateTeams: (teams) => {
    set({ teams });
  },

  // Update games
  updateGames: (games) => {
    set({ games });
  },

  // Handle WebSocket message
  updateFromWebSocket: (data: unknown) => {
    // Type guard for WebSocket messages
    if (typeof data !== "object" || data === null) return;

    const message = data as Record<string, unknown>;

    // Track sequence number
    if (typeof message.sequence === "number" && message.sequence > 0) {
      const lastSeq = get().lastSequence;
      if (message.sequence <= lastSeq) {
        log.warn(`Out-of-order WebSocket message: got ${message.sequence}, have ${lastSeq}`);
        // Still process it - the backend data is authoritative
      }
      set({ lastSequence: message.sequence });
    }

    // Handle different message types
    if (message.type === "draft_event" && message.draft_state) {
      // Draft state update - trigger refresh of tournament data
      log.debug("Received draft_event, refreshing tournament data");
      get().loadFull();
    }
  },

  // Get user by ID
  getUserById: (id) => {
    return get().users.find((u) => u.pk === id);
  },

  // Get team by ID
  getTeamById: (id) => {
    return get().teams.find((t) => t.pk === id);
  },

  // Connect to tournament WebSocket
  connectWebSocket: () => {
    const id = get().tournamentId;
    if (id === null) return;

    const channel = `tournament/${id}`;

    wsUnsubscribe = WebSocketManager.subscribe(
      channel,
      (data) => get().updateFromWebSocket(data),
      (state) => set({ wsState: state })
    );

    log.debug(`Subscribed to WebSocket channel: ${channel}`);
  },

  // Disconnect from WebSocket
  disconnectWebSocket: () => {
    if (wsUnsubscribe) {
      wsUnsubscribe();
      wsUnsubscribe = null;
      set({ wsState: "disconnected" });
      log.debug("Unsubscribed from tournament WebSocket");
    }
  },

  // Reset store to initial state
  reset: () => {
    get().disconnectWebSocket();
    set({
      tournamentId: null,
      metadata: null,
      users: [],
      teams: [],
      games: [],
      tournament: null,
      loading: { ...initialLoadingState },
      errors: { ...initialErrorState },
      wsState: "disconnected",
      lastSequence: 0,
    });
  },
}));
