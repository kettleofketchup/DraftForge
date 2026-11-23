import { describe, expect, it } from 'vitest';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { leadershipAccess, leadershipTrack } from '../access';
import { leadershipFeatureAccess, leadershipTrackInfo } from './fixtures';

describe('leadershipAccess', () => {
  it('reads the flags off the leadership track', () => {
    expect(
      leadershipAccess(
        leadershipFeatureAccess({
          track: { can_manage: true, board_open: false },
        }),
      ),
    ).toEqual({
      unlocked: true,
      member: true,
      canManage: true,
      canModerate: false,
      boardOpen: false,
    });
  });

  it('a non-member admin is not a member', () => {
    const flags = leadershipAccess(
      leadershipFeatureAccess({
        track: { can_manage: true, can_view_own: false },
      }),
    );
    expect(flags.member).toBe(false);
    expect(flags.canManage).toBe(true);
  });

  it('is all false without the leadership track', () => {
    expect(leadershipAccess(leadershipFeatureAccess({ track: null }))).toEqual({
      unlocked: false,
      member: false,
      canManage: false,
      canModerate: false,
      boardOpen: false,
    });
  });

  it('reads can_moderate for org staff who cannot manage', () => {
    const flags = leadershipAccess(
      leadershipFeatureAccess({
        track: { can_moderate: true, can_manage: false },
      }),
    );
    expect(flags.canModerate).toBe(true);
    expect(flags.canManage).toBe(false);
  });

  it('ignores tracks until access is settled', () => {
    const access = makeOrgFeatureAccess({
      settled: false,
      standingTracks: [
        leadershipTrackInfo({ can_manage: true, can_moderate: true }),
      ],
    });
    expect(leadershipTrack(access)).toBeUndefined();
    expect(leadershipAccess(access).canManage).toBe(false);
    expect(leadershipAccess(access).canModerate).toBe(false);
  });
});
