import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import {
  StaffReasonField,
  useStaffReasonForm,
} from '~/components/events/StaffReasonField';
import { RankSignalsCard } from '~/components/events/games/RankSignalsCard';
import type { EventSignupType } from '~/components/events/schemas';
import {
  DEFAULT_MMR_BOUNDS,
  GAME_LABEL,
  GAME_MMR_BOUNDS,
  GAME_TYPE,
  type GameTypeValue,
} from '~/components/game/constants';
import {
  LARGE_MMR_CHANGE_THRESHOLD,
  computeMmrDelta,
} from '~/components/game/mmrDelta';
import { Badge } from '~/components/ui/badge';
import {
  CancelButton,
  ConfirmButton,
  DotabuffButton,
  SubmitButton,
  brandDialogPanel,
} from '~/components/ui/buttons';
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
import { SteamVerificationBadge } from '~/components/user/SteamVerificationBadge';
import { UserAvatar } from '~/components/user/UserAvatar';
import { UserStrip } from '~/components/user/UserStrip';
import { DisplayName } from '~/components/user/avatar';
import type { UserType } from '~/components/user/types';
import { useContextGameType } from '~/hooks/useGameType';
import { cn } from '~/lib/utils';

// 0 means "Not added" for non-Dota games, so they require at least 1; Dota allows 0.
function buildMmrSchema(gameType: GameTypeValue) {
  const [lo, hi] = GAME_MMR_BOUNDS[gameType] ?? DEFAULT_MMR_BOUNDS;
  const min = gameType === GAME_TYPE.DOTA2 ? lo : Math.max(lo, 1);
  return z.object({
    mmr: z.preprocess(
      (v) =>
        v === '' || v === null || (typeof v === 'number' && Number.isNaN(v))
          ? undefined
          : v,
      z.coerce
        .number({ error: 'MMR is required' })
        .int()
        .min(
          min,
          min > 0 ? `MMR must be at least ${min}` : 'MMR must be positive',
        )
        .max(hi, 'MMR too high'),
    ),
  });
}
type MmrSchema = ReturnType<typeof buildMmrSchema>;
type MmrFormValues = z.infer<MmrSchema>;

