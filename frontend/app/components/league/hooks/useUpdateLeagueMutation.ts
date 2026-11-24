import { useMutation, useQueryClient } from '@tanstack/react-query';

import { updateLeague } from '~/components/api/api';
import type { LeagueType } from '~/components/league/schemas';
import { leagueKeys } from './leagueKeys';

// The detail page refreshes through the modal's onSuccess, since useLeague is not a query.
export function useUpdateLeagueMutation(leagueId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<LeagueType>) => updateLeague(leagueId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leagueKeys.all });
    },
  });
}
