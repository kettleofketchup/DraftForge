import { useCallback, useEffect } from 'react';
import { useUserStore } from '~/store/userStore';

export function useOrganization(pk: number | undefined) {
  const organization = useUserStore((state) => state.organization);
  const organizationPk = useUserStore((state) => state.organizationPk);
  const getOrganization = useUserStore((state) => state.getOrganization);

  const refetch = useCallback(() => {
    if (pk) {
      getOrganization(pk, true);
    }
  }, [pk, getOrganization]);

  useEffect(() => {
    // Only fetch if pk is set and we haven't loaded this org yet
    if (pk && organizationPk !== pk) {
      getOrganization(pk);
    }
  }, [pk, organizationPk, getOrganization]);

  return {
    organization: organizationPk === pk ? organization : null,
    isLoading: organizationPk !== pk,
    refetch,
  };
}
