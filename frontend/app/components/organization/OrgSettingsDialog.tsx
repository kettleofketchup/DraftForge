import { useQueryClient } from '@tanstack/react-query';
import { ShieldCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useBlocker } from 'react-router';
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
  const enabled = open && pk != null && canOpen;

  const profile = useOrgProfileSections(organization, sectionsRef);
  const activeId = section ?? profile.sections[0].value;
  const [visited, setVisited] = useState<ReadonlySet<string>>(
    () => new Set([activeId]),
  );
  if (!visited.has(activeId)) setVisited(new Set(visited).add(activeId));
  const registry = ORG_SETTINGS_SECTIONS.map((s) => ({
    section: s,
    ...s.useSection(
      pk ?? 0,
      enabled && visibleSectionIds.includes(s.id) && visited.has(s.id),
      sectionsRef,
    ),
  }));
  const defaultsVisited = [...visited].some((v) => v.startsWith('defaults-'));
  const defaults = useOrgEventDefaultsSections(
    pk ?? 0,
    sectionsRef,
    enabled && defaultsVisited,
  );

  const units: SettingsFormUnit[] = [
    profile.unit,
    ...registry.flatMap((r) => (r.unit ? [r.unit] : [])),
    defaults.unit,
  ];
  const { isDirty, isSaving, isSaveStuck, saveAll, discardAll, saveBar } =
    useSettingsSaveBar(units, {
      testIdPrefix: 'org-settings',
    });

  // After the user confirms a discard, the close navigation must not prompt again.
  const allowLeave = useRef(false);
  useEffect(() => {
    if (isDirty) allowLeave.current = false;
  }, [isDirty]);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      open &&
      isDirty &&
      !allowLeave.current &&
      (nextLocation.pathname !== currentLocation.pathname ||
        !new URLSearchParams(nextLocation.search).has('settings')),
  );
  const blocked = blocker.state === 'blocked';

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
    if (!next && isSaving && !isSaveStuck) return;
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
        open={confirmOpen || blocked}
        onOpenChange={(next) => {
          if (next) return;
          setConfirmOpen(false);
          if (blocked && !allowLeave.current) blocker.reset();
        }}
        title="Discard unsaved changes?"
        description="Your unsaved organization settings will be lost."
        confirmLabel="Discard"
        variant="destructive"
        onConfirm={() => {
          allowLeave.current = true;
          discardAll();
          if (blocked) blocker.proceed();
          else onOpenChange(false);
        }}
        confirmTestId="org-settings-discard-confirm"
        cancelTestId="org-settings-discard-cancel"
      />
    </>
  );
}
