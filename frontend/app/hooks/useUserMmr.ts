import { useMemo } from 'react';

import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';

/**
 * Get a single user's org and league MMR from the cache.
 * For single-user views (profile, detail). NOT for list contexts —
 * in lists, pass orgId/leagueId as props and read user.orgData directly.
 */
export function useUserMmr(
  pk: number,
): { orgMmr?: number; leagueMmr?: number } {
  const user = useUserCacheStore((state) => state.entities[pk]);
  const orgId = useOrgStore((state) => state.currentOrg?.pk);
  const leagueId = useLeagueStore((state) => state.currentLeague?.pk);

  return useMemo(
    () => ({
      orgMmr: orgId ? user?.orgData[orgId]?.mmr : undefined,
      leagueMmr: leagueId
        ? user?.leagueData[leagueId]?.mmr
        : undefined,
    }),
    [user, orgId, leagueId],
  );
}
