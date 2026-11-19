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
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { ORG_SETTINGS_SECTIONS } from './orgSettings/sections';
import { useOrgProfileSections } from './orgSettings/useOrgProfileSections';
import { useOrgSettingsTabAccess } from './orgSettings/useOrgSettingsTabAccess';

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
  const { visibleSectionIds } = useOrgSettingsTabAccess(organization);
  const queryClient = useQueryClient();
  const profile = useOrgProfileSections(organization, sectionsRef);

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
          ...ORG_SETTINGS_SECTIONS.filter((s) =>
            visibleSectionIds.includes(s.id),
          ).map(({ id, label, icon, keywords, Component }) => ({
            value: id,
            label,
            icon,
            keywords,
            content: <Component organizationId={pk} />,
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
      footer={isOrgAdmin ? profile.saveBar : null}
      data-testid="org-settings-tab"
    />
  );
}
