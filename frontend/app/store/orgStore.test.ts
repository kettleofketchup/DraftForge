import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('~/components/api/api', () => ({
  fetchOrganization: vi.fn(),
  getOrganizationUsers: vi.fn(),
}));

import { getOrganizationUsers } from '~/components/api/api';
import { useOrgStore } from './orgStore';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe('orgStore.getOrgUsers', () => {
  beforeEach(() => {
    useOrgStore.getState().reset();
    vi.mocked(getOrganizationUsers).mockReset();
  });

  it('drops a response that lands after clearOrgUsers', async () => {
    const pending = deferred<{ pk: number; username: string }[]>();
    vi.mocked(getOrganizationUsers).mockReturnValueOnce(pending.promise as never);
    const request = useOrgStore.getState().getOrgUsers(3);
    useOrgStore.getState().clearOrgUsers();
    pending.resolve([{ pk: 1, username: 'a' }]);
    await request;
    expect(useOrgStore.getState()).toMatchObject({
      orgUserPks: [],
      orgUsersOrgId: null,
      orgUsersLoading: false,
    });
  });

  it('reloads after a clear and labels the result with its org', async () => {
    vi.mocked(getOrganizationUsers).mockResolvedValue([{ pk: 1, username: 'a' }] as never);
    const stale = useOrgStore.getState().getOrgUsers(3);
    useOrgStore.getState().clearOrgUsers();
    await Promise.all([stale, useOrgStore.getState().getOrgUsers(3)]);
    expect(useOrgStore.getState()).toMatchObject({ orgUserPks: [1], orgUsersOrgId: 3 });
  });

  it('does not start a second request while one is in flight', async () => {
    vi.mocked(getOrganizationUsers).mockResolvedValue([] as never);
    await Promise.all([
      useOrgStore.getState().getOrgUsers(3),
      useOrgStore.getState().getOrgUsers(3),
    ]);
    expect(getOrganizationUsers).toHaveBeenCalledTimes(1);
  });
});
