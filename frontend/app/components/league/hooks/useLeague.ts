import { useCallback, useEffect, useState } from 'react';
import { fetchLeague } from '~/components/api/api';
import type { LeagueType } from '../schemas';

export function useLeague(pk: number | undefined) {
  const [league, setLeague] = useState<LeagueType | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(() => {
    if (pk) {
      setIsLoading(true);
      setError(null);
      fetchLeague(pk)
        .then(setLeague)
        .catch(setError)
        .finally(() => setIsLoading(false));
    }
  }, [pk]);

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
