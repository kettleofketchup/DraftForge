import { useMutation, useQueryClient } from '@tanstack/react-query';

import { createLeague } from '~/components/api/api';
import type { CreateLeagueInput } from '~/components/league/schemas';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import { organizationsQueryKey } from '~/components/organization/hooks/useOrganizations';
import { leagueKeys } from './leagueKeys';

export function useCreateLeagueMutation(organizationId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateLeagueInput) =>
      createLeague({ ...data, organization_id: organizationId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leagueKeys.all });
      queryClient.invalidateQueries({ queryKey: organizationsQueryKey });
      queryClient.invalidateQueries({
        queryKey: organizationQueryKey(organizationId),
      });
    },
  });
}
