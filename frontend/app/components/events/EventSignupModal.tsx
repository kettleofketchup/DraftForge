'use client';
import { useMemo } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMediaQuery } from '@uidotdev/usehooks';

import { Dialog, DialogContent, DialogTitle, DialogHeader } from '~/components/ui/dialog';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '~/components/ui/sheet';
import { Form } from '~/components/ui/form';
import { Badge } from '~/components/ui/badge';
import { SubmitButton, CancelButton } from '~/components/ui/buttons';
import { extractApiError } from '~/lib/apiError';
import { cn } from '~/lib/utils';

import { buildSignupPatchSchema, type SignupInputPatch } from './EventSignupModal/schema';
import { toPatch } from './EventSignupModal/toPatch';
import { FriendIdField } from './EventSignupModal/FriendIdField';
import { RankStatusRadioGroup } from './EventSignupModal/RankStatusRadioGroup';
import { PositionPickerGrid } from './EventSignupModal/PositionPickerGrid';
import { RankDetailFields } from './EventSignupModal/RankDetailFields';
import { ScreenshotUrlField } from './EventSignupModal/ScreenshotUrlField';
import { PrefilledSummaryChip } from './EventSignupModal/PrefilledSummaryChip';
import { useSignupMutation } from '~/hooks/useEvent';

import { GameType, type EventType } from './schemas';
import type { DotaProfileData } from '~/components/user';

const POSITION_LABELS: Record<number, string> = {
  1: 'Carry',
  2: 'Mid',
  3: 'Offlane',
  4: 'Soft Support',
  5: 'Hard Support',
};

function positionsSummary(positions: DotaProfileData['positions']): string {
  const picked: number[] = [];
  if (positions.pos_1) picked.push(1);
  if (positions.pos_2) picked.push(2);
  if (positions.pos_3) picked.push(3);
  if (positions.pos_4) picked.push(4);
  if (positions.pos_5) picked.push(5);
  return picked.map((n) => POSITION_LABELS[n]).join(' · ');
}

