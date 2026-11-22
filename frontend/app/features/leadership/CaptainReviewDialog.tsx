import { zodResolver } from '@hookform/resolvers/zod';
import { Clock } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import {
  CancelButton,
  ConfirmButton,
  DestructiveButton,
} from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { DisplayName } from '~/components/user/avatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getLogger } from '~/lib/logger';
import { formatCountdown, useCountdown } from './countdown';
import {
  refusalCode,
  refusalMessage,
  refusalText,
  type RefusalContext,
} from './errors';
import { useSubmitReview, useWithdrawReview } from './queries';
import { reviewAction } from './reviewState';
import { ScoresFormSchema, type PendingReview, type Scores } from './schemas';
import { ScoreRadioGroup } from './ScoreRadioGroup';

const log = getLogger('CaptainReviewDialog');

export interface CaptainReviewDialogProps {
  orgId: number;
  access: OrgFeatureAccess;
  review: PendingReview;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CaptainReviewDialog({
  orgId,
  access,
  review,
  open,
  onOpenChange,
}: CaptainReviewDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="leadership-review-dialog">
        <ReviewForm
          orgId={orgId}
          access={access}
          review={review}
          onDone={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

function initialScores(
  review: PendingReview,
): Record<string, number | undefined> {
  return Object.fromEntries(
    review.traits.map((t) => [t.key, review.scores?.[t.key]]),
  );
}

function ReviewForm({
  orgId,
  access,
  review,
  onDone,
}: {
  orgId: number;
  access: OrgFeatureAccess;
  review: PendingReview;
  onDone: () => void;
}) {
  const keys = useMemo(() => review.traits.map((t) => t.key), [review.traits]);
  const schema = useMemo(() => ScoresFormSchema(keys), [keys]);
  const form = useForm<Scores>({
    resolver: zodResolver(schema),
    defaultValues: initialScores(review),
  });
  const { msLeft, closed } = useCountdown(review.window_closes_at);
  const submitReview = useSubmitReview(orgId, access);
  const withdrawReview = useWithdrawReview(orgId, access);
  const [error, setError] = useState<string | null>(null);

  const action = reviewAction(review);
  const moderated = action.state === 'moderated';
  const resubmit =
    review.scores !== null &&
    (review.void_kind === 'withdrawn' || review.void_kind === 'lifecycle');
  const busy = submitReview.isPending || withdrawReview.isPending;
  const locked = moderated || closed;
  const target = {
    eventId: review.event_id,
    captainOrgUserId: review.captain_org_user_id,
  };

  function refused(err: unknown, context: RefusalContext) {
    log.warn('captain review refused', {
      orgId,
      eventId: review.event_id,
      code: refusalCode(err),
    });
    setError(refusalMessage(err, context));
  }

  const onSubmit = form.handleSubmit((values) => {
    setError(null);
    const scores: Scores = Object.fromEntries(
      keys.map((key) => [key, values[key]]),
    );
    submitReview.mutate(
      { ...target, scores },
      {
        onSuccess: () => {
          toast.success('Review saved');
          onDone();
        },
        onError: (err) => refused(err, 'submit'),
      },
    );
  });

  function onWithdraw() {
    setError(null);
    withdrawReview.mutate(target, {
      onSuccess: () => {
        toast.success('Review withdrawn');
        onDone();
      },
      onError: (err) => refused(err, 'withdraw'),
    });
  }

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <DialogHeader className="pr-8">
          <DialogTitle>Rate your captain</DialogTitle>
          <DialogDescription className="break-words">
            How did {DisplayName(review.captain)} lead {review.team_name} at{' '}
            {review.event_name}? Your scores are anonymous to the captain.
          </DialogDescription>
          <p
            data-testid="leadership-review-countdown"
            className="flex items-center justify-center gap-1.5 text-sm text-muted-foreground sm:justify-start"
          >
            <Clock aria-hidden="true" className="size-4 shrink-0" />
            {formatCountdown(msLeft)}
          </p>
        </DialogHeader>

        {moderated && (
          <p
            data-testid="leadership-review-moderated"
            className="rounded-md border border-border bg-muted/40 p-3 text-sm"
          >
            {refusalText('review_moderated')}
          </p>
        )}
        {closed && (
          <p
            data-testid="leadership-review-closed"
            className="rounded-md border border-border bg-muted/40 p-3 text-sm"
          >
            The review window has closed.
          </p>
        )}
        {resubmit && !locked && (
          <p
            data-testid="leadership-review-resubmit"
            className="text-sm text-muted-foreground"
          >
            Your earlier review no longer counts. Submit again to restore it.
          </p>
        )}

        <div className="flex flex-col gap-4">
          {review.traits.map((trait) => (
            <FormField
              key={trait.key}
              control={form.control}
              name={trait.key}
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="break-words">{trait.label}</FormLabel>
                  <FormControl>
                    <ScoreRadioGroup
                      name={field.name}
                      label={trait.label}
                      value={field.value}
                      onChange={field.onChange}
                      disabled={locked || busy}
                      testIdPrefix={`leadership-review-${trait.key}`}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          ))}
        </div>

        {error && (
          <p
            role="alert"
            data-testid="leadership-review-error"
            className="text-sm font-medium text-destructive"
          >
            {error}
          </p>
        )}

        <DialogFooter>
          <CancelButton
            type="button"
            className="min-h-11 sm:min-h-9"
            onClick={onDone}
            disabled={busy}
          >
            {locked ? 'Close' : 'Cancel'}
          </CancelButton>
          {action.state === 'submitted' && (
            <DestructiveButton
              type="button"
              data-testid="leadership-review-withdraw"
              className="min-h-11 sm:min-h-9"
              onClick={onWithdraw}
              disabled={closed || submitReview.isPending}
              loading={withdrawReview.isPending}
            >
              Withdraw
            </DestructiveButton>
          )}
          {!moderated && (
            <ConfirmButton
              type="submit"
              data-testid="leadership-review-submit"
              className="min-h-11 sm:min-h-9"
              disabled={closed || withdrawReview.isPending}
              loading={submitReview.isPending}
            >
              {action.state === 'submitted' ? 'Update' : 'Submit'}
            </ConfirmButton>
          )}
        </DialogFooter>
      </form>
    </Form>
  );
}
