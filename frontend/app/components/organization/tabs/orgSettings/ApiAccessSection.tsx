import type { ReactNode } from 'react';

import { useOrganization } from '~/components/organization/hooks/useOrganization';
import { ApiAccessPanel } from '~/features/api-tokens';
import { useOrgFeatureAccess } from '~/features/org-features';

export function useApiAccessSection(
  organizationId: number,
  enabled: boolean,
): { content: ReactNode } {
  const { organization } = useOrganization(
    enabled ? organizationId : undefined,
  );
  const access = useOrgFeatureAccess(organization ?? undefined);
  return {
    content: (
      <ApiAccessPanel
        orgId={organizationId}
        access={access}
        enabled={enabled}
      />
    ),
  };
}
