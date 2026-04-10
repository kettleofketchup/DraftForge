import { useCallback, useEffect, useRef } from 'react';
import { useUserStore } from '~/store/userStore';

// Shared across all hook instances — prevents duplicate fetches
let fetchPromise: Promise<void> | null = null;

export function useOrganizations() {
  const organizations = useUserStore((state) => state.organizations);
  const getOrganizations = useUserStore((state) => state.getOrganizations);
  const fetched = useRef(false);

  const refetch = useCallback(async () => {
    fetchPromise = null;
    await getOrganizations();
  }, [getOrganizations]);

  useEffect(() => {
    if (organizations.length > 0 || fetched.current) return;
    fetched.current = true;

    if (!fetchPromise) {
      fetchPromise = getOrganizations();
    }
  }, [organizations.length, getOrganizations]);

  return {
    organizations,
    isLoading: organizations.length === 0 && !fetched.current,
    refetch,
  };
}
