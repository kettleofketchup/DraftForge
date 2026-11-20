import { useEffect } from 'react';
import type { OrganizationType } from '~/components/organization/schemas';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { useUserStore } from '~/store/userStore';
import { ORG_SETTINGS_SECTIONS } from './sections';

export interface OrgSettingsAccess {
  settled: boolean;
  /** Org admins and above, once the org payload matches the current viewer. */
  canOpen: boolean;
  visibleSectionIds: string[];
}

export function useOrgSettingsAccess(
  org: OrganizationType | undefined,
): OrgSettingsAccess {
  const viewerPk = useUserStore((s) => s.currentUser?.pk ?? null);
  const isOrgAdmin = useIsOrganizationAdmin(org);
  const settled =
    org?.members_viewer_pk !== undefined && org.members_viewer_pk === viewerPk;
  const visibility = ORG_SETTINGS_SECTIONS.map((section) => ({
    id: section.id,
    visible: section.useVisible(org),
  }));
  const visibleSectionIds = settled
    ? visibility.filter((s) => s.visible).map((s) => s.id)
    : [];
  return {
    settled,
    canOpen: settled && isOrgAdmin,
    visibleSectionIds,
  };
}

export function useSettingsTabRedirect(
  activeTab: string,
  setActiveTab: (tab: string) => void,
  access: Pick<OrgSettingsAccess, 'canOpen' | 'settled'>,
): void {
  const { canOpen, settled } = access;
  useEffect(() => {
    if (activeTab === 'settings' && settled && !canOpen) {
      setActiveTab('leagues');
    }
  }, [activeTab, settled, canOpen, setActiveTab]);
}
