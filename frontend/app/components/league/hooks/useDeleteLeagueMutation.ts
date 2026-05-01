import { useMutation, useQueryClient } from '@tanstack/react-query';

import { deleteLeague } from '~/components/api/api';
import { useUserStore } from '~/store/userStore';

export function useDeleteLeagueMutation(leagueId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteLeague(leagueId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leagues'] });
      queryClient.removeQueries({ queryKey: ['league', leagueId] });
      const { leagues } = useUserStore.getState();
      useUserStore.setState({
        leagues: leagues.filter((l) => l.pk !== leagueId),
        leaguesOrgId: null,
      });
    },
  });
}
