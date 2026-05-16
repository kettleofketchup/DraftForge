import { describe, it, expect } from 'vitest';
import { toPatch } from '../EventSignupModal/toPatch';

describe('toPatch', () => {
  it('omits unchanged fields', () => {
    const profile = { unverified_friend_id: '12345', rank_status: 'active' };
    const values = {
      unverified_friend_id: '12345',
      rank_status: 'active',
      rank_medal: 'Legend 1',
    };
    expect(toPatch(values as never, profile as never)).toEqual({ rank_medal: 'Legend 1' });
  });

  it('includes changed fields', () => {
    const profile = { unverified_friend_id: '11111' };
    const values = { unverified_friend_id: '22222' };
    expect(toPatch(values as never, profile as never)).toEqual({ unverified_friend_id: '22222' });
  });

  it('includes everything when no profile', () => {
    expect(toPatch({ rank_status: 'never' } as never, null)).toEqual({ rank_status: 'never' });
  });

  it('omits undefined values', () => {
    const profile = { unverified_friend_id: '12345' };
    const values = { unverified_friend_id: undefined as unknown as string };
    expect(toPatch(values as never, profile as never)).toEqual({});
  });

  it('omits positions when dict matches userPositions baseline', () => {
    const userPositions = { carry: 1, mid: 2, offlane: 0, soft_support: 0, hard_support: 0 };
    const values = {
      positions: { carry: 1, mid: 2, offlane: 0, soft_support: 0, hard_support: 0 },
    };
    expect(toPatch(values as never, null, userPositions)).toEqual({});
  });

  it('includes positions when any role priority differs from userPositions baseline', () => {
    const userPositions = { carry: 1, mid: 2, offlane: 0, soft_support: 0, hard_support: 0 };
    const values = {
      positions: { carry: 1, mid: 2, offlane: 3, soft_support: 0, hard_support: 0 },
    };
    expect(toPatch(values as never, null, userPositions)).toEqual({
      positions: { carry: 1, mid: 2, offlane: 3, soft_support: 0, hard_support: 0 },
    });
  });

  it('treats missing keys on baseline as zero', () => {
    // Empty baseline {} → any non-zero priority in values triggers a diff.
    const values = {
      positions: { carry: 1, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
    };
    expect(toPatch(values as never, null, {})).toEqual({
      positions: { carry: 1, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
    });
  });
});
