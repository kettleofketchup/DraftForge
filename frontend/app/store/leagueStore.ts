/**
 * League Store
 *
 * Zustand store for current league context.
 * Used to provide league context across components.
 */

import { create } from 'zustand';
import { fetchLeague, getLeagueUsers } from '~/components/api/api';
import type { LeagueType } from '~/components/league/schemas';
import type { UserType } from '~/components/user/types';
import { getLogger } from '~/lib/logger';
import { useUserCacheStore } from '~/store/userCacheStore';

// Bumped per request and on clear so a superseded response is dropped.
let leagueUsersRequest = 0;
// Response for leagueUsersLeagueId, kept so a later org id can be applied without a refetch.
let leagueUsersResponse: UserType[] | null = null;
// Org ids applied to (or queued for) the current league's users.
let leagueUsersOrgIds = new Set<number>();

function resetLeagueUsersScope(): void {
  leagueUsersRequest++;
  leagueUsersResponse = null;
  leagueUsersOrgIds = new Set();
}

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
  getLeagueUsers: (leagueId: number, orgId?: number) => Promise<void>;
  addLeagueUser: (leagueId: number, user: UserType) => void;
  removeLeagueUser: (leagueId: number, pk: number) => void;
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

  reset: () => {
    resetLeagueUsersScope();
    set({
      currentLeague: null,
      currentLeagueLoading: false,
      leagueUserPks: [],
      leagueUsersLoading: false,
      leagueUsersLeagueId: null,
      leagueUsersError: null,
    });
  },

  getLeagueUsers: async (leagueId: number, orgId?: number) => {
    const { leagueUsersLeagueId, leagueUsersLoading, leagueUserPks } = get();
    const sameLeague = leagueUsersLeagueId === leagueId;

    if (sameLeague && leagueUsersLoading) {
      if (orgId != null) leagueUsersOrgIds.add(orgId);
      return;
    }

    if (sameLeague && leagueUserPks.length > 0 && leagueUsersResponse) {
      if (orgId != null && !leagueUsersOrgIds.has(orgId)) {
        leagueUsersOrgIds.add(orgId);
        useUserCacheStore
          .getState()
          .upsert(leagueUsersResponse, { leagueId, orgId });
      }
      log.debug('LeagueUsers already loaded for league:', leagueId);
      return;
    }

    resetLeagueUsersScope();
    const request = leagueUsersRequest;
    if (orgId != null) leagueUsersOrgIds.add(orgId);
    set({
      leagueUsersLoading: true,
      leagueUsersError: null,
      leagueUsersLeagueId: leagueId,
      leagueUserPks: [],
    });

    try {
      const users = await getLeagueUsers(leagueId);
      if (request !== leagueUsersRequest) return;
      leagueUsersResponse = users;
      const cache = useUserCacheStore.getState();
      if (leagueUsersOrgIds.size === 0) cache.upsert(users, { leagueId });
      for (const id of leagueUsersOrgIds) {
        cache.upsert(users, { leagueId, orgId: id });
      }
      set({
        leagueUserPks: users.filter((u) => u.pk != null).map((u) => u.pk!),
        leagueUsersLoading: false,
      });
      log.debug('LeagueUsers fetched successfully:', users.length, 'users');
    } catch (error) {
      if (request !== leagueUsersRequest) return;
      log.error('Error fetching league users:', error);
      set({
        leagueUsersError:
          error instanceof Error
            ? error.message
            : 'Failed to fetch league users',
        leagueUsersLoading: false,
        leagueUserPks: [],
      });
    }
  },

  addLeagueUser: (leagueId: number, user: UserType) => {
    const cache = useUserCacheStore.getState();
    const loaded = get().leagueUsersLeagueId === leagueId;
    if (!loaded || leagueUsersOrgIds.size === 0) {
      cache.upsert(user, { leagueId });
    }
    if (!loaded || user.pk == null) return;
    for (const orgId of leagueUsersOrgIds) {
      cache.upsert(user, { leagueId, orgId });
    }
    if (leagueUsersResponse) {
      leagueUsersResponse = [
        ...leagueUsersResponse.filter((u) => u.pk !== user.pk),
        user,
      ];
    }
    const { leagueUserPks } = get();
    if (!leagueUserPks.includes(user.pk)) {
      set({ leagueUserPks: [...leagueUserPks, user.pk] });
    }
  },

  removeLeagueUser: (leagueId: number, pk: number) => {
    if (get().leagueUsersLeagueId !== leagueId) return;
    if (leagueUsersResponse) {
      leagueUsersResponse = leagueUsersResponse.filter((u) => u.pk !== pk);
    }
    set({ leagueUserPks: get().leagueUserPks.filter((p) => p !== pk) });
  },

  clearLeagueUsers: () => {
    resetLeagueUsersScope();
    set({
      leagueUserPks: [],
      leagueUsersLeagueId: null,
      leagueUsersError: null,
      leagueUsersLoading: false,
    });
  },
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
