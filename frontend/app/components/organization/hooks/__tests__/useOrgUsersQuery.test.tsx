// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getOrganizationUsers } from '~/components/api/api';
import type { OrgMemberType } from '~/components/organization/schemas';
import { useOrgUsers } from '~/hooks/useOrgUsers';
import { useUserCacheStore } from '~/store/userCacheStore';
import { organizationQueryKey } from '../useOrganization';
import { orgUsersQueryKey, useOrgUsersQuery } from '../useOrgUsersQuery';

vi.mock('~/components/api/api', () => ({
  getOrganizationUsers: vi.fn(),
  fetchOrganization: vi.fn(),
}));

function member(pk: number, username: string): OrgMemberType {
  return {
    orgUserPk: pk + 100,
    pk,
    username,
    nickname: null,
    guildNickname: null,
    discordNickname: null,
    avatar: null,
    discordId: null,
    positions: null,
    steam_account_id: null,
    avatarUrl: null,
    mmr: 0,
    mmr_game_type: 0,
    game_mmrs: {},
    league_mmr: null,
  };
}

const alice = member(1, 'alice');
const bob = member(2, 'bob');

function setup(): {
  qc: QueryClient;
  wrapper: (props: { children: ReactNode }) => ReactNode;
} {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

afterEach(() => {
  vi.mocked(getOrganizationUsers).mockReset();
  useUserCacheStore.getState().reset();
});

describe('useOrgUsersQuery', () => {
  it('nests the members key under the organization key', () => {
    expect(orgUsersQueryKey(3).slice(0, 2)).toEqual([
      ...organizationQueryKey(3),
    ]);
  });

  it('returns member pks and upserts users into the cache', async () => {
    vi.mocked(getOrganizationUsers).mockResolvedValue([alice, bob]);
    const { wrapper } = setup();
    const { result } = renderHook(() => useOrgUsersQuery(3), { wrapper });

    await waitFor(() => expect(result.current.data).toEqual([1, 2]));
    expect(getOrganizationUsers).toHaveBeenCalledWith(3);
    expect(useUserCacheStore.getState().entities[2]?.username).toBe('bob');
  });

  it('does not fetch when disabled or without an org', () => {
    const { wrapper } = setup();
    renderHook(() => useOrgUsersQuery(3, { enabled: false }), { wrapper });
    renderHook(() => useOrgUsersQuery(null), { wrapper });
    expect(getOrganizationUsers).not.toHaveBeenCalled();
  });

  it('refetches members when the organization key is invalidated', async () => {
    vi.mocked(getOrganizationUsers).mockResolvedValueOnce([alice]);
    const { qc, wrapper } = setup();
    const { result } = renderHook(() => useOrgUsers(3), { wrapper });
    await waitFor(() =>
      expect(result.current.users.map((u) => u.pk)).toEqual([1]),
    );

    vi.mocked(getOrganizationUsers).mockResolvedValueOnce([alice, bob]);
    await act(() =>
      qc.invalidateQueries({ queryKey: organizationQueryKey(3) }),
    );

    await waitFor(() =>
      expect(result.current.users.map((u) => u.pk)).toEqual([1, 2]),
    );
    expect(getOrganizationUsers).toHaveBeenCalledTimes(2);
  });
});
