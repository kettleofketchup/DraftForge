import { useCallback, useEffect, useState } from 'react';
import { useUserStore } from '~/store/userStore';

export function useOrganizations() {
  const organizations = useUserStore((state) => state.organizations);
  const getOrganizations = useUserStore((state) => state.getOrganizations);
  const [isLoading, setIsLoading] = useState(true);
  const [hasFetched, setHasFetched] = useState(false);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    try {
      await getOrganizations();
    } finally {
      setIsLoading(false);
      setHasFetched(true);
    }
  }, [getOrganizations]);

  useEffect(() => {
    if (!hasFetched) {
      refetch();
    }
  }, [hasFetched, refetch]);

  return {
    organizations,
    isLoading,
    refetch,
  };
}
