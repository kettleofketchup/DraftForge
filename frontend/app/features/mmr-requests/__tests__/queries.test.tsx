// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getOrganizationUsers } from '~/components/api/orgAPI';
import type { UserType } from '~/components/user/types';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import {
  approveMmrRequest,
  createMmrRequest,
  fetchMmrPendingCount,
  fetchUserMmrSummary,
} from '../api';
import {
  useApproveMmrRequest,
  useCreateMmrRequest,
  useMmrPendingCount,
  useUserMmrSummary,
} from '../queries';
import { mmrKeys } from '../queryKeys';
import { mmrRequest, mmrSummary } from './fixtures';

vi.mock('../api', () => ({
  fetchUserMmrSummary: vi.fn(),
  fetchMyMmrRequests: vi.fn(),
  createMmrRequest: vi.fn(),
  cancelMmrRequest: vi.fn(),
  fetchMmrQueue: vi.fn(),
  fetchMmrPendingCount: vi.fn(),
  approveMmrRequest: vi.fn(),
  rejectMmrRequest: vi.fn(),
  staffSetMmr: vi.fn(),
  mmrScreenshotUrl: (id: number) => `/api/mmr-requests/${id}/screenshot/`,
}));

vi.mock('~/components/api/orgAPI', () => ({
  getOrganizationUsers: vi.fn(),
}));

vi.mock('~/components/api/leagueAPI', () => ({
  getLeagueUsers: vi.fn(),
}));

const VIEWER = 42;

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const invalid = (key: readonly unknown[]) =>
    client.getQueryState(key)?.isInvalidated ?? false;
  return { client, wrapper, invalid };
}

beforeEach(() => {
  useUserStore.setState({ currentUser: { pk: VIEWER } as UserType });
});

afterEach(() => {
  vi.clearAllMocks();
  useOrgStore.getState().clearOrgUsers();
});

describe('useUserMmrSummary', () => {
  it('keys the summary by subject and viewer', async () => {
    vi.mocked(fetchUserMmrSummary).mockResolvedValue(mmrSummary());
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useUserMmrSummary(42), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchUserMmrSummary).toHaveBeenCalledWith(42);
    expect(client.getQueryData(mmrKeys.summary(42, VIEWER))).toEqual(
      mmrSummary(),
    );
  });
});

describe('useMmrPendingCount', () => {
  it('reads the count for a scope', async () => {
    vi.mocked(fetchMmrPendingCount).mockResolvedValue({ count: 2 });
    const { wrapper } = setup();
    const { result } = renderHook(() => useMmrPendingCount({ org: 3 }), {
      wrapper,
    });
    await waitFor(() => expect(result.current.data).toEqual({ count: 2 }));
    expect(fetchMmrPendingCount).toHaveBeenCalledWith({ org: 3 });
  });

  it('does not fetch when disabled', () => {
    const { wrapper } = setup();
    renderHook(() => useMmrPendingCount({ org: 3 }, false), { wrapper });
    expect(fetchMmrPendingCount).not.toHaveBeenCalled();
  });
});

describe('useCreateMmrRequest', () => {
  it('invalidates mmr-requests and the legacy user payload on success', async () => {
    vi.mocked(createMmrRequest).mockResolvedValue(mmrRequest());
    const { client, wrapper, invalid } = setup();
    const keys = {
      summary: mmrKeys.summary(VIEWER, VIEWER),
      queue: mmrKeys.queue({ org: 3 }, VIEWER, 'pending'),
      user: ['user', VIEWER],
      other: ['user', 7],
    };
    for (const key of Object.values(keys)) client.setQueryData(key, {});
    const { result } = renderHook(() => useCreateMmrRequest(VIEWER), {
      wrapper,
    });
    const screenshot = new File(['x'], 'a.png', { type: 'image/png' });
    await act(() =>
      result.current.mutateAsync({
        target: 'org',
        orgUserPk: 117,
        gameType: 1,
        requestedMmr: 4800,
        screenshot,
        note: '',
      }),
    );
    expect(invalid(keys.summary)).toBe(true);
    expect(invalid(keys.queue)).toBe(true);
    expect(invalid(keys.user)).toBe(true);
    expect(invalid(keys.other)).toBe(false);
  });

  it('invalidates after a failed create too', async () => {
    vi.mocked(createMmrRequest).mockRejectedValue(new Error('409'));
    const { client, wrapper, invalid } = setup();
    client.setQueryData(mmrKeys.summary(VIEWER, VIEWER), {});
    const { result } = renderHook(() => useCreateMmrRequest(VIEWER), {
      wrapper,
    });
    await act(async () => {
      await result.current
        .mutateAsync({
          target: 'league',
          leagueUserPk: 300,
          requestedMmr: 4800,
          screenshot: new File(['x'], 'a.png', { type: 'image/png' }),
          note: '',
        })
        .catch(() => undefined);
    });
    expect(invalid(mmrKeys.summary(VIEWER, VIEWER))).toBe(true);
  });
});

describe('useApproveMmrRequest', () => {
  it('refreshes the loaded org member list for the subject', async () => {
    const row = mmrRequest();
    vi.mocked(approveMmrRequest).mockResolvedValue({
      ...row,
      status: 'approved',
      approved_mmr: 4750,
    });
    vi.mocked(getOrganizationUsers).mockResolvedValue([
      { pk: 42, username: 'member', game_mmrs: { '1': 4750 } } as UserType,
      { pk: 8, username: 'other' } as UserType,
    ]);
    useOrgStore.setState({ orgUsersOrgId: 3, orgUserPks: [42, 8] });
    const upsert = vi.spyOn(useUserCacheStore.getState(), 'upsert');
    const { client, wrapper, invalid } = setup();
    client.setQueryData(['user', 42], {});
    const { result } = renderHook(() => useApproveMmrRequest(), { wrapper });
    await act(() => result.current.mutateAsync({ request: row, mmr: 4750 }));
    expect(approveMmrRequest).toHaveBeenCalledWith(77, 4750);
    expect(invalid(['user', 42])).toBe(true);
    await waitFor(() =>
      expect(upsert).toHaveBeenCalledWith(
        [expect.objectContaining({ pk: 42 })],
        { orgId: 3 },
      ),
    );
    upsert.mockRestore();
  });

  it('leaves the member list alone when another org is loaded', async () => {
    vi.mocked(approveMmrRequest).mockResolvedValue(mmrRequest());
    useOrgStore.setState({ orgUsersOrgId: 99, orgUserPks: [1] });
    const { wrapper } = setup();
    const { result } = renderHook(() => useApproveMmrRequest(), { wrapper });
    await act(() => result.current.mutateAsync({ request: mmrRequest() }));
    expect(approveMmrRequest).toHaveBeenCalledWith(77, undefined);
    expect(getOrganizationUsers).not.toHaveBeenCalled();
  });
});
