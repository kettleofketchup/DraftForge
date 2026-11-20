import { useRef, type ReactNode } from 'react';
import {
  SettingsDialog,
  type SettingsDialogHandle,
} from '~/components/patterns/SettingsDialog';
import { useOrgEventDefaultsSections } from '../useOrgEventDefaultsSections';

/** The event-defaults sections inside a SettingsDialog whose submit saves the unit. */
export function OrgEventDefaultsHarness({
  organizationId,
}: {
  organizationId: number;
}): ReactNode {
  const sectionsRef = useRef<SettingsDialogHandle<string>>(null);
  const { sections, unit } = useOrgEventDefaultsSections(
    organizationId,
    sectionsRef,
    true,
  );
  return (
    <SettingsDialog
      open
      onOpenChange={() => {}}
      title="Event defaults"
      autoFocus={false}
      onSubmit={async () => {
        await unit.save();
      }}
      sectionRef={sectionsRef}
      sections={sections}
      testIdPrefix="org-defaults"
    />
  );
}
