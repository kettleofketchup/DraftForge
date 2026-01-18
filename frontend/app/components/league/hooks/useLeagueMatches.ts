import { useCallback, useEffect, useState } from 'react';
import { getLeagueMatches } from '~/components/api/api';
import type { LeagueMatchType } from '../schemas';

interface UseLeagueMatchesOptions {
  tournament?: number;
  linkedOnly?: boolean;
}

export function useLeagueMatches(leaguePk: number | null, options?: UseLeagueMatchesOptions) {
  const [matches, setMatches] = useState<LeagueMatchType[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchMatches = useCallback(async () => {
    if (!leaguePk) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await getLeagueMatches(leaguePk, options);
      setMatches(data);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to fetch matches'));
    } finally {
      setIsLoading(false);
    }
  }, [leaguePk, options?.tournament, options?.linkedOnly]);

  useEffect(() => {
    fetchMatches();
  }, [fetchMatches]);

  return { matches, isLoading, error, refetch: fetchMatches };
}
