import { useCallback, useMemo, useState } from 'react';
import { toast } from 'sonner';
import type { EventType } from '~/components/events/schemas';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getLogger } from '~/lib/logger';
import { refusalCode, refusalMessage } from './errors';
import { LEADERSHIP_EVENT_STATES } from './moderationColumns';
import {
  useEventReviews,
  useLeadershipTraits,
  useUnvoidReview,
  useVoidReview,
} from './queries';
import { ReviewModerationTable } from './ReviewModerationTable';
import type { ModerationReview } from './schemas';
import { VoidReviewDialog } from './VoidReviewDialog';

const log = getLogger('EventLeadershipSection');

export interface EventLeadershipSectionProps {
  event: Pick<EventType, 'id' | 'organization' | 'state'>;
  access: OrgFeatureAccess;
}

export function EventLeadershipSection({
  event,
  access,
}: EventLeadershipSectionProps) {
  const visible =
    access.canManageLeadership && LEADERSHIP_EVENT_STATES.has(event.state);
  if (!visible) return null;
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
  const voidMutation = useVoidReview(orgId, access, eventId);
  const unvoidMutation = useUnvoidReview(orgId, access, eventId);
  const [target, setTarget] = useState<ModerationReview | null>(null);
  const [voidError, setVoidError] = useState<string | null>(null);
  const [unvoidPk, setUnvoidPk] = useState<number | null>(null);

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
  if (captains.length === 0) return null;

  return (
    <section
      className="mb-4 flex flex-col gap-4 rounded-lg border border-border p-4"
      data-testid="leadership-moderation"
    >
      <div>
        <h2 className="text-lg font-semibold">Captain reviews</h2>
        <p className="text-sm text-muted-foreground">
          Admins only. Raters are never shown to captains.
        </p>
      </div>
      {captains.map((captain) => (
        <ReviewModerationTable
          key={captain.org_user_id}
          captain={captain}
          traits={traits}
          onVoid={onVoid}
          onUnvoid={onUnvoid}
          pendingPk={unvoidPk}
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
    </section>
  );
}
