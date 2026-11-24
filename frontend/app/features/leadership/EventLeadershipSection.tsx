import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import type { EventType } from '~/components/events/schemas';
import { PrimaryButton } from '~/components/ui/buttons';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getLogger } from '~/lib/logger';
import { leadershipAccess } from './access';
import { refusalCode, refusalMessage } from './errors';
import {
  useEventReviews,
  useLeadershipTraits,
  useUnvoidReview,
  useVoidReview,
} from './queries';
import {
  ReleaseResultsDialog,
  type ReleaseTarget,
} from './ReleaseResultsDialog';
import { ReviewModerationTable } from './ReviewModerationTable';
import type { EventCaptainReviews, ModerationReview } from './schemas';
import { VoidReviewDialog } from './VoidReviewDialog';

const log = getLogger('EventLeadershipSection');

export interface EventLeadershipSectionProps {
  event: Pick<EventType, 'id' | 'organization'>;
  access: OrgFeatureAccess;
}

export function EventLeadershipSection({
  event,
  access,
}: EventLeadershipSectionProps) {
  if (!leadershipAccess(access).canModerate) return null;
  return (
    <ModerationSection
      key={`${event.organization}:${event.id}`}
      orgId={event.organization}
      eventId={event.id}
      access={access}
    />
  );
}

function ModerationSection({
  orgId,
  eventId,
  access,
}: {
  orgId: number;
  eventId: number;
  access: OrgFeatureAccess;
}) {
  const reviews = useEventReviews(orgId, access, eventId, true);
  const traitsQuery = useLeadershipTraits(orgId, access);
  const voidMutation = useVoidReview(orgId, eventId);
  const unvoidMutation = useUnvoidReview(orgId, eventId);
  const [target, setTarget] = useState<ModerationReview | null>(null);
  const [voidError, setVoidError] = useState<string | null>(null);
  const [unvoidPk, setUnvoidPk] = useState<number | null>(null);
  const [releaseTarget, setReleaseTarget] = useState<ReleaseTarget | null>(
    null,
  );

  useEffect(() => {
    if (reviews.isError)
      log.warn('captain reviews failed to load', {
        orgId,
        eventId,
        code: refusalCode(reviews.error),
      });
  }, [reviews.isError, reviews.error, orgId, eventId]);

  const traits = useMemo(
    () => (traitsQuery.data ?? []).map(({ key, label }) => ({ key, label })),
    [traitsQuery.data],
  );

  const onVoid = useCallback((review: ModerationReview) => {
    setVoidError(null);
    setTarget(review);
  }, []);

  const { mutate: unvoid } = unvoidMutation;
  const onUnvoid = useCallback(
    (review: ModerationReview) => {
      setUnvoidPk(review.pk);
      unvoid(
        { reviewPk: review.pk },
        {
          onError: (err) => {
            log.warn('unvoid refused', { code: refusalCode(err) });
            toast.error(refusalMessage(err, 'unvoid'));
          },
          onSettled: () => setUnvoidPk(null),
        },
      );
    },
    [unvoid],
  );

  const onRelease = useCallback((captain: EventCaptainReviews) => {
    setReleaseTarget({ captains: [captain], explicit: true });
  }, []);

  const confirmVoid = (reason: string) => {
    if (!target) return;
    setVoidError(null);
    voidMutation.mutate(
      { reviewPk: target.pk, reason },
      {
        onSuccess: () => setTarget(null),
        onError: (err) => {
          log.warn('void refused', { code: refusalCode(err) });
          setVoidError(refusalMessage(err, 'moderate'));
        },
      },
    );
  };

  const captains = reviews.data?.captains ?? [];
  if (reviews.isSuccess && captains.length === 0) return null;
  const releasable = captains.filter((c) => c.can_release && !c.own_snapshot);
  const showReleaseAll =
    reviews.data?.require_staff_release === true && releasable.length > 0;

  return (
    <section
      className="mb-4 flex flex-col gap-4 rounded-lg border border-border p-4"
      data-testid="leadership-moderation"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold">Captain reviews</h2>
          <p className="text-sm text-muted-foreground">
            Moderators only. Raters are never shown to captains.
          </p>
        </div>
        {showReleaseAll && (
          <PrimaryButton
            type="button"
            className="min-h-11 shrink-0 sm:min-h-9"
            data-testid="leadership-release-all"
            onClick={() =>
              setReleaseTarget({ captains: releasable, explicit: false })
            }
          >
            Release all pending ({releasable.length})
          </PrimaryButton>
        )}
      </div>
      {reviews.isLoading && (
        <p className="text-sm text-muted-foreground">
          Loading captain reviews...
        </p>
      )}
      {reviews.isError && (
        <p
          className="text-sm text-destructive"
          data-testid="leadership-moderation-error"
        >
          {refusalMessage(reviews.error, 'moderate')}
        </p>
      )}
      {captains.map((captain) => (
        <ReviewModerationTable
          key={captain.org_user_id}
          captain={captain}
          viewerPk={access.viewerPk}
          traits={traits}
          onVoid={onVoid}
          onUnvoid={onUnvoid}
          pendingPk={unvoidPk}
          onRelease={onRelease}
        />
      ))}
      <VoidReviewDialog
        open={target !== null}
        onOpenChange={(open) => {
          if (!open && !voidMutation.isPending) setTarget(null);
        }}
        pending={voidMutation.isPending}
        error={voidError}
        onConfirm={confirmVoid}
      />
      <ReleaseResultsDialog
        orgId={orgId}
        eventId={eventId}
        target={releaseTarget}
        onClose={() => setReleaseTarget(null)}
      />
    </section>
  );
}
