import { useQueryClient } from '@tanstack/react-query';
import { ShieldCheck } from 'lucide-react';
import { useRef, useState } from 'react';
import { AdminTeamSection } from '~/components/admin-team';
import { useOrgEventDefaultsSections } from '~/components/events/useOrgEventDefaultsSections';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import type { OrganizationType } from '~/components/organization/schemas';
import { ORG_SETTINGS_SECTIONS } from '~/components/organization/tabs/orgSettings/sections';
import { useOrgProfileSections } from '~/components/organization/tabs/orgSettings/useOrgProfileSections';
import { useOrgSettingsAccess } from '~/components/organization/tabs/orgSettings/useOrgSettingsAccess';
import {
  SettingsDialog,
  type SettingsDialogHandle,
  type SettingsSection,
} from '~/components/patterns/SettingsDialog';
import {
  useSettingsSaveBar,
  type SettingsFormUnit,
} from '~/components/patterns/settingsSaveBar';
import { ConfirmDialog } from '~/components/ui/dialogs';

export interface OrgSettingsDialogProps {
  organization: OrganizationType;
  open: boolean;
  /** Requested section; falls back to the first when unknown or null. */
  section: string | null;
  onSectionChange: (value: string) => void;
  onOpenChange: (open: boolean) => void;
}

/**
 * Every organization setting in one full-screen modal: profile, admin team,
 * registered settings sections and new-event defaults, saved by one save bar.
 */
export function OrgSettingsDialog({
  organization,
  open,
  section,
  onSectionChange,
  onOpenChange,
}: OrgSettingsDialogProps) {
  const sectionsRef = useRef<SettingsDialogHandle<string>>(null);
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const { canOpen, visibleSectionIds } = useOrgSettingsAccess(organization);
  const pk = organization.pk;

  const profile = useOrgProfileSections(organization, sectionsRef);
  const registry = ORG_SETTINGS_SECTIONS.map((s) => ({
    section: s,
    ...s.useSection(
      pk ?? 0,
      open && pk != null && visibleSectionIds.includes(s.id),
    ),
  }));
  const defaults = useOrgEventDefaultsSections(pk ?? 0, sectionsRef, open);

  const units: SettingsFormUnit[] = [
    profile.unit,
    ...registry.flatMap((r) => (r.unit ? [r.unit] : [])),
    defaults.unit,
  ];
  const { isDirty, saveAll, discardAll, saveBar } = useSettingsSaveBar(units, {
    testIdPrefix: 'org-settings',
  });

  if (pk == null || !canOpen) return null;

  const sections: SettingsSection[] = [
    ...profile.sections,
    {
      value: 'admins',
      label: 'Admin Team',
      icon: ShieldCheck,
      keywords: ['owner', 'admin', 'staff', 'promoter', 'roles'],
      group: 'Organization',
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
    ...registry
      .filter((r) => visibleSectionIds.includes(r.section.id))
      .map(({ section: { id, label, icon, keywords, group }, content }) => ({
        value: id,
        label,
        icon,
        keywords,
        group,
        content,
      })),
    ...defaults.sections,
  ];

  const handleOpenChange = (next: boolean): void => {
    if (!next && isDirty) setConfirmOpen(true);
    else onOpenChange(next);
  };

  return (
    <>
      <SettingsDialog
        open={open}
        onOpenChange={handleOpenChange}
        title="Organization Settings"
        sections={sections}
        section={section}
        onSectionChange={onSectionChange}
        sectionRef={sectionsRef}
        testIdPrefix="org-settings"
        data-testid="org-settings-modal"
        autoFocus={false}
        showFooter={false}
        footer={saveBar}
        onSubmit={async () => {
          await saveAll();
        }}
      />
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Discard unsaved changes?"
        description="Your unsaved organization settings will be lost."
        confirmLabel="Discard"
        variant="destructive"
        onConfirm={() => {
          discardAll();
          onOpenChange(false);
        }}
        confirmTestId="org-settings-discard-confirm"
        cancelTestId="org-settings-discard-cancel"
      />
    </>
  );
}
