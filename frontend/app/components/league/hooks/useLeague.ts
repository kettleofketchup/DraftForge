import { useCallback, useEffect, useState } from 'react';
import { fetchLeague } from '~/components/api/api';
import { useLeagueStore } from '~/store/leagueStore';
import type { LeagueType } from '../schemas';

export function useLeague(pk: number | undefined) {
  const [league, setLeague] = useState<LeagueType | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(
    (opts?: { silent?: boolean }) => {
      if (pk) {
        if (!opts?.silent) setIsLoading(true);
        setError(null);
        fetchLeague(pk)
          .then((data) => {
            // Before the page renders it, so its names resolve against the league's org.
            useLeagueStore.getState().setCurrentLeague(data);
            setLeague(data);
          })
          .catch(setError)
          .finally(() => setIsLoading(false));
      }
    },
    [pk],
  );

  useEffect(() => {
    refetch();
  }, [refetch]);

  return {
    league,
    isLoading,
    error,
    refetch,
  };
}
