import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { getOrganizations } from '~/components/api/api';

export const organizationsQueryKey = ['organizations'] as const;

export function useOrganizations() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: organizationsQueryKey,
    queryFn: getOrganizations,
  });

  const refetch = useCallback(
    () => queryClient.invalidateQueries({ queryKey: organizationsQueryKey }),
    [queryClient],
  );

  return { organizations: data ?? [], isLoading, refetch };
}
