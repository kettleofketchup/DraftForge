import { useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  SettingsDialog,
  type SettingsDialogHandle,
} from '~/components/patterns/SettingsDialog';
import { useOrgEventDefaultsSections } from './useOrgEventDefaultsSections';

interface EditOrgDefaultsModalProps {
  organizationId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditOrgDefaultsModal({
  organizationId,
  open,
  onOpenChange,
}: EditOrgDefaultsModalProps) {
  const sectionsRef = useRef<SettingsDialogHandle<string>>(null);
  const [saving, setSaving] = useState(false);
  const { sections, unit } = useOrgEventDefaultsSections(
    organizationId,
    sectionsRef,
    open,
  );

  async function onSubmit() {
    setSaving(true);
    try {
      if (await unit.save()) {
        toast.success('Event defaults updated');
        onOpenChange(false);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <SettingsDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Organization Event Defaults"
      description="These defaults are applied when creating new events."
      submitLabel="Save Defaults"
      isSubmitting={saving}
      autoFocus={false}
      onSubmit={onSubmit}
      sectionRef={sectionsRef}
      sections={sections}
      testIdPrefix="org-defaults"
      data-testid="org-defaults-modal"
    />
  );
}
