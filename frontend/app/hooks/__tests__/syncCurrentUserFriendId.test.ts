import { beforeEach, describe, expect, it } from 'vitest';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { syncCurrentUserFriendId } from '../useEvent';

function setUser(steamAccountId: number | null): void {
  useUserStore.setState({
    currentUser: { pk: 7, steam_account_id: steamAccountId } as UserType,
  });
}

describe('syncCurrentUserFriendId', () => {
  beforeEach(() => setUser(null));

  it('fills an empty Friend ID from the submitted signup', () => {
    syncCurrentUserFriendId({
      intent: 'rsvp',
      profile: { steam_account_id: ' 4294967295 ' },
    });
    expect(useUserStore.getState().currentUser.steam_account_id).toBe(
      4294967295,
    );
  });

  it('never replaces a stored Friend ID', () => {
    setUser(111);
    syncCurrentUserFriendId({
      intent: 'rsvp',
      profile: { steam_account_id: '222' },
    });
    expect(useUserStore.getState().currentUser.steam_account_id).toBe(111);
  });

  it('ignores a signup without a Friend ID', () => {
    syncCurrentUserFriendId({ intent: 'rsvp', profile: {} });
    expect(useUserStore.getState().currentUser.steam_account_id).toBeNull();
  });
});
