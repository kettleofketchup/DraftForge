import { useMutation, useQueryClient } from '@tanstack/react-query';

import { deleteLeague } from '~/components/api/api';
import { leagueKeys } from './leagueKeys';

export function useDeleteLeagueMutation(leagueId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteLeague(leagueId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leagueKeys.all });
      queryClient.removeQueries({ queryKey: ['league', leagueId] });
    },
  });
}
