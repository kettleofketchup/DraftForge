import { useCallback, useEffect } from 'react';
import { useUserStore } from '~/store/userStore';

export function useOrganizations() {
  const organizations = useUserStore((state) => state.organizations);
  const getOrganizations = useUserStore((state) => state.getOrganizations);

  const refetch = useCallback(() => {
    getOrganizations();
  }, [getOrganizations]);

  useEffect(() => {
    if (organizations.length === 0) {
      refetch();
    }
  }, [organizations.length, refetch]);

  return {
    organizations,
    isLoading: organizations.length === 0,
    refetch,
  };
}
