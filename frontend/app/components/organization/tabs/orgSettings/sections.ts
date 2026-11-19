import { UserCog, type LucideIcon } from 'lucide-react';
import type { ComponentType } from 'react';
import type { OrganizationType } from '~/components/organization/schemas';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { StaffPlacementSection } from './StaffPlacementSection';

export interface OrgSettingsSection {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Extra search terms for the settings sidebar. */
  keywords?: string[];
  Component: ComponentType<{ organizationId: number }>;
  useVisible: (org: OrganizationType | undefined) => boolean;
}

export const ORG_SETTINGS_SECTIONS: readonly OrgSettingsSection[] = [
  {
    id: 'staff-placement',
    label: 'Staff placement',
    icon: UserCog,
    keywords: ['staff', 'override', 'policy', 'codes'],
    Component: StaffPlacementSection,
    useVisible: useIsOrganizationAdmin,
  },
];
