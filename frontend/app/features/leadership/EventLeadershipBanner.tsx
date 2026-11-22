import type { EventType } from '~/components/events/schemas';
import type { OrgFeatureAccess } from '~/features/org-features';
import { PendingReviewsCard } from './PendingReviewsCard';

export interface EventLeadershipBannerProps {
  event: Pick<EventType, 'id' | 'organization' | 'pending_captain_reviews'>;
  access: OrgFeatureAccess;
}

export function EventLeadershipBanner({
  event,
  access,
}: EventLeadershipBannerProps) {
  if (!access.leadershipUnlocked || (event.pending_captain_reviews ?? 0) <= 0)
    return null;
  return (
    <div className="mb-4">
      <PendingReviewsCard
        orgId={event.organization}
        access={access}
        eventId={event.id}
        testIdPrefix="event-leadership"
      />
    </div>
  );
}
