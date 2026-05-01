import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

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
  SecondaryButton,
} from '~/components/ui/buttons';
import { cn } from '~/lib/utils';
import { UserAvatar } from '~/components/user/UserAvatar';
import { DisplayName } from '~/components/user/avatar';
import { RolePositions } from '~/components/user/positions';
import { dotaProfileToPositions } from '~/components/user/UserEventStrip';
import type { EventSignupType } from '~/components/events/schemas';

// ---------------------------------------------------------------------------
// MMR schema
// ---------------------------------------------------------------------------
const mmrSchema = z.object({
  mmr: z.number({ coerce: true }).int().min(0, 'MMR must be positive').max(20000, 'MMR too high'),
});
type MmrFormValues = z.infer<typeof mmrSchema>;

// ---------------------------------------------------------------------------
// Medal -> estimated MMR
// ---------------------------------------------------------------------------
const MEDAL_MMR: Record<string, number> = {
  Herald: 200,
  Guardian: 800,
  Crusader: 1400,
  Archon: 2200,
  Legend: 3000,
  Ancient: 3800,
  Divine: 4600,
  Immortal: 5500,
};

function estimateMmr(medal: string | null): number {
  if (!medal) return 0;
  const [name, starStr] = medal.split(' ');
  const base = MEDAL_MMR[name] ?? 0;
  const star = parseInt(starStr) || 1;
  return base + (star - 1) * 140;
}


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
  const form = useForm<MmrFormValues>({
    resolver: zodResolver(mmrSchema),
    defaultValues: { mmr: 0 },
  });

  // Reset form when signup changes. Prefer the previously admin-approved MMR
  // (org_user_mmr) over the user's self-reported PlayerDotaProfile.mmr.
  useEffect(() => {
    if (signup && open) {
      const profile = signup.dota_profile;
      const defaultMmr =
        signup.org_user_mmr ??
        profile?.mmr ??
        (profile ? estimateMmr(profile.rank_medal) : 0);
      form.reset({ mmr: defaultMmr });
    }
  }, [signup, open]);

  const watchedMmr = form.watch('mmr');
  const previousMmr = signup?.org_user_mmr ?? null;
  const mmrDelta =
    previousMmr != null && Number.isFinite(watchedMmr)
      ? watchedMmr - previousMmr
      : null;

  if (!signup) return null;

  const profile = signup.dota_profile;
  const user = signup.user_data;
  const playerName = user ? DisplayName(user) : signup.username ?? `User #${signup.user}`;

  // Screenshot URL (rank or battlecup)
  const screenshotUrl = profile?.rank_screenshot ?? profile?.battlecup_screenshot ?? null;

  // Build positions-compatible user for RolePositions
  const positionsUser = profile?.positions
    ? { ...({} as import('~/components/user/types').UserType), positions: dotaProfileToPositions(profile.positions) }
    : null;

  // Rank status badge
  const rankStatusBadge = profile ? (
    profile.rank_status === 'ranked' ? (
      <Badge variant="outline" className="px-1.5 py-0 text-xs font-medium text-amber-300 border-amber-500/30">
        Ranked
      </Badge>
    ) : profile.rank_status === 'expired' ? (
      <Badge variant="outline" className="px-1.5 py-0 text-xs font-medium text-amber-300 border-amber-500/30">
        Expired
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
            <div className="min-w-0">
              <DialogTitle className="text-lg truncate">{playerName}</DialogTitle>
              <DialogDescription className="flex items-center gap-1.5 mt-0.5">
                {rankStatusBadge ?? 'No Dota profile'}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Previously approved MMR (admin-set on OrgUser). Shown even when no
            PlayerDotaProfile exists, so admins can re-approve at the prior value. */}
        {signup.org_user_mmr != null && (
          <div className="bg-base-300 border border-border rounded-lg p-4 text-sm flex justify-between">
            <span className="text-muted-foreground">Previously Approved MMR</span>
            <span className="font-mono">{signup.org_user_mmr.toLocaleString()}</span>
          </div>
        )}

        {/* Profile summary (read-only) */}
        {profile && (
          <div className="bg-base-300 border border-border rounded-lg p-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Rank Status</span>
              <span className="capitalize">{profile.rank_status}</span>
            </div>

            {profile.rank_medal && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Medal</span>
                <Badge variant="outline" className="px-1.5 py-0 text-xs font-medium text-amber-300 border-amber-500/30">
                  {profile.rank_medal}
                </Badge>
              </div>
            )}

            <div className="flex justify-between">
              <span className="text-muted-foreground">Self-reported MMR</span>
              <span className="font-mono">
                {profile.mmr != null ? profile.mmr.toLocaleString() : '\u2014'}
              </span>
            </div>

            {positionsUser?.positions && (
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Positions</span>
                <RolePositions user={positionsUser as import('~/components/user/types').UserType} compact disableTooltips />
              </div>
            )}

            {profile.rank_status === 'never' && profile.battle_cup_tier != null && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Battle Cup Tier</span>
                <Badge variant="outline" className="px-1.5 py-0 text-xs font-medium text-blue-300 border-blue-500/30">
                  Tier {profile.battle_cup_tier}
                </Badge>
              </div>
            )}
          </div>
        )}

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
                      {...field}
                      onChange={(e) => field.onChange(e.target.valueAsNumber || 0)}
                    />
                  </FormControl>
                  {mmrDelta != null && mmrDelta !== 0 && (
                    <div className="mt-2 flex items-center justify-between gap-2 rounded-md border border-border/60 bg-base-300 px-3 py-2">
                      <span
                        data-testid="mmr-delta"
                        className={cn(
                          'text-xs font-mono',
                          mmrDelta > 0 ? 'text-emerald-400' : 'text-rose-400',
                        )}
                      >
                        {previousMmr!.toLocaleString()} → {watchedMmr.toLocaleString()} ({mmrDelta > 0 ? '+' : ''}
                        {mmrDelta.toLocaleString()})
                      </span>
                      <div className="flex gap-1.5">
                        <SecondaryButton
                          type="button"
                          size="sm"
                          color="emerald"
                          onClick={() => {
                            // Accept the change — already in form state, just acknowledge.
                            // No-op visually; included for explicit affordance.
                          }}
                          data-testid="accept-mmr-change"
                        >
                          Accept change
                        </SecondaryButton>
                        <SecondaryButton
                          type="button"
                          size="sm"
                          color="red"
                          onClick={() => field.onChange(previousMmr ?? 0)}
                          data-testid="reject-mmr-change"
                        >
                          Reject change
                        </SecondaryButton>
                      </div>
                    </div>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter className="flex-col-reverse sm:flex-row gap-2">
              <SecondaryButton
                type="button"
                onClick={() => onOpenChange(false)}
                disabled={isApproving || isRejecting}
                data-testid="mmr-modal-close"
              >
                Close
              </SecondaryButton>
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
              <ConfirmButton
                type="submit"
                variant="success"
                loading={isApproving}
                disabled={isRejecting}
                data-testid="mmr-modal-approve"
              >
                Approve
              </ConfirmButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
