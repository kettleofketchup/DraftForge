import { useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchOrganization } from '~/components/api/api';
import { useOrgStore } from '~/store/orgStore';

export const organizationQueryKey = (pk: number) => ['organization', pk] as const;

export function useOrganization(pk: number | undefined) {
  const queryClient = useQueryClient();

  const { data: organization, isLoading } = useQuery({
    queryKey: organizationQueryKey(pk!),
    queryFn: () => fetchOrganization(pk!),
    enabled: !!pk,
  });

  // Keep Zustand orgStore in sync so other consumers (AdminTeamSection, etc.) see live data
  useEffect(() => {
    if (organization) {
      useOrgStore.getState().setCurrentOrg(organization);
    }
  }, [organization]);

  const refetch = useCallback(() => {
    if (pk) {
      queryClient.invalidateQueries({ queryKey: organizationQueryKey(pk) });
    }
  }, [pk, queryClient]);

  return {
    organization: organization ?? null,
    isLoading,
    refetch,
  };
}
