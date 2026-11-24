import { useQuery } from '@tanstack/react-query';
import { getLeagues } from '~/components/api/api';
import { leagueKeys } from './leagueKeys';

export function useLeagues(organizationId?: number) {
  const { data, isLoading, refetch } = useQuery({
    queryKey: leagueKeys.list(organizationId),
    queryFn: () => getLeagues(organizationId),
  });

  return { leagues: data ?? [], isLoading, refetch };
}
