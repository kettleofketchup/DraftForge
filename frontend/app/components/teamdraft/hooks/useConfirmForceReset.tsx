import { useCallback, useRef, useState } from 'react';
import type { DraftReferenceCounts } from '~/components/api/types';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { type ConfirmForceReset, forceResetMessage } from './initDraftHook';

/** Promise-backed second confirm for a draft reset whose teams are referenced. */
export function useConfirmForceReset() {
  const [references, setReferences] = useState<DraftReferenceCounts | null>(
    null,
  );
  const resolveRef = useRef<((confirmed: boolean) => void) | null>(null);

  const settle = useCallback((confirmed: boolean) => {
    resolveRef.current?.(confirmed);
    resolveRef.current = null;
    setReferences(null);
  }, []);

  const confirmForce = useCallback<ConfirmForceReset>(
    (refs) =>
      new Promise<boolean>((resolve) => {
        resolveRef.current?.(false);
        resolveRef.current = resolve;
        setReferences(refs);
      }),
    [],
  );

  const confirmForceDialog = (
    <ConfirmDialog
      open={references !== null}
      onOpenChange={(open) => {
        if (!open) settle(false);
      }}
      title="Teams are in use"
      description={references ? forceResetMessage(references) : ''}
      confirmLabel="Reset anyway"
      variant="destructive"
      onConfirm={() => settle(true)}
      contentTestId="draft-force-reset-dialog"
      confirmTestId="draft-force-reset-confirm"
      cancelTestId="draft-force-reset-cancel"
    />
  );

  return { confirmForce, confirmForceDialog };
}
