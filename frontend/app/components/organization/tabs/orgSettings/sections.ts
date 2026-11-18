import type { ComponentType } from 'react';
import type { OrganizationType } from '~/components/organization/schemas';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { StaffPlacementSection } from './StaffPlacementSection';

export interface OrgSettingsSection {
  id: string;
  Component: ComponentType<{ organizationId: number }>;
  useVisible: (org: OrganizationType | undefined) => boolean;
}

export const ORG_SETTINGS_SECTIONS: readonly OrgSettingsSection[] = [
  {
    id: 'staff-placement',
    Component: StaffPlacementSection,
    useVisible: useIsOrganizationAdmin,
  },
];
