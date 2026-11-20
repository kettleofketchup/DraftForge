import { type ReactNode, useEffect, useRef, useState } from 'react';
import type {
  FieldValues,
  SubmitErrorHandler,
  UseFormHandleSubmit,
} from 'react-hook-form';
import { toast } from 'sonner';

import { CancelButton, SubmitButton } from '~/components/ui/buttons';
import { getLogger } from '~/lib/logger';

const log = getLogger('settingsSaveBar');

/** A save pending this long is reported as stuck and no longer blocks closing. */
export const SAVE_STUCK_MS = 15_000;

export interface SettingsFormUnit {
  id: string;
  isDirty: boolean;
  /**
   * Validates and saves. Resolves false when invalid or the request failed; the
   * unit shows its own error. `select: false` keeps an invalid unit from moving
   * the dialog to its failing section; the save bar sets it after the first failure.
   */
  save: (opts?: { select?: boolean }) => Promise<boolean>;
  discard: () => void;
}

/** Runs a react-hook-form submit and resolves whether `onValid` ran and returned true. */
export async function submitForm<
  TFieldValues extends FieldValues,
  TTransformed,
>(
  form: { handleSubmit: UseFormHandleSubmit<TFieldValues, TTransformed> },
  onValid: (data: TTransformed) => Promise<boolean>,
  onInvalid?: SubmitErrorHandler<TFieldValues>,
): Promise<boolean> {
  let ok = false;
  await form.handleSubmit(async (data) => {
    ok = await onValid(data);
  }, onInvalid)();
  return ok;
}

export function useSettingsSaveBar(
  units: SettingsFormUnit[],
  opts: { testIdPrefix: string },
): {
  isDirty: boolean;
  isSaving: boolean;
  /** A save has been pending longer than SAVE_STUCK_MS. */
  isSaveStuck: boolean;
  saveAll: () => Promise<boolean>;
  discardAll: () => void;
  saveBar: ReactNode;
} {
  const [isSaving, setIsSaving] = useState(false);
  const [isSaveStuck, setIsSaveStuck] = useState(false);
  const isDirty = units.some((u) => u.isDirty);

  useEffect(() => {
    if (!isSaving) {
      setIsSaveStuck(false);
      return;
    }
    const timer = window.setTimeout(() => {
      log.warn('settings save still pending', { after_ms: SAVE_STUCK_MS });
      setIsSaveStuck(true);
    }, SAVE_STUCK_MS);
    return () => window.clearTimeout(timer);
  }, [isSaving]);

  const inFlight = useRef<Promise<boolean> | null>(null);

  const saveAll = (): Promise<boolean> => {
    if (inFlight.current) return inFlight.current;
    const dirty = units.filter((u) => u.isDirty);
    if (dirty.length === 0) return Promise.resolve(true);
    const run = async (): Promise<boolean> => {
      setIsSaving(true);
      let failed = 0;
      for (const unit of dirty) {
        let ok = false;
        try {
          ok = await unit.save({ select: failed === 0 });
        } catch (err) {
          log.error('settings unit save threw', { unit: unit.id, err });
        }
        if (!ok) failed += 1;
      }
      inFlight.current = null;
      setIsSaving(false);
      if (failed === 0) toast.success('Settings saved');
      else if (failed < dirty.length) {
        toast.warning(
          'Some settings saved. Fix the highlighted fields to save the rest.',
        );
      }
      return failed === 0;
    };
    inFlight.current = run();
    return inFlight.current;
  };

  const discardAll = (): void => {
    for (const unit of units) if (unit.isDirty) unit.discard();
  };

  const prefix = opts.testIdPrefix;
  const saveBar = isDirty ? (
    <div
      className="sticky bottom-4 mx-auto mt-6 flex w-full max-w-4xl items-center justify-end gap-2 rounded-lg border border-border bg-background/95 p-3 shadow-lg backdrop-blur"
      data-testid={`${prefix}-save-bar`}
    >
      <span className="mr-auto text-sm text-muted-foreground">
        {isSaveStuck ? 'Still saving…' : 'Unsaved changes'}
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

  return { isDirty, isSaving, isSaveStuck, saveAll, discardAll, saveBar };
}
