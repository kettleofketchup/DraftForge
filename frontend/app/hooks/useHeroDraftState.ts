/**
 * useHeroDraftState - Migration helper hook for hero draft (ban/pick phase).
 *
 * This hook provides a unified API for accessing hero draft state during
 * the migration from useHeroDraftWebSocket to useHeroDraftStore.
 *
 * Note: This is different from useHeroDraft.ts which uses TanStack Query
 * for mutations. This hook focuses on real-time state via WebSocket.
 *
 * Usage:
 *   const { draft, tick, currentTeam, isMyTurn } = useHeroDraftState(draftId, currentUserId);
 *
 * After migration is complete (Phase 2D), components should use
 * useHeroDraftStore directly for more control.
 */

import { useEffect } from "react";
import { useHeroDraftStore } from "~/store/heroDraftStore";

interface UseHeroDraftStateOptions {
  /**
   * Whether to auto-connect when draftId is set.
   * @default true
   */
  autoConnect?: boolean;
}

export function useHeroDraftState(
  draftId: number | null | undefined,
  currentUserId?: number | null,
  options: UseHeroDraftStateOptions = {}
) {
  const { autoConnect = true } = options;

  const store = useHeroDraftStore();

  // Set draft ID (triggers WebSocket connection)
  useEffect(() => {
    if (autoConnect && draftId) {
      store.setDraftId(draftId);
    }
    return () => {
      // Cleanup on unmount
      if (draftId) {
        store.reset();
      }
    };
  }, [draftId, autoConnect]);

  // Computed values
  const currentTeam = store.getCurrentTeam();
  const otherTeam = store.getOtherTeam();
  const isMyTurn = currentUserId ? store.isMyTurn(currentUserId) : false;

  return {
    // Draft data
    draft: store.draft,
    tick: store.tick,
    events: store.events,

    // Teams
    currentTeam,
    otherTeam,
    isMyTurn,

    // Hero selection
    selectedHeroId: store.selectedHeroId,
    setSelectedHeroId: store.setSelectedHeroId,
    searchQuery: store.searchQuery,
    setSearchQuery: store.setSearchQuery,

    // Hero lists
    usedHeroIds: store.getUsedHeroIds(),
    bannedHeroIds: store.getBannedHeroIds(),
    getPickedHeroIds: store.getPickedHeroIds,

    // Loading/Error
    loading: store.loading,
    error: store.error,

    // WebSocket state
    wsState: store.wsState,
    isConnected: store.wsState === "connected",

    // Timer info from tick
    graceTimeRemaining: store.tick?.grace_time_remaining_ms ?? null,
    activeTeamId: store.tick?.active_team_id ?? null,

    // Reserve times
    getTeamReserveTime: (teamId: number) => {
      if (!store.tick) return null;
      if (teamId === store.tick.team_a_id) return store.tick.team_a_reserve_ms;
      if (teamId === store.tick.team_b_id) return store.tick.team_b_reserve_ms;
      return null;
    },

    // Actions
    refresh: store.loadDraft,
  };
}

/**
 * Hook for hero grid components (optimized for hero selection).
 */
export function useHeroDraftHeroSelection(draftId: number | null | undefined) {
  const store = useHeroDraftStore();

  // Minimal connection - just for reading state
  useEffect(() => {
    if (draftId && store.draftId !== draftId) {
      store.setDraftId(draftId);
    }
  }, [draftId]);

  return {
    selectedHeroId: store.selectedHeroId,
    setSelectedHeroId: store.setSelectedHeroId,
    searchQuery: store.searchQuery,
    setSearchQuery: store.setSearchQuery,
    usedHeroIds: store.getUsedHeroIds(),
    bannedHeroIds: store.getBannedHeroIds(),
    getPickedHeroIds: store.getPickedHeroIds,
  };
}

/**
 * Hook for timer display (optimized for tick updates).
 */
export function useHeroDraftTimer(draftId: number | null | undefined) {
  const store = useHeroDraftStore();

  // Minimal connection
  useEffect(() => {
    if (draftId && store.draftId !== draftId) {
      store.setDraftId(draftId);
    }
  }, [draftId]);

  const tick = store.tick;

  return {
    currentRound: tick?.current_round ?? null,
    activeTeamId: tick?.active_team_id ?? null,
    graceTimeRemaining: tick?.grace_time_remaining_ms ?? null,
    teamAReserve: tick?.team_a_reserve_ms ?? null,
    teamBReserve: tick?.team_b_reserve_ms ?? null,
    teamAId: tick?.team_a_id ?? null,
    teamBId: tick?.team_b_id ?? null,
    draftState: tick?.draft_state ?? null,
  };
}
