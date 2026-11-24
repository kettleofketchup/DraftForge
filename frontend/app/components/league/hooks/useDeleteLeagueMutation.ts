import { useMutation, useQueryClient } from '@tanstack/react-query';

import { deleteLeague } from '~/components/api/api';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import { organizationsQueryKey } from '~/components/organization/hooks/useOrganizations';
import { leagueKeys } from './leagueKeys';

export function useDeleteLeagueMutation(
  leagueId: number,
  organizationId?: number,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteLeague(leagueId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leagueKeys.all });
      queryClient.invalidateQueries({ queryKey: organizationsQueryKey });
      if (organizationId) {
        queryClient.invalidateQueries({
          queryKey: organizationQueryKey(organizationId),
        });
      }
      queryClient.removeQueries({ queryKey: ['league', leagueId] });
    },
  });
}
