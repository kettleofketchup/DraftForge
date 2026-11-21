import { useEffect, useId, useState } from 'react';
import { CancelButton, ConfirmButton } from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Label } from '~/components/ui/label';
import { Textarea } from '~/components/ui/textarea';
import { REASON_MAX_LENGTH, REASON_MIN_LENGTH, ReasonSchema } from './schemas';

export interface ReasonDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  changeCount: number;
  pending: boolean;
  onConfirm: (reason: string) => void;
}

export function ReasonDialog({
  open,
  onOpenChange,
  changeCount,
  pending,
  onConfirm,
}: ReasonDialogProps) {
  const [reason, setReason] = useState('');
  const inputId = useId();
  const parsed = ReasonSchema.safeParse(reason);

  useEffect(() => {
    if (open) setReason('');
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="conduct-reason-dialog">
        <DialogHeader>
          <DialogTitle>Why are you changing attendance?</DialogTitle>
          <DialogDescription>
            {changeCount} {changeCount === 1 ? 'change' : 'changes'} will be
            saved with this reason. Edits are audited.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          <Label htmlFor={inputId}>Reason</Label>
          <Textarea
            id={inputId}
            data-testid="conduct-reason-input"
            value={reason}
            maxLength={REASON_MAX_LENGTH}
            onChange={(e) => setReason(e.target.value)}
            placeholder={`At least ${REASON_MIN_LENGTH} characters`}
          />
        </div>
        <DialogFooter>
          <CancelButton
            className="min-h-11 sm:min-h-9"
            onClick={() => onOpenChange(false)}
            disabled={pending}
          >
            Cancel
          </CancelButton>
          <ConfirmButton
            className="min-h-11 sm:min-h-9"
            data-testid="conduct-reason-confirm"
            disabled={!parsed.success}
            loading={pending}
            onClick={() => {
              if (parsed.success) onConfirm(parsed.data);
            }}
          >
            Save attendance
          </ConfirmButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
