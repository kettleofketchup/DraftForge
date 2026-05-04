import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { GAME_TYPE } from '~/components/game/constants';
import { useGameType } from '~/hooks/useGameType';
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
import { Input } from '~/components/ui/input';
import { Badge } from '~/components/ui/badge';
import {
  ConfirmButton,
  DestructiveButton,
  DotabuffButton,
  SecondaryButton,
  SubmitButton,
} from '~/components/ui/buttons';
import { cn } from '~/lib/utils';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { RankSignalsCard } from '~/components/events/games/RankSignalsCard';
import type { EventSignupType } from '~/components/events/schemas';

const OVERRIDE_THRESHOLD = 0.2;

// ---------------------------------------------------------------------------
// MMR schema
// ---------------------------------------------------------------------------
const mmrSchema = z.object({
  mmr: z.number({ coerce: true }).int().min(0, 'MMR must be positive').max(20000, 'MMR too high'),
});
type MmrFormValues = z.infer<typeof mmrSchema>;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
interface MmrApprovalModalProps {
  signup: EventSignupType | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApprove: (signupId: number, mmr: number) => void;
  onReject?: (signupId: number) => void;
  isApproving?: boolean;
  isRejecting?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export function MmrApprovalModal({
  signup,
  open,
  onOpenChange,
  onApprove,
  onReject,
  isApproving = false,
  isRejecting = false,
}: MmrApprovalModalProps) {
  const gameType = useGameType();
  const [overrideConfirmed, setOverrideConfirmed] = useState(false);
  const form = useForm<MmrFormValues>({
    resolver: zodResolver(mmrSchema),
    defaultValues: { mmr: 0 },
  });

  // Reset form when signup changes. Use the serializer-computed suggested_mmr
  // (now self-report-first per the suggest_mmr precedence change).
  useEffect(() => {
    if (signup && open) {
      form.reset({ mmr: signup.suggested_mmr });
      setOverrideConfirmed(false);
    }
  }, [signup, open]);

  const watchedMmr = form.watch('mmr');
  const autofillDefault = signup?.suggested_mmr ?? null;
  const overrideDeltaPct =
    autofillDefault != null && autofillDefault > 0 && Number.isFinite(watchedMmr)
      ? Math.abs(watchedMmr - autofillDefault) / autofillDefault
      : 0;
  const needsConfirm = overrideDeltaPct >= OVERRIDE_THRESHOLD;

  // Re-arm confirmation on every input change. Keying off needsConfirm alone
  // misses the case where an admin confirms one over-threshold value (e.g.
  // 4,500), then keeps typing another over-threshold value (5,000): the
  // confirm flag would stay set since needsConfirm never flipped.
  useEffect(() => {
    setOverrideConfirmed(false);
  }, [watchedMmr]);

  if (!signup) return null;

  const profile = signup.dota_profile;
  const user = signup.user_data;
  const playerName = user ? DisplayName(user) : signup.username ?? `User #${signup.user}`;

  // Screenshot URL (rank or battlecup)
  const screenshotUrl = profile?.rank_screenshot ?? profile?.battlecup_screenshot ?? null;

  // Rank status badge — values come from PlayerDotaProfile.rank_status:
  // 'active' | 'previous' | 'never'.
  const rankStatusBadge = profile ? (
    profile.rank_status === 'active' ? (
      <Badge variant="outline" className="px-1.5 py-0 text-xs font-medium text-amber-300 border-amber-500/30">
        Active
      </Badge>
    ) : profile.rank_status === 'previous' ? (
      <Badge variant="outline" className="px-1.5 py-0 text-xs font-medium text-amber-300 border-amber-500/30">
        Previous
      </Badge>
    ) : (
      <Badge variant="outline" className="px-1.5 py-0 text-xs font-medium text-blue-300 border-blue-500/30">
        Never Ranked
      </Badge>
    )
  ) : null;

  const handleSubmit = (values: MmrFormValues) => {
    onApprove(signup.id, values.mmr);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <UserAvatar user={user ?? undefined} src={signup.user_avatar ?? undefined} size="lg" />
            <div className="min-w-0 flex-1">
              <DialogTitle className="text-lg truncate">{playerName}</DialogTitle>
              <DialogDescription className="flex items-center gap-1.5 mt-0.5">
                {rankStatusBadge ?? 'No Dota profile'}
              </DialogDescription>
            </div>
            <DotabuffButton
              steamAccountId={user?.steam_account_id}
              responsive={false}
              size="sm"
            />
          </div>
        </DialogHeader>

        {/* Rank signals — replaces the two prior inline blocks. */}
        <RankSignalsCard signup={signup} />

        {/* Screenshot section */}
        {screenshotUrl && (
          <div className="rounded-lg border border-border overflow-hidden bg-base-800">
            <a href={screenshotUrl} target="_blank" rel="noopener noreferrer">
              <img
                src={screenshotUrl}
                alt="Rank verification screenshot"
                className="w-full max-h-[300px] object-contain"
                loading="lazy"
              />
            </a>
          </div>
        )}

        {/* MMR input form */}
        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="mmr"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Approved MMR</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      placeholder="e.g. 3000"
                      data-testid="mmr-input"
                      {...field}
                      onChange={(e) => field.onChange(e.target.valueAsNumber || 0)}
                    />
                  </FormControl>
                  {gameType === GAME_TYPE.DOTA2 && (
                    <p
                      data-testid="suggested-range-helper"
                      className="text-xs text-muted-foreground font-mono mt-1"
                    >
                      Suggested range:{' '}
                      {signup.suggested_mmr_range[0].toLocaleString()}&ndash;
                      {signup.suggested_mmr_range[1].toLocaleString()}
                      <span className="ml-1 text-muted-foreground/80">
                        (from{' '}
                        {signup.suggested_mmr_range_source === 'battle_cup'
                          ? 'battle cup'
                          : signup.suggested_mmr_range_source}
                        )
                      </span>
                    </p>
                  )}
                  {needsConfirm && autofillDefault != null && (
                    <div
                      data-testid="mmr-override-confirm"
                      className={cn(
                        'mt-2 rounded-md border px-3 py-2',
                        overrideConfirmed
                          ? 'border-emerald-500/40 bg-emerald-500/5'
                          : 'border-amber-500/40 bg-amber-500/5',
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span
                          data-testid="mmr-override-delta"
                          className="text-xs font-mono text-amber-200"
                        >
                          {autofillDefault.toLocaleString()} → {watchedMmr.toLocaleString()} (
                          {watchedMmr > autofillDefault ? '+' : ''}
                          {(watchedMmr - autofillDefault).toLocaleString()},{' '}
                          {Math.round(overrideDeltaPct * 100)}%)
                        </span>
                        <div className="flex gap-1.5">
                          <SecondaryButton
                            type="button"
                            size="sm"
                            color="emerald"
                            onClick={() => setOverrideConfirmed(true)}
                            disabled={overrideConfirmed}
                            data-testid="accept-mmr-change"
                          >
                            {overrideConfirmed ? 'Confirmed' : 'Accept change'}
                          </SecondaryButton>
                          <SecondaryButton
                            type="button"
                            size="sm"
                            color="red"
                            onClick={() => {
                              field.onChange(autofillDefault);
                              setOverrideConfirmed(false);
                            }}
                            data-testid="reject-mmr-change"
                          >
                            Reject change
                          </SecondaryButton>
                        </div>
                      </div>
                      {!overrideConfirmed && (
                        <p className="mt-1 text-[11px] text-amber-300/80">
                          Approval is locked until you confirm — this is more than{' '}
                          {Math.round(OVERRIDE_THRESHOLD * 100)}% off the autofilled MMR.
                        </p>
                      )}
                    </div>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter className="flex-col-reverse sm:flex-row gap-2">
              <DestructiveButton
                type="button"
                onClick={() => onOpenChange(false)}
                disabled={isApproving || isRejecting}
                data-testid="mmr-modal-close"
              >
                Close
              </DestructiveButton>
              {onReject && (
                <ConfirmButton
                  type="button"
                  variant="destructive"
                  loading={isRejecting}
                  disabled={isApproving}
                  onClick={() => onReject(signup.id)}
                  data-testid="mmr-modal-reject"
                >
                  Reject
                </ConfirmButton>
              )}
              <SubmitButton
                loading={isApproving}
                disabled={isRejecting || (needsConfirm && !overrideConfirmed)}
                data-testid="mmr-modal-approve"
              >
                Approve
              </SubmitButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
