'use client';
import { useMemo } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMediaQuery } from '@uidotdev/usehooks';

import { Dialog, DialogContent, DialogTitle, DialogHeader } from '~/components/ui/dialog';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '~/components/ui/sheet';
import { Form } from '~/components/ui/form';
import { Badge } from '~/components/ui/badge';
import { ScrollArea } from '~/components/ui/scroll-area';
import { SubmitButton, CancelButton } from '~/components/ui/buttons';
import { extractApiError } from '~/lib/apiError';
import { cn } from '~/lib/utils';

import { buildSignupPatchSchema, type SignupInputPatch } from './EventSignupModal/schema';
import { toPatch } from './EventSignupModal/toPatch';
import { isRankSectionComplete } from './EventSignupModal/evaluateSignupGap';
import { FriendIdField } from './EventSignupModal/FriendIdField';
import { RankStatusRadioGroup } from './EventSignupModal/RankStatusRadioGroup';
import { RankDetailFields } from './EventSignupModal/RankDetailFields';
import { ScreenshotUrlField } from './EventSignupModal/ScreenshotUrlField';
import { PrefilledSummaryChip } from './EventSignupModal/PrefilledSummaryChip';
import { useSignupMutation } from '~/hooks/useEvent';
import { PositionFormFields } from '~/pages/profile/forms/position';
import {
  POSITION_LABELS as DOTA_POSITION_LABELS,
  positionKeys,
} from '~/components/user/positions/positionEdit';
import { useUserStore } from '~/store/userStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { selectPositions } from '~/store/selectPositions';

import { type EventType } from './schemas';
import { GAME_TYPE } from '~/components/game/constants';
import type { DotaProfileData } from '~/components/user';

type PositionPriorities = {
  carry: number;
  mid: number;
  offlane: number;
  soft_support: number;
  hard_support: number;
};

function positionsSummary(positions: PositionPriorities | undefined | null): string {
  if (!positions) return '';
  // Sort by priority asc (1=Favorite first) then show label · "(rating: N)" for non-zero.
  const picked = positionKeys
    .filter((k) => positions[k] > 0)
    .sort((a, b) => positions[a] - positions[b])
    .map((k) => DOTA_POSITION_LABELS[k]);
  return picked.join(' · ');
}

// Exported so smoke tests can verify intent → title interpolation without
// having to render the modal (its body lives in a Radix portal that
// renderToStaticMarkup can't reach).
export function buildSignupModalTitle(
  intent: 'rsvp' | 'tentative',
  eventName: string,
): string {
  return intent === 'rsvp'
    ? `Sign Up for ${eventName}`
    : `Mark Tentative for ${eventName}`;
}

