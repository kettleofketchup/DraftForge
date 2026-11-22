import { useState } from 'react';
import type { EventType } from '~/components/events/schemas';
import type { OrgFeatureAccess } from '~/features/org-features';
import { leadershipAccess } from './access';
import { PendingReviewsCard } from './PendingReviewsCard';

export interface EventLeadershipBannerProps {
  event: Pick<EventType, 'id' | 'organization' | 'pending_captain_reviews'>;
  access: OrgFeatureAccess;
}

export function EventLeadershipBanner({
  event,
  access,
}: EventLeadershipBannerProps) {
  const pending = (event.pending_captain_reviews ?? 0) > 0;
  // A submit refetches the event to 0 pending while the dialog still has to
  // show its toast or refusal, so stay mounted until it closes.
  const [dialogOpen, setDialogOpen] = useState(false);
  if (!leadershipAccess(access).member || !(pending || dialogOpen)) return null;
  return (
    <PendingReviewsCard
      orgId={event.organization}
      access={access}
      eventId={event.id}
      testIdPrefix="event-leadership"
      className="mb-4"
      onDialogOpenChange={setDialogOpen}
    />
  );
}
