import { useCallback, useRef, useState } from 'react';
import type { DraftResetConflict } from '~/components/api/types';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { forceResetMessage, usageCount } from '../draftResetText';
import type { ConfirmForceReset } from './initDraftHook';

/** Promise-backed second confirm for a draft reset whose teams are referenced. */
export function useConfirmForceReset() {
  const [conflict, setConflict] = useState<DraftResetConflict | null>(null);
  const resolveRef = useRef<((confirmed: boolean) => void) | null>(null);

  const settle = useCallback((confirmed: boolean) => {
    resolveRef.current?.(confirmed);
    resolveRef.current = null;
    setConflict(null);
  }, []);

  const confirmForce = useCallback<ConfirmForceReset>(
    (next) =>
      new Promise<boolean>((resolve) => {
        resolveRef.current?.(false);
        resolveRef.current = resolve;
        setConflict(next);
      }),
    [],
  );

  const usage = conflict?.usage ?? [];
  const confirmForceDialog = (
    <ConfirmDialog
      open={conflict !== null}
      onOpenChange={(open) => {
        if (!open) settle(false);
      }}
      title="Teams are in use"
      description={conflict ? forceResetMessage(conflict) : ''}
      bodyContent={
        usage.length ? (
          <ul
            className="flex flex-col gap-1 text-sm"
            data-testid="draft-force-reset-usage"
          >
            {usage.map((kind) => (
              <li
                key={kind.model}
                className="flex flex-wrap gap-x-2"
                data-testid="draft-force-reset-usage-row"
              >
                <span className="font-semibold">{usageCount(kind)}</span>
                <span className="text-muted-foreground">
                  {kind.teams.map((team) => team.name).join(', ')}
                </span>
              </li>
            ))}
          </ul>
        ) : undefined
      }
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
