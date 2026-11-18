import type { OrganizationType } from '~/components/organization/schemas';
import { ORG_SETTINGS_SECTIONS } from './orgSettings/sections';
import { useOrgSettingsTabAccess } from './orgSettings/useOrgSettingsTabAccess';

export function OrgSettingsTab({
  organization,
}: {
  organization: OrganizationType;
}) {
  const { visibleSectionIds } = useOrgSettingsTabAccess(organization);
  const visible = ORG_SETTINGS_SECTIONS.filter((s) =>
    visibleSectionIds.includes(s.id),
  );
  return (
    <div data-testid="org-settings-tab" className="flex flex-col gap-6">
      {organization.pk != null &&
        visible.map(({ id, Component }) => (
          <Component key={id} organizationId={organization.pk!} />
        ))}
    </div>
  );
}
