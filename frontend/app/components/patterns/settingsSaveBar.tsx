import { type ReactNode, useCallback, useState } from 'react';
import { toast } from 'sonner';

import { CancelButton, SubmitButton } from '~/components/ui/buttons';
import { getLogger } from '~/lib/logger';

const log = getLogger('settingsSaveBar');

export interface SettingsFormUnit {
  id: string;
  isDirty: boolean;
  /** Validates and saves. Resolves false when invalid or the request failed; the unit shows its own error. */
  save: () => Promise<boolean>;
  discard: () => void;
}

export function useSettingsSaveBar(
  units: SettingsFormUnit[],
  opts: { testIdPrefix: string },
): {
  isDirty: boolean;
  isSaving: boolean;
  saveAll: () => Promise<boolean>;
  discardAll: () => void;
  saveBar: ReactNode;
} {
  const [isSaving, setIsSaving] = useState(false);
  const isDirty = units.some((u) => u.isDirty);

  const saveAll = useCallback(async (): Promise<boolean> => {
    setIsSaving(true);
    let allOk = true;
    try {
      for (const unit of units.filter((u) => u.isDirty)) {
        let ok = false;
        try {
          ok = await unit.save();
        } catch (err) {
          log.error('settings unit save threw', { unit: unit.id, err });
        }
        if (!ok) allOk = false;
      }
    } finally {
      setIsSaving(false);
    }
    if (allOk) toast.success('Settings saved');
    return allOk;
  }, [units]);

  const discardAll = useCallback((): void => {
    for (const unit of units) if (unit.isDirty) unit.discard();
  }, [units]);

  const prefix = opts.testIdPrefix;
  const saveBar = isDirty ? (
    <div
      className="sticky bottom-4 mx-auto mt-6 flex w-full max-w-4xl items-center justify-end gap-2 rounded-lg border border-border bg-background/95 p-3 shadow-lg backdrop-blur"
      data-testid={`${prefix}-save-bar`}
    >
      <span className="mr-auto text-sm text-muted-foreground">
        Unsaved changes
      </span>
      <CancelButton
        type="button"
        disabled={isSaving}
        onClick={discardAll}
        data-testid={`${prefix}-discard`}
      >
        Discard
      </CancelButton>
      <SubmitButton
        loading={isSaving}
        onClick={() => void saveAll()}
        data-testid={`${prefix}-save`}
      >
        Save changes
      </SubmitButton>
    </div>
  ) : null;

  return { isDirty, isSaving, saveAll, discardAll, saveBar };
}
