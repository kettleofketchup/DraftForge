// @vitest-environment jsdom
import { describe, expect, it, beforeEach, vi } from 'vitest';

import { fetchCurrentUser } from '~/components/api/api';
import type { UserType } from '~/index';

import { useUserStore } from './userStore';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  fetchCurrentUser: vi.fn(),
}));

const mockFetchCurrentUser = vi.mocked(fetchCurrentUser);

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

describe('userStore.currentUserStatus', () => {
  beforeEach(() => {
    mockFetchCurrentUser.mockReset();
    useUserStore.getState().clearUser();
    useUserStore.setState({ currentUserStatus: 'unknown' });
  });

  it("starts as 'unknown'", () => {
    expect(useUserStore.getInitialState().currentUserStatus).toBe('unknown');
  });

  it("is 'loading' while the fetch is pending and 'resolved' after success", async () => {
    let resolveFetch: (user: UserType) => void = () => {};
    mockFetchCurrentUser.mockReturnValue(
      new Promise<UserType>((resolve) => {
        resolveFetch = resolve;
      }),
    );
    const pending = useUserStore.getState().getCurrentUser();
    expect(useUserStore.getState().currentUserStatus).toBe('loading');
    resolveFetch(freshUser());
    await pending;
    expect(useUserStore.getState().currentUserStatus).toBe('resolved');
    expect(useUserStore.getState().currentUser.pk).toBe(1);
  });

  it("is 'resolved' with an empty user when the fetch rejects", async () => {
    mockFetchCurrentUser.mockRejectedValue(new Error('401'));
    await useUserStore.getState().getCurrentUser();
    expect(useUserStore.getState().currentUserStatus).toBe('resolved');
    expect(useUserStore.getState().currentUser).toEqual({});
  });

  it("is 'resolved' with an empty user for an anonymous empty body", async () => {
    mockFetchCurrentUser.mockResolvedValue('' as unknown as UserType);
    await useUserStore.getState().getCurrentUser();
    expect(useUserStore.getState().currentUserStatus).toBe('resolved');
    expect(useUserStore.getState().currentUser).toEqual({});
  });

  it('is not persisted', () => {
    const partialize = useUserStore.persist.getOptions().partialize!;
    expect(partialize(useUserStore.getState())).not.toHaveProperty(
      'currentUserStatus',
    );
  });
});
