import { useCallback, useEffect, useMemo, useState } from 'react';
import { useUserStore } from '~/store/userStore';

export function useLeagues(organizationId?: number) {
  const leagues = useUserStore((state) => state.leagues);
  const getLeagues = useUserStore((state) => state.getLeagues);
  const [isLoading, setIsLoading] = useState(true);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    try {
      await getLeagues(organizationId);
    } finally {
      setIsLoading(false);
    }
  }, [getLeagues, organizationId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  // Filter to ensure we only show leagues for the current org
  const filteredLeagues = useMemo(
    () =>
      organizationId
        ? leagues.filter((l) => l.organization === organizationId)
        : leagues,
    [leagues, organizationId],
  );

  return {
    leagues: filteredLeagues,
    isLoading,
    refetch,
  };
}
