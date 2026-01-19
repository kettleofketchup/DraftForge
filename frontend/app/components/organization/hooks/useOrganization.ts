import { useCallback, useEffect } from 'react';
import { useUserStore } from '~/store/userStore';

export function useOrganization(pk: number | undefined) {
  const organization = useUserStore((state) => state.organization);
  const getOrganization = useUserStore((state) => state.getOrganization);

  const refetch = useCallback(() => {
    if (pk) {
      getOrganization(pk);
    }
  }, [pk, getOrganization]);

  useEffect(() => {
    if (pk && (!organization || organization.pk !== pk)) {
      refetch();
    }
  }, [pk, organization, refetch]);

  return {
    organization: organization?.pk === pk ? organization : null,
    isLoading: !organization || organization.pk !== pk,
    refetch,
  };
}
