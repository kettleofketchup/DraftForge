/**
 * League Store
 *
 * Zustand store for current league context.
 * Used to provide league context across components.
 */

import { create } from 'zustand';
import { fetchLeague } from '~/components/api/api';
import type { LeagueType } from '~/components/league/schemas';
import { getLogger } from '~/lib/logger';

const log = getLogger('leagueStore');

interface LeagueState {
  /** Current league context */
  currentLeague: LeagueType | null;
  currentLeagueLoading: boolean;

  /** Actions */
  setCurrentLeague: (league: LeagueType | null) => void;
  getLeague: (leaguePk: number) => Promise<void>;
  reset: () => void;
}

export const useLeagueStore = create<LeagueState>((set, get) => ({
  currentLeague: null,
  currentLeagueLoading: false,

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
    }),
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
};
