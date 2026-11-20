import { ClipboardCheck, UserCog, type LucideIcon } from 'lucide-react';
import type { ComponentType } from 'react';
import type { OrganizationType } from '~/components/organization/schemas';
import { useOrgFeatureAccess } from '~/features/org-features';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { ConductSection } from './ConductSection';
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

export function useCanManageConduct(
  org: OrganizationType | undefined,
): boolean {
  return useOrgFeatureAccess(org).canManageConduct;
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
  {
    id: 'conduct',
    label: 'Conduct',
    icon: ClipboardCheck,
    keywords: ['attendance', 'no-show', 'late cancel', 'enforcement'],
    Component: ConductSection,
    useVisible: useCanManageConduct,
  },
];
