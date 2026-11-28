import { useEffect, useRef, useState, type ReactNode } from 'react';
import { staffReasonFormSchema } from '~/components/api/overridesAPI';
import { ConfirmDialog } from '~/components/ui/dialogs/ConfirmDialog';
import { Form } from '~/components/ui/form';
import { StaffReasonField, useStaffReasonForm } from './StaffReasonField';

export interface StaffReasonDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  contentTestId?: string;
  confirmTestId?: string;
  cancelTestId?: string;
  actionLabel: string;
  required: boolean;
  destructive?: boolean;
  submitting: boolean;
  onConfirm: (reason: string) => Promise<boolean>;
  serverError?: string;
  initialReason?: string;
  resetKey?: number;
}

export function StaffReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  actionLabel,
  required,
  destructive = false,
  submitting,
  onConfirm,
  serverError,
  initialReason = '',
  resetKey,
  contentTestId = 'staff-reason-dialog',
  confirmTestId = 'staff-reason-confirm',
  cancelTestId = 'staff-reason-cancel',
}: StaffReasonDialogProps) {
  const form = useStaffReasonForm(required, initialReason, open);
  const { reset } = form;
  const inFlight = useRef<Promise<void> | null>(null);
  const ignoreClose = useRef(false);
  const [pending, setPending] = useState(false);
  // formState.isValid is not recomputed by reset() when `required` flips.
  const reasonValid = staffReasonFormSchema(required).safeParse({
    reason: form.watch('reason'),
  }).success;

  useEffect(() => {
    reset({ reason: open ? initialReason : '' });
    ignoreClose.current = false;
  }, [open, initialReason, resetKey, reset]);

  const handleConfirm = (fromDialog: boolean): Promise<void> => {
    if (inFlight.current) return inFlight.current;
    if (submitting || !open) return Promise.resolve();
    setPending(true);
    const request = (async () => {
      let success = false;
      try {
        await form.handleSubmit(async ({ reason }) => {
          success = await onConfirm(reason);
        })();
        if (success && !fromDialog) onOpenChange(false);
      } finally {
        // ConfirmDialog closes in finally, even when the action was refused.
        ignoreClose.current = fromDialog && !success;
        inFlight.current = null;
        setPending(false);
      }
    })();
    inFlight.current = request;
    return request;
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && ignoreClose.current) {
          ignoreClose.current = false;
          return;
        }
        if (!nextOpen && (inFlight.current || submitting)) return;
        onOpenChange(nextOpen);
      }}
      title={title}
      description={description ?? 'This reason is recorded in signup history.'}
      confirmLabel={actionLabel}
      variant={destructive ? 'destructive' : 'default'}
      isLoading={submitting || pending}
      confirmDisabled={!reasonValid || submitting || pending}
      onConfirm={() => handleConfirm(true)}
      contentTestId={contentTestId}
      confirmTestId={confirmTestId}
      cancelTestId={cancelTestId}
      bodyContent={
        <Form {...form}>
          <div className="flex flex-col gap-4">
            <StaffReasonField
              form={form}
              required={required}
              onSubmit={() => handleConfirm(false)}
            />
            {serverError ? (
              <p role="alert" className="text-sm text-destructive">
                {serverError}
              </p>
            ) : null}
          </div>
        </Form>
      }
    />
  );
}