interface MmrApprovalModalProps {
  signup: EventSignupType | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApprove: (
    signupId: number,
    mmr: number,
    reason: string,
  ) => Promise<boolean>;
  reasonMode?: 'required' | 'optional';
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
  reasonMode = 'optional',
}: MmrApprovalModalProps) {
  const gameType = useContextGameType();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [approvedMmr, setApprovedMmr] = useState<number | null>(null);
  const reasonRequired = reasonMode === 'required';
  const reasonForm = useStaffReasonForm(
    reasonRequired,
    signup?.id,
    confirmOpen,
  );
  const inFlight = useRef(false);
  const ignoreClose = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  const mmrSchema = useMemo(() => buildMmrSchema(gameType), [gameType]);
  const formId = useId();
  // 3-generic useForm because z.coerce.number() genuinely splits input/output:
  // input is `unknown` (coerce accepts anything), output is `number`.
  // See https://github.com/react-hook-form/resolvers/issues/792.
  const form = useForm<z.input<MmrSchema>, unknown, MmrFormValues>({
    resolver: zodResolver(mmrSchema),
    defaultValues: { mmr: '' },
  });

  // Reset when a different signup opens, not when the same row refetches.
  // suggested_mmr is self-report-first (see backend events.mmr_suggestions.suggest_mmr).
  const signupId = signup?.id;
  useEffect(() => {
    if (signup && open) {
      form.reset({ mmr: signup.suggested_mmr ?? '' });
      setConfirmOpen(false);
      setApprovedMmr(null);
    }
  }, [signupId, open]);

  const rawMmr = form.watch('mmr');
  const hasValue = typeof rawMmr === 'number' && Number.isFinite(rawMmr);
  const watchedMmr = hasValue ? rawMmr : 0;
  const priorMmr = signup?.org_user_mmr ?? null;
  const delta =
    priorMmr != null && hasValue ? computeMmrDelta(priorMmr, watchedMmr) : null;
  const hasDelta = delta != null && delta.delta !== 0;
  const deltaAmount = hasDelta ? delta.delta : 0;
  const deltaPct = delta?.pct ?? 0;
  const isLargeChange = delta?.isLarge ?? false;

  if (!signup) return null;

  const profile = signup.dota_profile;
  const user = signup.user_data;
  const playerName = user
    ? DisplayName(user)
    : (signup.username ?? `User #${signup.user}`);

  const screenshotUrl =
    profile?.rank_screenshot ?? profile?.battlecup_screenshot ?? null;

  // Rank-status badge — values come from PlayerDotaProfile.rank_status:
  // 'active' | 'previous' | 'never'.
  const rankStatusBadge = profile ? (
    profile.rank_status === 'active' ? (
      <Badge
        variant="outline"
        className="px-1.5 py-0 text-xs font-medium text-rank-ranked border-rank-ranked/30"
      >
        Active
      </Badge>
    ) : profile.rank_status === 'previous' ? (
      <Badge
        variant="outline"
        className="px-1.5 py-0 text-xs font-medium text-rank-ranked border-rank-ranked/30"
      >
        Previous
      </Badge>
    ) : (
      <Badge
        variant="outline"
        className="px-1.5 py-0 text-xs font-medium text-rank-unranked border-rank-unranked/30"
      >
        Never Ranked
      </Badge>
    )
  ) : null;

  // Form submit opens the confirm dialog rather than approving directly.
  // Final approval is always preceded by an explicit "yes I mean it" step,
  // which doubles as a recap (player + MMR + delta) for the admin.
  const handleSubmit = (values: MmrFormValues) => {
    setApprovedMmr(values.mmr);
    setConfirmOpen(true);
  };

  const handleConfirmApproval = async (fromDialog: boolean) => {
    if (approvedMmr == null || isApproving || inFlight.current) return;
    inFlight.current = true;
    setSubmitting(true);
    let success = false;
    try {
      await reasonForm.handleSubmit(async ({ reason }) => {
        success = await onApprove(signup.id, approvedMmr, reason);
      })();
      if (success) setConfirmOpen(false);
    } finally {
      // ConfirmDialog otherwise closes even when approval was refused.
      ignoreClose.current = fromDialog && !success;
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  const deltaSummary = (() => {
    const mmrText = `${watchedMmr.toLocaleString()} MMR`;
    if (priorMmr == null) {
      return `Approving with ${mmrText}. No prior MMR is on file for this org.`;
    }
    if (!hasDelta) {
      return `Approving with ${mmrText}. Same as the previously approved MMR.`;
    }
    const deltaSign = deltaAmount > 0 ? '+' : '';
    const pctText = priorMmr > 0 ? `, ${Math.round(deltaPct * 100)}%` : '';
    const base =
      `Approving with ${mmrText}. ` +
      `Previously approved was ${priorMmr.toLocaleString()} ` +
      `(${deltaSign}${deltaAmount.toLocaleString()}${pctText}).`;
    if (isLargeChange) {
      return (
        base +
        ` This is more than ${Math.round(LARGE_MMR_CHANGE_THRESHOLD * 100)}% off the prior MMR — confirm this is intentional.`
      );
    }
    return base;
  })();

  // Show the MMR being approved on the strip's badge — acts as a visual
  // recap alongside the textual summary below.
  const stripUser = user ? ({ ...user, mmr: watchedMmr } as UserType) : null;

  const confirmDescription = (
    <div className="flex flex-col gap-3">
      {stripUser ? (
        <UserStrip
          user={stripUser}
          showBorder={false}
          className={brandDialogPanel}
          data-testid="mmr-confirm-user-strip"
        />
      ) : null}
      <p data-testid="mmr-confirm-summary">{deltaSummary}</p>
    </div>
  );

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md max-h-[90svh] grid-cols-[minmax(0,1fr)] overflow-y-auto">
          <DialogHeader>
            <div className="flex items-center gap-3">
              <UserAvatar
                user={user ?? undefined}
                src={signup.user_avatar ?? undefined}
                size="lg"
              />
              <div className="min-w-0 flex-1">
                <DialogTitle className="text-lg truncate">
                  {playerName}
                </DialogTitle>
                <DialogDescription className="flex items-center gap-1.5 mt-0.5">
                  {gameType === GAME_TYPE.DOTA2
                    ? (rankStatusBadge ?? 'No Dota profile')
                    : null}
                </DialogDescription>
              </div>
              {gameType === GAME_TYPE.DOTA2 && (
                <DotabuffButton
                  steamAccountId={user?.steam_account_id}
                  responsive={false}
                  size="sm"
                />
              )}
            </div>
            {user?.steam_account_id ? (
              <div
                className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground"
                data-testid="mmr-modal-friend-id"
              >
                <span>Friend ID {user.steam_account_id}</span>
                <SteamVerificationBadge
                  userPk={user.pk ?? signup.user}
                  steamAccountId={user.steam_account_id}
                  verified={user.steam_account_verified ?? false}
                  verifiedOrgName={user.steam_account_verified_org_name}
                  verifiedAt={user.steam_account_verified_at}
                  existsChecked={user.steam_account_exists_checked ?? false}
                  canVerify={signup.can_verify_steam_account ?? false}
                  staffView
                  showDotabuff={false}
                />
              </div>
            ) : null}
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
            <form
              id={formId}
              onSubmit={form.handleSubmit(handleSubmit)}
              className="space-y-4"
            >
              <FormField
                control={form.control}
                name="mmr"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel data-testid="mmr-modal-game-title">
                      Set {GAME_LABEL[gameType]} org MMR
                    </FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        placeholder="e.g. 3000"
                        data-testid="mmr-input"
                        {...field}
                        // field.value is `unknown` (coerce input). Narrow to
                        // number|'' so the <input> value prop typechecks.
                        value={
                          typeof field.value === 'number' ? field.value : ''
                        }
                        onChange={(e) =>
                          field.onChange(
                            e.target.value === '' ? '' : e.target.valueAsNumber,
                          )
                        }
                      />
                    </FormControl>
                    {gameType === GAME_TYPE.DOTA2 &&
                      signup.suggested_mmr_range != null &&
                      signup.suggested_mmr_range_source !== 'fallback' && (
                        <p
                          data-testid="suggested-range-helper"
                          className="text-xs text-muted-foreground font-mono mt-1"
                        >
                          Suggested range:{' '}
                          {signup.suggested_mmr_range[0].toLocaleString()}
                          &ndash;
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
                            ? 'border-warning/40 bg-warning/5 text-warning'
                            : 'border-border/60 bg-base-300 text-muted-foreground',
                        )}
                      >
                        <span data-testid="mmr-delta-text">
                          {priorMmr!.toLocaleString()} →{' '}
                          {watchedMmr.toLocaleString()} (
                          {deltaAmount > 0 ? '+' : ''}
                          {deltaAmount.toLocaleString()}
                          {priorMmr! > 0
                            ? `, ${Math.round(deltaPct * 100)}%`
                            : ''}
                          )
                        </span>
                        {isLargeChange && (
                          <p className="mt-1 text-[11px] text-warning/80">
                            This is more than{' '}
                            {Math.round(LARGE_MMR_CHANGE_THRESHOLD * 100)}% off
                            the previously approved MMR — you'll be asked to
                            confirm.
                          </p>
                        )}
                      </div>
                    )}
                    <FormMessage />
                  </FormItem>
                )}
              />
            </form>
          </Form>

          <DialogFooter className="sticky -bottom-6 -mx-6 -mb-6 flex-row justify-end border-t border-border bg-background/95 px-6 py-4 backdrop-blur">
            <CancelButton
              type="button"
              onClick={() => onOpenChange(false)}
              disabled={isApproving || isRejecting}
              data-testid="mmr-modal-close"
            >
              Close
            </CancelButton>
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
              form={formId}
              loading={isApproving}
              disabled={isRejecting}
              data-testid="mmr-modal-approve"
            >
              Approve
            </SubmitButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && ignoreClose.current) {
            ignoreClose.current = false;
            return;
          }
          if (!nextOpen && inFlight.current) return;
          setConfirmOpen(nextOpen);
        }}
        title={isLargeChange ? 'Confirm large MMR change' : 'Confirm approval'}
        description={confirmDescription}
        confirmLabel={isLargeChange ? 'Approve anyway' : 'Approve'}
        variant={isLargeChange ? 'warning' : 'default'}
        isLoading={isApproving || submitting}
        confirmDisabled={
          !reasonForm.formState.isValid || isApproving || submitting
        }
        onConfirm={() => handleConfirmApproval(true)}
        bodyContent={
          <Form {...reasonForm}>
            <StaffReasonField
              form={reasonForm}
              required={reasonRequired}
              onSubmit={() => handleConfirmApproval(false)}
            />
          </Form>
        }
        confirmTestId="mmr-confirm-approve"
        cancelTestId="mmr-confirm-cancel"
      />
    </>
  );
}
