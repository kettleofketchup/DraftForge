import {
  ClipboardCheck,
  Crown,
  KeyRound,
  UserCog,
  type LucideIcon,
} from 'lucide-react';
import type { ReactNode, RefObject } from 'react';
import type { OrganizationType } from '~/components/organization/schemas';
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import type { SettingsFormUnit } from '~/components/patterns/settingsSaveBar';
import { leadershipAccess } from '~/features/leadership/access';
import { useOrgFeatureAccess } from '~/features/org-features';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { useApiAccessSection } from './ApiAccessSection';
import { useConductSection } from './ConductSection';
import { useLeadershipSection } from './LeadershipSection';
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

export function useCanManageLeadership(
  org: OrganizationType | undefined,
): boolean {
  return leadershipAccess(useOrgFeatureAccess(org)).canManage;
}

export function useCanUseMmrSync(org: OrganizationType | undefined): boolean {
  return useOrgFeatureAccess(org).canUseMmrSync;
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
    keywords: [
      'attendance',
      'no-show',
      'late cancel',
      'enforcement',
      'show rate',
    ],
    group: 'Organization',
    useSection: useConductSection,
    useVisible: useCanManageConduct,
  },
  {
    id: 'leadership',
    label: 'Leadership',
    icon: Crown,
    keywords: ['captain', 'traits', 'review window', 'rating', 'points'],
    group: 'Organization',
    useSection: useLeadershipSection,
    useVisible: useCanManageLeadership,
  },
  {
    id: 'api-access',
    label: 'API access',
    icon: KeyRound,
    keywords: ['api', 'token', 'mmr', 'sync', 'rate limit'],
    group: 'Organization',
    useSection: useApiAccessSection,
    useVisible: useCanUseMmrSync,
  },
];
