/**
 * League Store
 *
 * Zustand store for current league context.
 * Used to provide league context across components.
 */

import { create } from 'zustand';
import { fetchLeague, getLeagueUsers } from '~/components/api/api';
import type { LeagueType } from '~/components/league/schemas';
import { getLogger } from '~/lib/logger';
import { useUserCacheStore } from '~/store/userCacheStore';

const log = getLogger('leagueStore');

interface LeagueState {
  /** Current league context */
  currentLeague: LeagueType | null;
  currentLeagueLoading: boolean;

  /** League user pks (resolved via useLeagueUsers hook) */
  leagueUserPks: number[];
  leagueUsersLoading: boolean;
  leagueUsersError: string | null;
  leagueUsersLeagueId: number | null;

  /** Actions */
  setCurrentLeague: (league: LeagueType | null) => void;
  getLeague: (leaguePk: number) => Promise<void>;
  reset: () => void;

  /** League Users Actions */
  getLeagueUsers: (leagueId: number) => Promise<void>;
  clearLeagueUsers: () => void;
}

export const useLeagueStore = create<LeagueState>((set, get) => ({
  currentLeague: null,
  currentLeagueLoading: false,
  leagueUserPks: [],
  leagueUsersLoading: false,
  leagueUsersError: null,
  leagueUsersLeagueId: null,

  setCurrentLeague: (league) => set({ currentLeague: league }),

  getLeague: async (leaguePk: number) => {
    // Skip if already loaded for this league
    if (get().currentLeague?.pk === leaguePk) {
      log.debug('League already loaded:', leaguePk);
      return;
    }

    set({ currentLeagueLoading: true });

    try {
      const league = await fetchLeague(leaguePk);
      set({ currentLeague: league, currentLeagueLoading: false });
      log.debug('League fetched successfully:', league.name);
    } catch (error) {
      log.error('Error fetching league:', error);
      set({ currentLeague: null, currentLeagueLoading: false });
    }
  },

  reset: () =>
    set({
      currentLeague: null,
      currentLeagueLoading: false,
      leagueUserPks: [],
      leagueUsersLoading: false,
      leagueUsersLeagueId: null,
      leagueUsersError: null,
    }),

  getLeagueUsers: async (leagueId: number) => {
    // Skip if already loaded for this league
    if (get().leagueUsersLeagueId === leagueId && get().leagueUserPks.length > 0) {
      log.debug('LeagueUsers already loaded for league:', leagueId);
      return;
    }

    set({ leagueUsersLoading: true, leagueUsersError: null, leagueUsersLeagueId: leagueId, leagueUserPks: [] });

    try {
      const users = await getLeagueUsers(leagueId);
      useUserCacheStore.getState().upsert(users, { leagueId });
      set({
        leagueUserPks: users.filter((u) => u.pk != null).map((u) => u.pk!),
        leagueUsersLoading: false,
      });
      log.debug('LeagueUsers fetched successfully:', users.length, 'users');
    } catch (error) {
      log.error('Error fetching league users:', error);
      set({
        leagueUsersError:
          error instanceof Error ? error.message : 'Failed to fetch league users',
        leagueUsersLoading: false,
        leagueUserPks: [],
      });
    }
  },

  clearLeagueUsers: () =>
    set({ leagueUserPks: [], leagueUsersLeagueId: null, leagueUsersError: null }),
}));

// Selectors
export const leagueSelectors = {
  /** Get current league name */
  leagueName: (s: LeagueState) => s.currentLeague?.name ?? null,

  /** Get current league pk */
  leaguePk: (s: LeagueState) => s.currentLeague?.pk ?? null,

  /** Check if league is set */
  hasLeague: (s: LeagueState) => s.currentLeague !== null,

  /** Check if league is loading */
  isLoading: (s: LeagueState) => s.currentLeagueLoading,

  /** Check if league users are loading */
  isLoadingLeagueUsers: (s: LeagueState) => s.leagueUsersLoading,
};
