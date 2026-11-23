import type { OrgFeatureAccess } from '~/features/org-features';
import type { TrackInfo } from '~/features/standing/schemas';

export interface LeadershipAccess {
  /** The org payload lists the leadership track for this viewer. */
  unlocked: boolean;
  /** The viewer is an org member, so the rater endpoints answer. */
  member: boolean;
  canManage: boolean;
  /** Org staff or site staff: event moderation and release. */
  canModerate: boolean;
  /** Members can see the board; always true for org staff. */
  boardOpen: boolean;
}

export function leadershipTrack(
  access: OrgFeatureAccess,
): TrackInfo | undefined {
  if (!access.settled) return undefined;
  return access.standingTracks.find((track) => track.key === 'leadership');
}

export function leadershipAccess(access: OrgFeatureAccess): LeadershipAccess {
  const track = leadershipTrack(access);
  return {
    unlocked: track !== undefined,
    member: track?.can_view_own === true,
    canManage: track?.can_manage === true,
    canModerate: track?.can_moderate === true,
    boardOpen: track?.board_open === true,
  };
}
