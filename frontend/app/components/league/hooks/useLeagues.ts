import { useCallback, useEffect, useMemo } from 'react';
import { useUserStore } from '~/store/userStore';

export function useLeagues(organizationId?: number) {
  const leagues = useUserStore((state) => state.leagues);
  const leaguesOrgId = useUserStore((state) => state.leaguesOrgId);
  const getLeagues = useUserStore((state) => state.getLeagues);

  const targetOrgId = organizationId ?? 'all';

  const refetch = useCallback(async () => {
    // Force refetch by resetting state
    useUserStore.setState({ leaguesOrgId: null });
    await getLeagues(organizationId);
  }, [getLeagues, organizationId]);

  useEffect(() => {
    // Only fetch if we haven't loaded leagues for this org
    if (leaguesOrgId !== targetOrgId) {
      getLeagues(organizationId);
    }
  }, [targetOrgId, leaguesOrgId, getLeagues, organizationId]);

  // Filter to ensure we only show leagues for the current org
  const filteredLeagues = useMemo(
    () =>
      organizationId
        ? leagues.filter((l) => l.organization?.pk === organizationId)
        : leagues,
    [leagues, organizationId],
  );

  // Loading if we haven't fetched for this org yet
  const isLoading = leaguesOrgId !== targetOrgId;

  return {
    leagues: filteredLeagues,
    isLoading,
    refetch,
  };
}
