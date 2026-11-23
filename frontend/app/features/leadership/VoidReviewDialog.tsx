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
import { VOID_REASON_MAX_LENGTH, VoidReasonSchema } from './schemas';

export interface VoidReviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pending: boolean;
  error: string | null;
  onConfirm: (reason: string) => void;
}

export function VoidReviewDialog({
  open,
  onOpenChange,
  pending,
  error,
  onConfirm,
}: VoidReviewDialogProps) {
  const [reason, setReason] = useState('');
  const inputId = useId();
  const parsed = VoidReasonSchema.safeParse(reason);

  useEffect(() => {
    if (open) setReason('');
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="leadership-void-dialog">
        <DialogHeader className="pr-8">
          <DialogTitle>Void this review?</DialogTitle>
          <DialogDescription>
            The review stops counting toward the captain's rating. You can
            restore it later.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          <Label htmlFor={inputId}>Reason</Label>
          <Textarea
            id={inputId}
            data-testid="leadership-void-reason"
            value={reason}
            maxLength={VOID_REASON_MAX_LENGTH}
            onChange={(e) => setReason(e.target.value)}
          />
          {error && (
            <p role="alert" className="text-sm break-words text-destructive">
              {error}
            </p>
          )}
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
            variant="destructive"
            loadingText="Voiding..."
            className="min-h-11 sm:min-h-9"
            data-testid="leadership-void-confirm"
            disabled={!parsed.success}
            loading={pending}
            onClick={() => {
              if (parsed.success) onConfirm(parsed.data);
            }}
          >
            Void review
          </ConfirmButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
