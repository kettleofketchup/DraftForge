import { ClipboardCheck, UserCog, type LucideIcon } from 'lucide-react';
import type { ReactNode, RefObject } from 'react';
import type { OrganizationType } from '~/components/organization/schemas';
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import type { SettingsFormUnit } from '~/components/patterns/settingsSaveBar';
import { useOrgFeatureAccess } from '~/features/org-features';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { useConductSection } from './ConductSection';
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
    sectionsRef: RefObject<SettingsDialogHandle<string> | null>,
  ) => { content: ReactNode; unit?: SettingsFormUnit };
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
    group: 'Organization',
    useSection: useStaffPlacementSection,
    useVisible: useIsOrganizationAdmin,
  },
  {
    id: 'conduct',
    label: 'Conduct',
    icon: ClipboardCheck,
    keywords: ['attendance', 'no-show', 'late cancel', 'enforcement'],
    group: 'Organization',
    useSection: useConductSection,
    useVisible: useCanManageConduct,
  },
];
