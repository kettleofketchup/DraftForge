import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import type { z } from 'zod';
import { LEAGUE_MMR_GAME, toGameType } from '~/components/game/constants';
import {
  computeMmrDelta,
  LARGE_MMR_CHANGE_THRESHOLD,
} from '~/components/game/mmrDelta';
import { ConfirmDialog, FormDialog } from '~/components/ui/dialogs';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { cn } from '~/lib/utils';
import { MmrStatusBadge } from './MmrStatusBadge';
import { requestTargetLabel as targetLabel } from './format';
import { useApproveMmrRequest } from './queries';
import {
  firstFieldError,
  readReviewError,
  reviewErrorMessage,
} from './reviewErrors';
import { staffSetFormSchema, type MmrChangeRequest } from './schemas';

export interface ReviewMmrDialogProps {
  request: MmrChangeRequest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function approveSchema(request: MmrChangeRequest) {
  const game =
    request.target === 'org' ? toGameType(request.game_type) : LEAGUE_MMR_GAME;
  return staffSetFormSchema(game).pick({ mmr: true });
}
type ApproveSchema = ReturnType<typeof approveSchema>;
type ApproveValues = z.infer<ApproveSchema>;

export function ReviewMmrDialog({
  request,
  open,
  onOpenChange,
}: ReviewMmrDialogProps) {
  const approve = useApproveMmrRequest();
  const [confirmValue, setConfirmValue] = useState<number | null>(null);
  const schema = useMemo(() => approveSchema(request), [request]);
  const form = useForm<z.input<ApproveSchema>, unknown, ApproveValues>({
    resolver: zodResolver(schema),
    defaultValues: { mmr: request.requested_mmr },
  });

  useEffect(() => {
    if (open) {
      form.reset({ mmr: request.requested_mmr });
      setConfirmValue(null);
    }
  }, [open, request.requested_mmr, form]);

  const raw = form.watch('mmr');
  const value = typeof raw === 'number' && Number.isFinite(raw) ? raw : null;
  const delta =
    value != null ? computeMmrDelta(request.current_mmr, value) : null;
  const name = request.subject.nickname || request.subject.username;

  const doApprove = async (mmr: number) => {
    try {
      await approve.mutateAsync({
        request,
        mmr: mmr !== request.requested_mmr ? mmr : undefined,
      });
      toast.success(`Approved ${name}'s MMR as ${mmr}`);
      onOpenChange(false);
    } catch (error) {
      const { status, data } = readReviewError(error);
      const mmrError = status === 400 ? firstFieldError(data.mmr) : null;
      if (mmrError) {
        form.setError('mmr', { message: mmrError });
        return;
      }
      toast.error(reviewErrorMessage(error, 'Could not approve the request'));
      if (status === 409) onOpenChange(false);
    }
  };

  const onSubmit = async (values: ApproveValues) => {
    if (computeMmrDelta(request.current_mmr, values.mmr).isLarge) {
      setConfirmValue(values.mmr);
      return;
    }
    await doApprove(values.mmr);
  };

  return (
    <>
      <FormDialog
        open={open}
        onOpenChange={onOpenChange}
        title={`Approve MMR — ${name}`}
        description={`${targetLabel(request)}. Approving makes this value official.`}
        submitLabel="Approve"
        isSubmitting={approve.isPending}
        onSubmit={form.handleSubmit(onSubmit)}
        submitTestId="mmr-approve-confirm"
        data-testid="mmr-approve-dialog"
      >
        <Form {...form}>
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">Current:</span>
            <span className="font-medium">
              {request.current_mmr > 0 ? request.current_mmr : 'Not set'}
            </span>
            {request.current_mmr > 0 && (
              <MmrStatusBadge verified={request.current_verified} />
            )}
            <span className="text-muted-foreground">· Requested:</span>
            <span className="font-medium">{request.requested_mmr}</span>
          </p>
          <FormField
            control={form.control}
            name="mmr"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Official MMR</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    inputMode="numeric"
                    data-testid="mmr-approve-value"
                    name={field.name}
                    ref={field.ref}
                    onBlur={field.onBlur}
                    value={
                      typeof field.value === 'number' ||
                      typeof field.value === 'string'
                        ? field.value
                        : ''
                    }
                    onChange={(e) =>
                      field.onChange(
                        e.target.value === '' ? '' : e.target.valueAsNumber,
                      )
                    }
                  />
                </FormControl>
                {delta && delta.delta !== 0 && (
                  <div
                    data-testid="mmr-approve-delta"
                    className={cn(
                      'mt-2 rounded-md border px-3 py-2 font-mono text-xs',
                      delta.isLarge
                        ? 'border-warning/40 bg-warning/5 text-warning'
                        : 'border-border/60 bg-base-300 text-muted-foreground',
                    )}
                  >
                    {request.current_mmr} → {value} (
                    {delta.delta > 0 ? '+' : ''}
                    {delta.delta}
                    {delta.pct != null
                      ? `, ${Math.round(delta.pct * 100)}%`
                      : ''}
                    )
                    {delta.isLarge && (
                      <p className="mt-1 text-[11px] text-warning/80">
                        This is more than{' '}
                        {Math.round(LARGE_MMR_CHANGE_THRESHOLD * 100)}% off the
                        current MMR — you'll be asked to confirm.
                      </p>
                    )}
                  </div>
                )}
                <FormMessage />
              </FormItem>
            )}
          />
        </Form>
      </FormDialog>

      <ConfirmDialog
        open={confirmValue != null}
        onOpenChange={(next) => !next && setConfirmValue(null)}
        title="Confirm large MMR change"
        description={`Approving ${name} at ${confirmValue ?? ''} MMR. Their current MMR is ${request.current_mmr}. This is more than ${Math.round(LARGE_MMR_CHANGE_THRESHOLD * 100)}% off — confirm this is intentional.`}
        confirmLabel="Approve anyway"
        variant="warning"
        isLoading={approve.isPending}
        onConfirm={async () => {
          if (confirmValue != null) await doApprove(confirmValue);
        }}
        confirmTestId="mmr-approve-anyway"
        cancelTestId="mmr-approve-anyway-cancel"
      />
    </>
  );
}