export type EventSignupModalProps = {
  event: EventType;
  intent: 'rsvp' | 'tentative';
  profile: DotaProfileData | null | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function EventSignupModal({
  event,
  intent,
  profile,
  open,
  onOpenChange,
}: EventSignupModalProps) {
  const isDesktop = useMediaQuery('(min-width: 768px)');

  const schema = useMemo(
    () => buildSignupPatchSchema(event, profile),
    // Specific deps that drive section visibility:
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      event.id,
      event.require_steam_id,
      event.allow_active_mmr,
      event.allow_previous_rank,
      event.allow_battlecup_rating,
      event.discord_require_rank_screenshot,
      event.discord_require_battlecup_screenshot,
      profile?.unverified_friend_id != null,
      profile?.rank_status,
      profile?.rank_medal != null,
      profile?.battle_cup_tier != null,
      profile?.positions ? Object.values(profile.positions).some(Boolean) : false,
      profile?.rank_screenshot != null,
      profile?.battlecup_screenshot != null,
    ],
  );

  // Seed defaults from profile so prefilled-chip subcomponents (which mount
  // inside <CollapsibleContent>) register valid values with RHF immediately.
  const profilePositions = profile?.positions
    ? [
        profile.positions.pos_1 && 1,
        profile.positions.pos_2 && 2,
        profile.positions.pos_3 && 3,
        profile.positions.pos_4 && 4,
        profile.positions.pos_5 && 5,
      ].filter((v): v is number => typeof v === 'number')
    : [];

  const splitMedal = useMemo(() => {
    const m = profile?.rank_medal ?? '';
    if (!m) return { medal: '', star: '' };
    if (m === 'Immortal') return { medal: 'Immortal', star: '' };
    const parts = m.split(' ');
    return { medal: parts[0] ?? '', star: parts[1] ?? '' };
  }, [profile?.rank_medal]);

  const form = useForm<
    SignupInputPatch & { rank_medal_medal?: string; rank_medal_star?: string }
  >({
    resolver: zodResolver(schema as never),
    mode: 'onChange',
    shouldUnregister: true,
    defaultValues: {
      unverified_friend_id: profile?.unverified_friend_id ?? '',
      positions: profilePositions,
      rank_status: profile?.rank_status as 'active' | 'previous' | 'never' | undefined,
      rank_medal_medal: splitMedal.medal,
      rank_medal_star: splitMedal.star,
      rank_medal: profile?.rank_medal ?? '',
      battle_cup_tier: profile?.battle_cup_tier ?? undefined,
      rank_screenshot: profile?.rank_screenshot ?? '',
      battlecup_screenshot: profile?.battlecup_screenshot ?? '',
    } as never,
  });

  const watchedRankStatus = useWatch({ control: form.control, name: 'rank_status' });
  const mutation = useSignupMutation(event.id);

  const onSubmit = form.handleSubmit(async (values) => {
    const merged: SignupInputPatch = { ...(values as SignupInputPatch) };
    const v = values as Record<string, unknown>;
    if (v.rank_medal_medal) {
      const medal = v.rank_medal_medal as string;
      const star = v.rank_medal_star as string | undefined;
      (merged as Record<string, unknown>).rank_medal =
        medal === 'Immortal' ? 'Immortal' : `${medal} ${star ?? '1'}`;
    }
    delete (merged as Record<string, unknown>).rank_medal_medal;
    delete (merged as Record<string, unknown>).rank_medal_star;

    const patch = toPatch(merged, profile);
    try {
      await mutation.mutateAsync({ intent, profile: patch });
      onOpenChange(false);
    } catch {
      // Error surfaces via mutation.error inline; modal stays open for retry.
    }
  });

  const isDota = event.game_type === GameType.DOTA2;
  const showFriendId = event.require_steam_id;
  const friendIdPrefilled = !!profile?.unverified_friend_id;
  const showRankStatus = isDota;
  const rankStatusPrefilled = !!profile?.rank_status;
  const hasPos = profile?.positions
    ? Object.values(profile.positions).some(Boolean)
    : false;
  const showPositions = isDota;
  const positionsPrefilled = hasPos;
  const showRankDetail = isDota && !!watchedRankStatus;
  const rankDetailPrefilled =
    !!profile?.rank_medal || profile?.battle_cup_tier != null;
  const screenshotForActive =
    isDota &&
    event.discord_require_rank_screenshot &&
    (watchedRankStatus === 'active' || watchedRankStatus === 'previous');
  const screenshotForActivePrefilled = !!profile?.rank_screenshot;
  const screenshotForBC =
    isDota &&
    event.discord_require_battlecup_screenshot &&
    watchedRankStatus === 'never';
  const screenshotForBCPrefilled = !!profile?.battlecup_screenshot;

  let sectionNum = 0;
  const heading = (label: string) => {
    sectionNum += 1;
    return (
      <h3 className="text-sm font-semibold border-t border-border pt-3">
        {sectionNum}. {label}
      </h3>
    );
  };

  function withPrefill(
    prefilled: boolean,
    summary: string,
    testId: string,
    editable: React.ReactNode,
  ): React.ReactNode {
    if (prefilled) {
      return (
        <PrefilledSummaryChip testId={testId} summary={summary}>
          {editable}
        </PrefilledSummaryChip>
      );
    }
    return editable;
  }

  const title =
    intent === 'rsvp' ? `Sign Up for ${event.name}` : `Mark Tentative for ${event.name}`;
  const banner =
    intent === 'rsvp'
      ? "You're committing to play this event. We'll add you to the signup list."
      : "You're marking yourself tentative — we count you as interested but not committed.";

  const errorMessage = mutation.error
    ? extractApiError(mutation.error) || 'Something went wrong'
    : null;

  const scrollableBody = (
    <div
      className="flex flex-col gap-4 overflow-y-auto pb-4"
      data-testid="event-signup-modal-body"
    >
      <div className="flex items-center gap-2">
        <Badge variant={intent === 'rsvp' ? 'default' : 'secondary'} className="shrink-0">
          {intent === 'rsvp' ? 'Committed' : 'Tentative'}
        </Badge>
        <span
          role="status"
          aria-live="polite"
          className="text-sm text-muted-foreground"
        >
          {banner}
        </span>
      </div>

      {showFriendId && (
        <section className="flex flex-col gap-2">
          {heading('Steam Friend ID')}
          {withPrefill(
            friendIdPrefilled,
            profile?.unverified_friend_id ?? '',
            'signup-prefilled-summary-friend-id',
            <FriendIdField control={form.control as never} />,
          )}
        </section>
      )}
      {showRankStatus && (
        <section className="flex flex-col gap-2">
          {heading('Rank Status')}
          {withPrefill(
            rankStatusPrefilled,
            profile?.rank_status ?? '',
            'signup-prefilled-summary-rank-status',
            <RankStatusRadioGroup control={form.control as never} event={event} />,
          )}
        </section>
      )}
      {showPositions && (
        <section className="flex flex-col gap-2">
          {heading('Preferred Positions')}
          {withPrefill(
            positionsPrefilled,
            profile?.positions ? positionsSummary(profile.positions) : '',
            'signup-prefilled-summary-positions',
            <PositionPickerGrid control={form.control as never} />,
          )}
        </section>
      )}
      {showRankDetail && (
        <section className="flex flex-col gap-2">
          {heading('Rank Detail')}
          {withPrefill(
            rankDetailPrefilled,
            profile?.rank_medal ||
              (profile?.battle_cup_tier
                ? `Battle Cup Tier ${profile.battle_cup_tier}`
                : ''),
            'signup-prefilled-summary-rank-detail',
            <RankDetailFields control={form.control as never} />,
          )}
        </section>
      )}
      {screenshotForActive && (
        <section className="flex flex-col gap-2">
          {heading('MMR Screenshot')}
          {withPrefill(
            screenshotForActivePrefilled,
            'On file',
            'signup-prefilled-summary-screenshot',
            <ScreenshotUrlField
              control={form.control as never}
              name="rank_screenshot"
            />,
          )}
        </section>
      )}
      {screenshotForBC && (
        <section className="flex flex-col gap-2">
          {heading('Battle Cup Screenshot')}
          {withPrefill(
            screenshotForBCPrefilled,
            'On file',
            'signup-prefilled-summary-screenshot',
            <ScreenshotUrlField
              control={form.control as never}
              name="battlecup_screenshot"
              label="Battle Cup Screenshot URL"
            />,
          )}
        </section>
      )}
      {errorMessage && (
        <div
          data-testid="event-signup-error"
          role="alert"
          className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
        >
          {errorMessage}
        </div>
      )}
    </div>
  );

  const stickyFooter = (
    <div className="sticky bottom-0 -mx-6 mt-2 flex justify-end gap-2 border-t border-border bg-background px-6 py-3">
      <CancelButton
        type="button"
        onClick={() => onOpenChange(false)}
        disabled={mutation.isPending}
        data-testid="event-signup-cancel-btn"
      >
        Cancel
      </CancelButton>
      <SubmitButton
        loading={mutation.isPending}
        disabled={!form.formState.isValid}
        data-testid="event-signup-submit-btn"
      >
        {intent === 'rsvp' ? 'Sign Up' : 'Mark Tentative'}
      </SubmitButton>
    </div>
  );

  const body = (
    <Form {...form}>
      <form
        onSubmit={onSubmit}
        className="flex flex-col"
        noValidate
        data-testid="event-signup-modal"
      >
        {scrollableBody}
        {stickyFooter}
      </form>
    </Form>
  );

  if (isDesktop) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="flex max-h-[90vh] flex-col">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          {body}
        </DialogContent>
      </Dialog>
    );
  }
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="bottom"
        className={cn('flex flex-col', '[height:100svh]', 'max-h-[100dvh]')}
      >
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
        </SheetHeader>
        {body}
      </SheetContent>
    </Sheet>
  );
}
