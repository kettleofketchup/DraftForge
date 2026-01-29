/**
 * useTeamDraft - Migration helper hook for team draft (player picking).
 *
 * This hook provides a unified API for accessing team draft data during
 * the migration from useDraftWebSocket to useTeamDraftStore.
 *
 * Usage:
 *   const { draft, events, currentRound, wsState } = useTeamDraft(draftId, tournamentId);
 *
 * After migration is complete (Phase 2C), components should use
 * useTeamDraftStore directly for more control.
 */

import { useEffect } from "react";
import { useTeamDraftStore } from "~/store/teamDraftStore";

interface UseTeamDraftOptions {
  /**
   * Whether to auto-connect when draftId is set.
   * @default true
   */
  autoConnect?: boolean;
}

export function useTeamDraft(
  draftId: number | null | undefined,
  tournamentId: number | null | undefined,
  options: UseTeamDraftOptions = {}
) {
  const { autoConnect = true } = options;

  const store = useTeamDraftStore();

  // Set draft ID (triggers WebSocket connection and data load)
  useEffect(() => {
    if (autoConnect && draftId && tournamentId) {
      store.setDraftId(draftId, tournamentId);
    }
    return () => {
      // Cleanup on unmount
      if (draftId) {
        store.reset();
      }
    };
  }, [draftId, tournamentId, autoConnect]);

  return {
    // Draft data
    draft: store.draft,
    events: store.events,
    currentRound: store.getCurrentRound(),
    currentRoundIndex: store.currentRoundIndex,
    usersRemaining: store.getUsersRemaining(),

    // Tie resolution (for shuffle draft)
    tieResolution: store.tieResolution,
    clearTieResolution: store.clearTieResolution,

    // Loading/Error
    loading: store.loading,
    error: store.error,

    // WebSocket state
    wsState: store.wsState,
    isConnected: store.wsState === "connected",

    // UI feedback
    hasNewEvent: store.hasNewEvent,
    clearNewEvent: store.clearNewEvent,

    // Navigation
    nextRound: store.nextRound,
    previousRound: store.previousRound,
    setCurrentRoundIndex: store.setCurrentRoundIndex,

    // Actions
    refresh: store.loadDraft,
    refreshState: store.loadDraftState,
  };
}

/**
 * Hook for draft events only (optimized for event feed components).
 */
export function useTeamDraftEvents(
  draftId: number | null | undefined,
  tournamentId: number | null | undefined
) {
  const { events, hasNewEvent, clearNewEvent, wsState } = useTeamDraft(
    draftId,
    tournamentId
  );

  return { events, hasNewEvent, clearNewEvent, isConnected: wsState === "connected" };
}

/**
 * Hook for current round only (optimized for draft UI).
 */
export function useTeamDraftCurrentRound(
  draftId: number | null | undefined,
  tournamentId: number | null | undefined
) {
  const {
    currentRound,
    currentRoundIndex,
    usersRemaining,
    nextRound,
    previousRound,
    setCurrentRoundIndex,
    draft,
  } = useTeamDraft(draftId, tournamentId);

  const totalRounds = draft?.draft_rounds?.length ?? 0;
  const isFirstRound = currentRoundIndex === 0;
  const isLastRound = currentRoundIndex >= totalRounds - 1;

  return {
    currentRound,
    currentRoundIndex,
    totalRounds,
    usersRemaining,
    isFirstRound,
    isLastRound,
    nextRound,
    previousRound,
    setCurrentRoundIndex,
  };
}
