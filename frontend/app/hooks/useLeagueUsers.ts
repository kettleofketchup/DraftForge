import { useLeagueStore } from '~/store/leagueStore';
import type { UserEntry } from '~/store/userCacheTypes';

import { useResolvedUsers } from './useResolvedUsers';

/**
 * Get league users as UserEntry[] resolved from the cache.
 * Same unconditional-hook pattern as useOrgUsers.
 */
export function useLeagueUsers(leagueId: number): UserEntry[] {
  const pks = useLeagueStore((state) => state.leagueUserPks);
  const loadedLeagueId = useLeagueStore(
    (state) => state.leagueUsersLeagueId,
  );
  const users = useResolvedUsers(pks);

  if (loadedLeagueId !== leagueId) return [];
  return users;
}
