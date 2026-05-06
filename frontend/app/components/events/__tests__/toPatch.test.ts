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

  it('treats array order as significant (positions diff)', () => {
    const profile = { positions: [1, 2] };
    const valuesSame = { positions: [1, 2] };
    const valuesDifferent = { positions: [2, 1] };
    expect(toPatch(valuesSame as never, profile as never)).toEqual({});
    expect(toPatch(valuesDifferent as never, profile as never)).toEqual({ positions: [2, 1] });
  });
});
