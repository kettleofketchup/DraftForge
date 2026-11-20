import { UserCog, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import type { OrganizationType } from '~/components/organization/schemas';
import type { SettingsFormUnit } from '~/components/patterns/settingsSaveBar';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { useStaffPlacementSection } from './StaffPlacementSection';

export interface OrgSettingsSection {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Extra search terms for the settings sidebar. */
  keywords?: string[];
  group: string;
  useSection: (
    organizationId: number,
    enabled: boolean,
  ) => { content: ReactNode; unit?: SettingsFormUnit };
  useVisible: (org: OrganizationType | undefined) => boolean;
}

export const ORG_SETTINGS_SECTIONS: readonly OrgSettingsSection[] = [
  {
    id: 'staff-placement',
    label: 'Staff placement',
    icon: UserCog,
    keywords: ['staff', 'override', 'policy', 'codes'],
    group: 'Organization',
    useSection: useStaffPlacementSection,
    useVisible: useIsOrganizationAdmin,
  },
];
