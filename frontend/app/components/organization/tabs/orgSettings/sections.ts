import type { ComponentType } from 'react';
import type { OrganizationType } from '~/components/organization/schemas';
import { useOrgFeatureAccess } from '~/features/org-features';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { ConductSection } from './ConductSection';
import { StaffPlacementSection } from './StaffPlacementSection';

export interface OrgSettingsSection {
  id: string;
  Component: ComponentType<{ organizationId: number }>;
  useVisible: (org: OrganizationType | undefined) => boolean;
}

export function useCanManageConduct(
  org: OrganizationType | undefined,
): boolean {
  return useOrgFeatureAccess(org).canManageConduct;
}

export const ORG_SETTINGS_SECTIONS: readonly OrgSettingsSection[] = [
  {
    id: 'staff-placement',
    Component: StaffPlacementSection,
    useVisible: useIsOrganizationAdmin,
  },
  {
    id: 'conduct',
    Component: ConductSection,
    useVisible: useCanManageConduct,
  },
];
