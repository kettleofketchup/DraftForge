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

import { useEffect, useMemo } from "react";
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

  // Subscribe to individual state slices for reactivity
  const draft = useTeamDraftStore((state) => state.draft);
  const events = useTeamDraftStore((state) => state.events);
  const currentRoundIndex = useTeamDraftStore((state) => state.currentRoundIndex);
  const tieResolution = useTeamDraftStore((state) => state.tieResolution);
  const loading = useTeamDraftStore((state) => state.loading);
  const error = useTeamDraftStore((state) => state.error);
  const wsState = useTeamDraftStore((state) => state.wsState);
  const hasNewEvent = useTeamDraftStore((state) => state.hasNewEvent);

  // Subscribe to actions
  const setDraftId = useTeamDraftStore((state) => state.setDraftId);
  const reset = useTeamDraftStore((state) => state.reset);
  const clearTieResolution = useTeamDraftStore((state) => state.clearTieResolution);
  const clearNewEvent = useTeamDraftStore((state) => state.clearNewEvent);
  const nextRound = useTeamDraftStore((state) => state.nextRound);
  const previousRound = useTeamDraftStore((state) => state.previousRound);
  const setCurrentRoundIndex = useTeamDraftStore((state) => state.setCurrentRoundIndex);
  const loadDraft = useTeamDraftStore((state) => state.loadDraft);
  const loadDraftState = useTeamDraftStore((state) => state.loadDraftState);

  // Derive current round from subscribed state (reactive)
  const currentRound = useMemo(() => {
    if (!draft?.draft_rounds || draft.draft_rounds.length === 0) return null;
    return draft.draft_rounds[currentRoundIndex] ?? null;
  }, [draft, currentRoundIndex]);

  // Derive users remaining from draft
  const usersRemaining = useMemo(() => {
    return draft?.users_remaining ?? [];
  }, [draft?.users_remaining]);

  // Set draft ID (triggers WebSocket connection and data load)
  useEffect(() => {
    if (autoConnect && draftId && tournamentId) {
      setDraftId(draftId, tournamentId);
    }
    return () => {
      // Cleanup on unmount
      if (draftId) {
        reset();
      }
    };
  }, [draftId, tournamentId, autoConnect, setDraftId, reset]);

  return {
    // Draft data
    draft,
    events,
    currentRound,
    currentRoundIndex,
    usersRemaining,

    // Tie resolution (for shuffle draft)
    tieResolution,
    clearTieResolution,

    // Loading/Error
    loading,
    error,

    // WebSocket state
    wsState,
    isConnected: wsState === "connected",

    // UI feedback
    hasNewEvent,
    clearNewEvent,

    // Navigation
    nextRound,
    previousRound,
    setCurrentRoundIndex,

    // Actions
    refresh: loadDraft,
    refreshState: loadDraftState,
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
