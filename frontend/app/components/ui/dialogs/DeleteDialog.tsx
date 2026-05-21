import * as React from 'react';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { getLogger } from '~/lib/logger';
import { ConfirmDialog } from './ConfirmDialog';

const log = getLogger('DeleteDialog');

export interface DeleteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Display kind used in copy. e.g. "League", "Organization", "Event Series". */
  entityKind: string;
  /** Exact string the user must type to enable Delete. Must be non-empty. */
  entityName: string;
  /** Optional consequences copy. Default fallback is "This action cannot be undone." */
  description?: React.ReactNode;
  isLoading?: boolean;
  onConfirm: () => void | Promise<void>;
  ref?: React.Ref<HTMLDivElement>;
  contentTestId?: string;
  inputTestId?: string;
  confirmTestId?: string;
  cancelTestId?: string;
}

export const DEFAULT_DELETE_DESCRIPTION = 'This action cannot be undone.';

export function DeleteDialog({
  open,
  onOpenChange,
  entityKind,
  entityName,
  description,
  isLoading = false,
  onConfirm,
  ref,
  contentTestId,
  inputTestId,
  confirmTestId,
  cancelTestId,
}: DeleteDialogProps) {
  // Hooks first — keep call count stable across re-renders.
  const inputId = React.useId();
  const [value, setValue] = React.useState('');

  React.useEffect(() => {
    if (!open) setValue('');
  }, [open]);

  // Secondary guard. Primary defense is caller-side: callers should guard the mount
  // with `{entity?.name && <DeleteDialog ... />}`. Throwing here would kill the
  // parent tree; render-null is the safer fallback.
  if (!entityName) {
    log.error('entityName must be non-empty', { entityKind });
    return null;
  }

  const nameMatches = value === entityName;

  const bodyContent = (
    <div className="space-y-2">
      <Label htmlFor={inputId}>
        Type <strong>{entityName}</strong> to confirm
      </Label>
      <Input
        id={inputId}
        data-testid={inputTestId}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={entityName}
        autoComplete="off"
        disabled={isLoading}
        className="bg-base-900/80 border-destructive/60 text-foreground focus-visible:ring-destructive/40"
      />
    </div>
  );

  return (
    <ConfirmDialog
      ref={ref}
      open={open}
      onOpenChange={onOpenChange}
      title={`Delete this ${entityKind}?`}
      description={description ?? DEFAULT_DELETE_DESCRIPTION}
      confirmLabel={`Delete ${entityKind}`}
      cancelLabel="Cancel"
      variant="destructive"
      isLoading={isLoading}
      confirmDisabled={!nameMatches}
      onConfirm={onConfirm}
      contentTestId={contentTestId}
      confirmTestId={confirmTestId}
      cancelTestId={cancelTestId}
      bodyContent={bodyContent}
    />
  );
}

export default DeleteDialog;
