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
import { ConfirmDialog } from '~/components/ui/dialogs';
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
  SubmitButton,
} from '~/components/ui/buttons';
import { cn } from '~/lib/utils';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { RankSignalsCard } from '~/components/events/games/RankSignalsCard';
import type { EventSignupType } from '~/components/events/schemas';

const LARGE_CHANGE_THRESHOLD = 0.2;

const mmrSchema = z.object({
  mmr: z.number({ coerce: true }).int().min(0, 'MMR must be positive').max(20000, 'MMR too high'),
});
type MmrFormValues = z.infer<typeof mmrSchema>;

interface MmrApprovalModalProps {
  signup: EventSignupType | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApprove: (signupId: number, mmr: number) => void;
  onReject?: (signupId: number) => void;
  isApproving?: boolean;
  isRejecting?: boolean;
}

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
  const [confirmOpen, setConfirmOpen] = useState(false);
  const form = useForm<MmrFormValues>({
    resolver: zodResolver(mmrSchema),
    defaultValues: { mmr: 0 },
  });

  // Reset form when signup changes. suggested_mmr is now self-report-first
  // (see backend events.mmr_suggestions.suggest_mmr).
  useEffect(() => {
    if (signup && open) {
      form.reset({ mmr: signup.suggested_mmr });
      setConfirmOpen(false);
    }
  }, [signup, open]);

  const watchedMmr = form.watch('mmr');
  const priorMmr = signup?.org_user_mmr ?? null;
  const hasDelta =
    priorMmr != null && Number.isFinite(watchedMmr) && watchedMmr !== priorMmr;
  const deltaAmount = hasDelta ? watchedMmr - priorMmr! : 0;
  const deltaPct =
    priorMmr != null && priorMmr > 0 && Number.isFinite(watchedMmr)
      ? Math.abs(watchedMmr - priorMmr) / priorMmr
      : 0;
  const isLargeChange = hasDelta && deltaPct >= LARGE_CHANGE_THRESHOLD;

  if (!signup) return null;

  const profile = signup.dota_profile;
  const user = signup.user_data;
  const playerName = user ? DisplayName(user) : signup.username ?? `User #${signup.user}`;

  const screenshotUrl = profile?.rank_screenshot ?? profile?.battlecup_screenshot ?? null;

  // Rank-status badge — values come from PlayerDotaProfile.rank_status:
  // 'active' | 'previous' | 'never'. Earlier mapping checked for 'ranked' /
  // 'expired' (never set anywhere) and fell every profile through to "Never
  // Ranked" — including active and previously-ranked players.
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

  // Form submit opens the confirm dialog rather than approving directly.
  // Final approval is always preceded by an explicit "yes I mean it" step,
  // which doubles as a recap (player + MMR + delta) for the admin.
  const handleSubmit = (_values: MmrFormValues) => {
    setConfirmOpen(true);
  };

  const handleConfirmApproval = () => {
    onApprove(signup.id, form.getValues('mmr'));
    setConfirmOpen(false);
  };

  const confirmDescription = (() => {
    const mmrText = `${watchedMmr.toLocaleString()} MMR`;
    if (priorMmr == null) {
      return `Approve ${playerName} with ${mmrText}? No prior MMR is on file for this org.`;
    }
    if (!hasDelta) {
      return `Approve ${playerName} with ${mmrText}? Same as the previously approved MMR.`;
    }
    const deltaSign = deltaAmount > 0 ? '+' : '';
    const pctText = priorMmr > 0 ? `, ${Math.round(deltaPct * 100)}%` : '';
    return (
      `Approve ${playerName} with ${mmrText}? ` +
      `Previously approved was ${priorMmr.toLocaleString()} ` +
      `(${deltaSign}${deltaAmount.toLocaleString()}${pctText}).` +
      (isLargeChange
        ? ` This is more than ${Math.round(LARGE_CHANGE_THRESHOLD * 100)}% off the prior MMR — confirm this is intentional.`
        : '')
    );
  })();

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md max-h-[90vh] overflow-y-auto">
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

          <RankSignalsCard signup={signup} />

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
                    {hasDelta && (
                      <div
                        data-testid="mmr-delta"
                        className={cn(
                          'mt-2 rounded-md border px-3 py-2 text-xs font-mono',
                          isLargeChange
                            ? 'border-amber-500/40 bg-amber-500/5 text-amber-200'
                            : 'border-border/60 bg-base-300 text-muted-foreground',
                        )}
                      >
                        <span data-testid="mmr-delta-text">
                          {priorMmr!.toLocaleString()} → {watchedMmr.toLocaleString()} (
                          {deltaAmount > 0 ? '+' : ''}
                          {deltaAmount.toLocaleString()}
                          {priorMmr! > 0 ? `, ${Math.round(deltaPct * 100)}%` : ''})
                        </span>
                        {isLargeChange && (
                          <p className="mt-1 text-[11px] text-amber-300/80">
                            This is more than {Math.round(LARGE_CHANGE_THRESHOLD * 100)}% off
                            the previously approved MMR — you'll be asked to confirm.
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
                  disabled={isRejecting}
                  data-testid="mmr-modal-approve"
                >
                  Approve
                </SubmitButton>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={isLargeChange ? 'Confirm large MMR change' : 'Confirm approval'}
        description={confirmDescription}
        confirmLabel={isLargeChange ? 'Approve anyway' : 'Approve'}
        variant={isLargeChange ? 'warning' : 'default'}
        isLoading={isApproving}
        onConfirm={handleConfirmApproval}
        confirmTestId="mmr-confirm-approve"
        cancelTestId="mmr-confirm-cancel"
      />
    </>
  );
}