export function buildSignupModalBanner(intent: 'rsvp' | 'tentative'): string {
  return intent === 'rsvp'
    ? "You're committing to play this event. We'll add you to the signup list."
    : "You're marking yourself tentative — we count you as interested but not committed.";
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

  // Read the current user's positions BEFORE useMemo so the schema can consult
  // it. Route through the gameType-aware selector over the list-populated entity
  // adapter (userStore upserts currentUser into the cache). Explicit
  // GAME_TYPE.DOTA2: these are user-wide Dota positions, read unconditionally
  // here regardless of the event's game; fall back to currentUser.positions when
  // the user isn't cached yet.
  const currentUserPk = useUserStore((s) => s.currentUser?.pk);
  const currentUserFallbackPositions = useUserStore(
    (s) => s.currentUser?.positions,
  ) as Partial<PositionPriorities> | undefined;
  const cachedPositions = useUserCacheStore((s) =>
    currentUserPk != null
      ? selectPositions(s, currentUserPk, GAME_TYPE.DOTA2)
      : undefined,
  );
  const currentUserPositions = (cachedPositions ??
    currentUserFallbackPositions) as Partial<PositionPriorities> | undefined;
  const userHasPos =
    !!currentUserPositions &&
    Object.values(currentUserPositions).some((v) => (v ?? 0) > 0);

  const schema = useMemo(
    () => buildSignupPatchSchema(event, profile, currentUserPositions),
    // Specific deps that drive section visibility:
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
      userHasPos,
    ],
  );

  // Seed defaults from the user's main position priorities (CustomUser.positions
  // — PositionsModel rated 0..5, same shape PositionForm uses on the edit-profile
  // page). The per-org PlayerDotaProfile.pos_N booleans are derived server-side.
  const defaultPositions: PositionPriorities = {
    carry: currentUserPositions?.carry ?? 0,
    mid: currentUserPositions?.mid ?? 0,
    offlane: currentUserPositions?.offlane ?? 0,
    soft_support: currentUserPositions?.soft_support ?? 0,
    hard_support: currentUserPositions?.hard_support ?? 0,
  };

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
      positions: defaultPositions,
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

    const patch = toPatch(merged, profile, currentUserPositions);
    try {
      await mutation.mutateAsync({ intent, profile: patch });
      onOpenChange(false);
    } catch (err) {
      // Error surfaces via mutation.error inline; modal stays open for retry.
      // Log non-mutation failures (e.g. network throw before request) so they're findable.
      console.error('[EventSignupModal] submit failed', err);
    }
  });

  const isDota = event.game_type === GAME_TYPE.DOTA2;
  const showFriendId = event.require_steam_id;
  const friendIdPrefilled = !!profile?.unverified_friend_id;
  const showRankStatus = isDota;
  // Same check evaluateSignupGap uses — default `rank_status="never"` from
  // get_or_create doesn't count as a real user pick.
  const rankStatusPrefilled = isRankSectionComplete(event, profile);
  // "Prefilled" if the user already has any non-zero priority on their main
  // profile — same rule the schema uses to decide whether positions is required.
  const hasPos = Object.values(defaultPositions).some((v) => v > 0);
  const showPositions = isDota;
  const positionsPrefilled = hasPos;
  const showRankDetail = isDota && !!watchedRankStatus;
  const rankDetailPrefilled =
    !!profile?.rank_medal || profile?.battle_cup_tier != null;
  // Screenshot only required for ACTIVE MMR (current rank claim must be
  // corroborated). "I had an MMR" relies on the medal+star showing the last
  // rank held — no current ladder screen to take.
  const screenshotForActive =
    isDota &&
    event.discord_require_rank_screenshot &&
    watchedRankStatus === 'active';
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

  const title = buildSignupModalTitle(intent, event.name);
  const banner = buildSignupModalBanner(intent);

  const errorMessage = mutation.error
    ? extractApiError(mutation.error) || 'Something went wrong'
    : null;

  const scrollableBody = (
    // shadcn ScrollArea wraps a Radix Viewport (which IS the scroll
    // container) with a brand-styled scrollbar. Playwright tests that target
    // fields below the fold MUST focus() the target before click() — the
    // Radix Viewport's overflow contract doesn't always respond to
    // Playwright's auto-scrollIntoView. focus() triggers the browser's
    // native scrollIntoView({block:'nearest'}) which DOES scroll the
    // Viewport correctly. See 12-event-signup-form.spec.ts for the
    // focus-before-click pattern.
    <ScrollArea
      // flex-1 min-h-0 takes remaining space inside the form column;
      // combined with overflow-hidden on the DialogContent (see below),
      // this gives the Radix Viewport a definite parent height so its
      // size-full resolves correctly, content actually clips inside the
      // Viewport, and the brand-styled scrollbar appears as expected.
      className="flex-1 min-h-0 -mx-6 px-6"
      data-testid="event-signup-modal-body"
    >
      <div className="flex flex-col gap-4 pb-4">
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
            positionsSummary(defaultPositions),
            'signup-prefilled-summary-positions',
            <PositionFormFields
              form={form as never}
              gridClassName="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full"
            />,
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
    </ScrollArea>
  );

  const stickyFooter = (
    // flex-none keeps the footer at the natural bottom of the flex-column form;
    // scrollableBody takes the remaining height with min-h-0 + flex-1 +
    // overflow-y-auto, so the footer is never visually overlapping content
    // (which broke clicks on radio cards near the bottom of short modals).
    <div className="-mx-6 mt-2 flex flex-none justify-end gap-2 border-t border-border bg-background px-6 py-3">
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
        className="flex min-h-0 flex-1 flex-col"
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
        {/* overflow-hidden: shadcn's default DialogContent doesn't clip its
            content, so without it long forms render past the dialog edge
            even when max-h-[90vh] is set. Clipping here lets the inner
            ScrollArea (Radix Viewport) get a definite height so size-full
            resolves, content overflow is contained, and the brand scrollbar
            appears. */}
        <DialogContent className="flex max-h-[90vh] flex-col overflow-hidden sm:max-w-2xl">
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
