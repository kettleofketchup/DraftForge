import { describe, expect, it, beforeEach } from 'vitest';

import type { UserType } from '~/index';

import { useUserStore } from './userStore';

function freshUser(overrides: Partial<UserType> = {}): UserType {
  return {
    pk: 1,
    username: 'liv',
    nickname: 'Liv',
    avatar: null,
    discordId: '123',
    is_staff: false,
    is_active: true,
    is_superuser: false,
  } as UserType;
}

describe('userStore.patchCurrentUser', () => {
  beforeEach(() => {
    useUserStore.getState().clearUser();
  });

  it('merges the partial into currentUser', () => {
    useUserStore.getState().setCurrentUser(freshUser());
    useUserStore.getState().patchCurrentUser({ nickname: 'Liv-Renamed' });
    expect(useUserStore.getState().currentUser.nickname).toBe('Liv-Renamed');
    // unrelated fields preserved
    expect(useUserStore.getState().currentUser.username).toBe('liv');
    expect(useUserStore.getState().currentUser.pk).toBe(1);
  });

  it('is a no-op when currentUser has no pk', () => {
    // After clearUser, currentUser = {} as UserType — no pk.
    const before = useUserStore.getState().currentUser;
    useUserStore.getState().patchCurrentUser({ nickname: 'X' });
    expect(useUserStore.getState().currentUser).toBe(before);
  });

  it('applies multiple keys atomically', () => {
    useUserStore.getState().setCurrentUser(freshUser());
    useUserStore.getState().patchCurrentUser({
      nickname: 'New',
      avatar: 'abcdef',
    });
    const cu = useUserStore.getState().currentUser;
    expect(cu.nickname).toBe('New');
    expect(cu.avatar).toBe('abcdef');
  });

  it('does not pollute other store slices', () => {
    useUserStore.getState().setCurrentUser(freshUser());
    const beforeUsers = useUserStore.getState().globalUserPks;
    const beforeTournaments = useUserStore.getState().tournaments;
    useUserStore.getState().patchCurrentUser({ nickname: 'X' });
    expect(useUserStore.getState().globalUserPks).toBe(beforeUsers);
    expect(useUserStore.getState().tournaments).toBe(beforeTournaments);
  });

  it('accepts null nickname (clearing the field)', () => {
    useUserStore.getState().setCurrentUser(freshUser({ nickname: 'X' }));
    useUserStore.getState().patchCurrentUser({ nickname: null });
    expect(useUserStore.getState().currentUser.nickname).toBeNull();
  });
});
