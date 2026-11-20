import { useQueryClient } from '@tanstack/react-query';
import { ShieldCheck } from 'lucide-react';
import { useRef } from 'react';
import { AdminTeamSection } from '~/components/admin-team';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import type { OrganizationType } from '~/components/organization/schemas';
import {
  SettingsPage,
  type SettingsDialogHandle,
  type SettingsSection,
} from '~/components/patterns/SettingsDialog';
import {
  useSettingsSaveBar,
  type SettingsFormUnit,
} from '~/components/patterns/settingsSaveBar';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { ORG_SETTINGS_SECTIONS } from './orgSettings/sections';
import { useOrgProfileSections } from './orgSettings/useOrgProfileSections';
import { useOrgSettingsAccess } from './orgSettings/useOrgSettingsAccess';

/**
 * Every organization setting on one page: the organization's own fields
 * (formerly the Edit Organization dialog), its admin team, then the
 * registered settings sections, behind a searchable sidebar.
 */
export function OrgSettingsTab({
  organization,
}: {
  organization: OrganizationType;
}) {
  const sectionsRef = useRef<SettingsDialogHandle<string>>(null);
  const isOrgAdmin = useIsOrganizationAdmin(organization);
  const { visibleSectionIds } = useOrgSettingsAccess(organization);
  const queryClient = useQueryClient();
  const profile = useOrgProfileSections(organization, sectionsRef);
  const registry = ORG_SETTINGS_SECTIONS.map((s) => ({
    section: s,
    ...s.useSection(
      organization.pk ?? 0,
      organization.pk != null && visibleSectionIds.includes(s.id),
    ),
  }));
  const units: SettingsFormUnit[] = [
    ...(isOrgAdmin ? [profile.unit] : []),
    ...registry.flatMap((r) => (r.unit ? [r.unit] : [])),
  ];
  const { saveBar } = useSettingsSaveBar(units, {
    testIdPrefix: 'org-profile',
  });

  const pk = organization.pk;
  const sections: SettingsSection[] =
    pk == null
      ? []
      : [
          ...(isOrgAdmin ? profile.sections : []),
          ...(isOrgAdmin
            ? [
                {
                  value: 'admins',
                  label: 'Admin Team',
                  icon: ShieldCheck,
                  keywords: ['owner', 'admin', 'staff', 'promoter', 'roles'],
                  lazy: true,
                  content: (
                    <AdminTeamSection
                      organization={organization}
                      onUpdate={() =>
                        queryClient.invalidateQueries({
                          queryKey: organizationQueryKey(pk),
                        })
                      }
                    />
                  ),
                },
              ]
            : []),
          ...registry
            .filter((r) => visibleSectionIds.includes(r.section.id))
            .map(({ section: { id, label, icon, keywords }, content }) => ({
              value: id,
              label,
              icon,
              keywords,
              content,
            })),
        ];

  if (sections.length === 0) {
    return <div data-testid="org-settings-tab" />;
  }

  return (
    <SettingsPage
      sections={sections}
      testIdPrefix="org-settings"
      sectionRef={sectionsRef}
      footer={saveBar}
      data-testid="org-settings-tab"
    />
  );
}
