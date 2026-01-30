/**
 * League Store
 *
 * Zustand store for current league context.
 * Used to provide league context across components.
 */

import { create } from 'zustand';
import type { LeagueType } from '~/components/league/schemas';

interface LeagueState {
  /** Current league context */
  currentLeague: LeagueType | null;

  /** Actions */
  setCurrentLeague: (league: LeagueType | null) => void;
  reset: () => void;
}

export const useLeagueStore = create<LeagueState>((set) => ({
  currentLeague: null,

  setCurrentLeague: (league) => set({ currentLeague: league }),

  reset: () => set({ currentLeague: null }),
}));

// Selectors
export const leagueSelectors = {
  /** Get current league name */
  leagueName: (s: LeagueState) => s.currentLeague?.name ?? null,

  /** Get current league pk */
  leaguePk: (s: LeagueState) => s.currentLeague?.pk ?? null,

  /** Check if league is set */
  hasLeague: (s: LeagueState) => s.currentLeague !== null,
};
