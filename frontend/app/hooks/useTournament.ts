/**
 * useTournament - Migration helper hook for tournament data.
 *
 * This hook provides a unified API for accessing tournament data during
 * the migration from useUserStore to useTournamentDataStore.
 *
 * Usage:
 *   const { tournament, users, teams, loading, error } = useTournament(tournamentId);
 *
 * After migration is complete (Phase 2F), this hook can be simplified to
 * just use useTournamentDataStore directly.
 */

import { useEffect } from "react";
import { useTournamentDataStore } from "~/store/tournamentDataStore";
import { useUserStore } from "~/store/userStore";

interface UseTournamentOptions {
  /**
   * If true, use legacy useUserStore as fallback.
   * Set to false after component is fully migrated.
   * @default true
   */
  useLegacyFallback?: boolean;
}

export function useTournament(
  tournamentId: number | null | undefined,
  options: UseTournamentOptions = {}
) {
  const { useLegacyFallback = true } = options;

  // New store
  const newStore = useTournamentDataStore();

  // Legacy store (for fallback during migration)
  const legacyStore = useUserStore();

  // Set tournament ID in new store (triggers auto-load)
  useEffect(() => {
    if (tournamentId) {
      newStore.setTournamentId(tournamentId);
    }
    return () => {
      // Cleanup on unmount or ID change
      if (tournamentId) {
        newStore.reset();
      }
    };
  }, [tournamentId]);

  // Determine data source - prefer new store, fallback to legacy
  const hasNewData = newStore.users.length > 0 || newStore.teams.length > 0;
  const useLegacy = useLegacyFallback && !hasNewData && legacyStore.tournament;

  if (useLegacy) {
    // Use legacy store data
    return {
      // Data
      tournament: legacyStore.tournament,
      metadata: null,
      users: legacyStore.tournament?.users ?? [],
      teams: legacyStore.tournament?.teams ?? [],
      games: legacyStore.tournament?.games ?? [],

      // Loading/Error
      loading: false,
      error: null,

      // Helpers
      getUserById: (id: number) =>
        legacyStore.tournament?.users?.find((u) => u.pk === id),
      getTeamById: (id: number) =>
        legacyStore.tournament?.teams?.find((t) => t.pk === id),

      // Source indicator (for debugging)
      _source: "legacy" as const,
    };
  }

  // Use new store data
  return {
    // Data
    tournament: newStore.tournament,
    metadata: newStore.metadata,
    users: newStore.users,
    teams: newStore.teams,
    games: newStore.games,

    // Loading states
    loading: newStore.loading.full || newStore.loading.metadata,
    loadingUsers: newStore.loading.users,
    loadingTeams: newStore.loading.teams,
    loadingGames: newStore.loading.games,

    // Error states
    error: newStore.errors.full || newStore.errors.metadata,
    errorUsers: newStore.errors.users,
    errorTeams: newStore.errors.teams,
    errorGames: newStore.errors.games,

    // Helpers
    getUserById: newStore.getUserById,
    getTeamById: newStore.getTeamById,

    // Actions (for components that need to trigger reloads)
    refresh: newStore.loadAll,
    refreshUsers: newStore.loadUsers,
    refreshTeams: newStore.loadTeams,
    refreshGames: newStore.loadGames,

    // WebSocket state
    wsState: newStore.wsState,

    // Source indicator (for debugging)
    _source: "new" as const,
  };
}

/**
 * Selector hooks for optimized re-renders.
 * Use these when you only need specific data slices.
 */
export function useTournamentUsers(tournamentId: number | null | undefined) {
  const { users, loadingUsers, errorUsers, getUserById, refresh } =
    useTournament(tournamentId, { useLegacyFallback: false });

  return { users, loading: loadingUsers, error: errorUsers, getUserById, refresh };
}

export function useTournamentTeams(tournamentId: number | null | undefined) {
  const { teams, loadingTeams, errorTeams, getTeamById, refresh } =
    useTournament(tournamentId, { useLegacyFallback: false });

  return { teams, loading: loadingTeams, error: errorTeams, getTeamById, refresh };
}

export function useTournamentGames(tournamentId: number | null | undefined) {
  const { games, loadingGames, errorGames, refresh } = useTournament(
    tournamentId,
    { useLegacyFallback: false }
  );

  return { games, loading: loadingGames, error: errorGames, refresh };
}
