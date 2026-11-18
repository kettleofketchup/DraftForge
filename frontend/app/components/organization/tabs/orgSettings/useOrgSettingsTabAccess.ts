import { useEffect } from 'react';
import type { OrganizationType } from '~/components/organization/schemas';
import { useUserStore } from '~/store/userStore';
import { ORG_SETTINGS_SECTIONS } from './sections';

export interface OrgSettingsTabAccess {
  canView: boolean;
  settled: boolean;
  visibleSectionIds: string[];
}

export function useOrgSettingsTabAccess(
  org: OrganizationType | undefined,
): OrgSettingsTabAccess {
  const viewerPk = useUserStore((s) => s.currentUser?.pk ?? null);
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
    canView: settled && visibleSectionIds.length > 0,
    visibleSectionIds,
  };
}

export function useSettingsTabRedirect(
  activeTab: string,
  setActiveTab: (tab: string) => void,
  access: Pick<OrgSettingsTabAccess, 'canView' | 'settled'>,
): void {
  const { canView, settled } = access;
  useEffect(() => {
    if (activeTab === 'settings' && settled && !canView) {
      setActiveTab('leagues');
    }
  }, [activeTab, settled, canView, setActiveTab]);
}
