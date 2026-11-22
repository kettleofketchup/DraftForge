import type {
  TrackAdminProps,
  TrackDetailProps,
} from '~/features/standing/panels';
import { MemberLeadershipPanel } from './MemberLeadershipPanel';
import { MyReviewsList } from './MyReviewsList';
import { PendingReviewsCard } from './PendingReviewsCard';

export function LeadershipBanner({ orgId, access }: TrackAdminProps) {
  if (!access.leadershipUnlocked || !access.leadershipMember) return null;
  return (
    <div className="flex flex-col gap-3">
      <PendingReviewsCard orgId={orgId} access={access} />
      <MyReviewsList orgId={orgId} access={access} />
    </div>
  );
}

export function LeadershipDetail({
  orgId,
  orgUserPk,
  own,
  timeZone,
  access,
  onClose,
}: TrackDetailProps) {
  return (
    <MemberLeadershipPanel
      orgId={orgId}
      orgUserPk={orgUserPk}
      own={own}
      timeZone={timeZone}
      access={access}
      onClose={onClose}
    />
  );
}
