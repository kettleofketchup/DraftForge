// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/index';
import { setActivityCredential } from '~/lib/activity-session';
import { useUserStore } from '../userStore';
const mocks = vi.hoisted(() => ({ fetchCurrentUser: vi.fn() }));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  fetchCurrentUser: mocks.fetchCurrentUser,
}));
const activityUser = { pk: 99, username: 'activity-captain' } as UserType;
beforeEach(() => {
  vi.clearAllMocks();
  setActivityCredential(null);
  useUserStore.setState({ currentUser: {} as UserType });
});
afterEach(() => setActivityCredential(null));
describe('Activity identity in the shared user store', () => {
  it('keeps the verified Discord identity when an earlier cookie auth response arrives late', async () => {
    let resolve!: (value: UserType) => void;
    mocks.fetchCurrentUser.mockImplementation(
      () =>
        new Promise<UserType>((done) => {
          resolve = done;
        }),
    );
    const earlierRequest = useUserStore.getState().getCurrentUser();
    setActivityCredential({
      token: 'secret',
      scope: 'draft',
      tournament_id: null,
      pin: { kind: 'hero', id: 7 },
      site_url: 'https://site.test',
      user: activityUser,
    });
    useUserStore.getState().setCurrentUser(activityUser);
    resolve({} as UserType);
    await earlierRequest;
    expect(useUserStore.getState().currentUser).toEqual(activityUser);
  });
  it('keeps the Activity identity if that earlier auth request fails', async () => {
    let reject!: (reason: Error) => void;
    mocks.fetchCurrentUser.mockImplementation(
      () =>
        new Promise<UserType>((_done, fail) => {
          reject = fail;
        }),
    );
    const earlierRequest = useUserStore.getState().getCurrentUser();
    setActivityCredential({
      token: 'secret',
      scope: 'draft',
      tournament_id: null,
      pin: { kind: 'team', id: 8 },
      site_url: 'https://site.test',
      user: activityUser,
    });
    reject(new Error('no cookie session'));
    await earlierRequest;
    expect(useUserStore.getState().currentUser).toEqual(activityUser);
  });
  it('does not start a cookie-based identity request during an Activity session', async () => {
    setActivityCredential({
      token: 'secret',
      scope: 'draft',
      tournament_id: null,
      pin: { kind: 'hero', id: 7 },
      site_url: 'https://site.test',
      user: activityUser,
    });
    await useUserStore.getState().getCurrentUser();
    expect(mocks.fetchCurrentUser).not.toHaveBeenCalled();
    expect(useUserStore.getState().currentUserStatus).toBe('resolved');
    expect(useUserStore.getState().currentUser).toEqual(activityUser);
  });
  it('preserves ordinary website identity refresh after the Activity ends', async () => {
    const websiteUser = { pk: 12, username: 'website-user' } as UserType;
    mocks.fetchCurrentUser.mockResolvedValue(websiteUser);
    await useUserStore.getState().getCurrentUser();
    expect(useUserStore.getState().currentUser).toEqual(websiteUser);
  });
});
