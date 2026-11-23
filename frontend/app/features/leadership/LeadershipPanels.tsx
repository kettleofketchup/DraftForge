import type {
  TrackDetailProps,
  TrackSlotProps,
} from '~/features/standing/panels';
import { leadershipAccess } from './access';
import { MemberLeadershipPanel } from './MemberLeadershipPanel';
import { MyReviewsList } from './MyReviewsList';
import { PendingReviewsCard } from './PendingReviewsCard';

export function LeadershipBanner({ orgId, access }: TrackSlotProps) {
  if (!leadershipAccess(access).member) return null;
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
