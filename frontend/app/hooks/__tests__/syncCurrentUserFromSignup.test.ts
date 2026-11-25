import { beforeEach, describe, expect, it } from 'vitest';
import { GAME_TYPE } from '~/components/game/constants';
import type { PositionsType, UserType } from '~/components/user/types';
import { selectPositions } from '~/store/selectPositions';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { syncCurrentUserFromSignup } from '../useEvent';

const OLD_POSITIONS: PositionsType = {
  carry: 1,
  mid: 2,
  offlane: 4,
  soft_support: 5,
  hard_support: 3,
};

function setUser(
  steamAccountId: number | null,
  positions: PositionsType = OLD_POSITIONS,
): void {
  useUserStore.setState({
    currentUser: {
      pk: 7,
      username: 'player',
      steam_account_id: steamAccountId,
      positions,
    } as UserType,
  });
}

describe('syncCurrentUserFromSignup', () => {
  beforeEach(() => {
    useUserCacheStore.getState().reset();
    setUser(null);
  });

  it('fills an empty Friend ID from the submitted signup', () => {
    syncCurrentUserFromSignup({
      intent: 'rsvp',
      profile: { steam_account_id: ' 4294967295 ' },
    });
    expect(useUserStore.getState().currentUser.steam_account_id).toBe(
      4294967295,
    );
  });

  it('never replaces a stored Friend ID', () => {
    setUser(111);
    syncCurrentUserFromSignup({
      intent: 'rsvp',
      profile: { steam_account_id: '222' },
    });
    expect(useUserStore.getState().currentUser.steam_account_id).toBe(111);
  });

  it('ignores a signup without a Friend ID or positions', () => {
    useUserCacheStore.getState().upsert(useUserStore.getState().currentUser);
    syncCurrentUserFromSignup({ intent: 'rsvp', profile: {} });
    const { currentUser } = useUserStore.getState();
    expect(currentUser.steam_account_id).toBeNull();
    expect(currentUser.positions).toEqual(OLD_POSITIONS);
    expect(
      selectPositions(useUserCacheStore.getState(), 7, GAME_TYPE.DOTA2),
    ).toEqual(OLD_POSITIONS);
  });

  it('patches submitted positions into currentUser and the user cache', () => {
    useUserCacheStore.getState().upsert(useUserStore.getState().currentUser);
    const next = { ...OLD_POSITIONS, carry: 2, mid: 1 };
    syncCurrentUserFromSignup({ intent: 'rsvp', profile: { positions: next } });
    expect(useUserStore.getState().currentUser.positions).toEqual(next);
    expect(
      selectPositions(useUserCacheStore.getState(), 7, GAME_TYPE.DOTA2),
    ).toEqual(next);
  });

  it('adds the current user to the cache when it is not cached yet', () => {
    const next = { ...OLD_POSITIONS, mid: 1 };
    syncCurrentUserFromSignup({ intent: 'rsvp', profile: { positions: next } });
    const entry = useUserCacheStore.getState().getById(7);
    expect(entry?.positions).toEqual(next);
    expect(entry?.username).toBe('player');
  });

  it('ignores malformed positions', () => {
    syncCurrentUserFromSignup({
      intent: 'rsvp',
      profile: { positions: { mid: 'first' } },
    });
    expect(useUserStore.getState().currentUser.positions).toEqual(
      OLD_POSITIONS,
    );
  });
});
