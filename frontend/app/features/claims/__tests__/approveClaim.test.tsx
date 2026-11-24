// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import { orgUsersQueryKey } from '~/components/organization/hooks/useOrgUsersQuery';
import type { UserType } from '~/components/user/types';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { approveClaimRequest } from '../api';
import { useApproveClaim } from '../queries';
import { claimKeys } from '../queryKeys';

vi.mock('../api', () => ({
  approveClaimRequest: vi.fn(),
  getClaimRequests: vi.fn(),
}));

const ORG = 3;
const VIEWER = 9;
const CLAIMER = 40;
const TARGET = 41;
const ORG_KEY = organizationQueryKey(ORG);
const ORG_USERS_KEY = orgUsersQueryKey(ORG);
const OTHER_ORG_KEY = organizationQueryKey(4);
const PENDING_KEY = claimKeys.list(ORG, VIEWER, 'pending');

function setup() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  });
  qc.setQueryData(ORG_KEY, { pk: ORG, users_count: 5 });
  qc.setQueryData(ORG_USERS_KEY, [CLAIMER, TARGET]);
  qc.setQueryData(OTHER_ORG_KEY, { pk: 4 });
  qc.setQueryData(PENDING_KEY, [{ id: 1 }]);
  qc.setQueryData(['user', TARGET], { pk: TARGET });
  qc.setQueryData(['user', CLAIMER], { pk: CLAIMER });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

afterEach(() => {
  vi.mocked(approveClaimRequest).mockReset();
  useUserCacheStore.getState().reset();
  useUserStore.setState({ currentUser: {} as UserType });
});

describe('useApproveClaim', () => {
  it('refreshes the org and its members and evicts the merged profile', async () => {
    vi.mocked(approveClaimRequest).mockResolvedValue('approved');
    useUserStore.setState({ currentUser: { pk: VIEWER } as UserType });
    useUserCacheStore
      .getState()
      .upsert([{ pk: TARGET, username: null } as unknown as UserType]);
    expect(useUserCacheStore.getState().entities[TARGET]).toBeDefined();

    const { qc, wrapper } = setup();
    const { result } = renderHook(() => useApproveClaim(ORG), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({
        id: 1,
        claimer: CLAIMER,
        target_user: TARGET,
      });
    });

    expect(approveClaimRequest).toHaveBeenCalledWith(1);
    await waitFor(() => {
      expect(qc.getQueryState(ORG_KEY)?.isInvalidated).toBe(true);
      expect(qc.getQueryState(ORG_USERS_KEY)?.isInvalidated).toBe(true);
      expect(qc.getQueryState(PENDING_KEY)?.isInvalidated).toBe(true);
      expect(qc.getQueryState(['user', CLAIMER])?.isInvalidated).toBe(true);
    });
    expect(qc.getQueryState(OTHER_ORG_KEY)?.isInvalidated).toBe(false);
    expect(qc.getQueryData(['user', TARGET])).toBeUndefined();
    expect(useUserCacheStore.getState().entities[TARGET]).toBeUndefined();
  });

  it('skips target eviction when the merged profile is already absent', async () => {
    vi.mocked(approveClaimRequest).mockResolvedValue('approved');
    const { qc, wrapper } = setup();
    qc.setQueryData(['user', null], { placeholder: true });
    const { result } = renderHook(() => useApproveClaim(ORG), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({
        id: 1,
        claimer: CLAIMER,
        target_user: null,
      });
    });
    expect(qc.getQueryData(['user', null])).toEqual({ placeholder: true });
    expect(qc.getQueryData(['user', TARGET])).toEqual({ pk: TARGET });
    expect(qc.getQueryState(['user', CLAIMER])?.isInvalidated).toBe(true);
  });

  it('leaves the caches alone when the approval fails', async () => {
    vi.mocked(approveClaimRequest).mockRejectedValue(new Error('nope'));
    const { qc, wrapper } = setup();
    const { result } = renderHook(() => useApproveClaim(ORG), { wrapper });
    await act(async () => {
      await expect(
        result.current.mutateAsync({
          id: 1,
          claimer: CLAIMER,
          target_user: TARGET,
        }),
      ).rejects.toThrow('nope');
    });
    expect(qc.getQueryState(ORG_KEY)?.isInvalidated).toBe(false);
    expect(qc.getQueryData(['user', TARGET])).toEqual({ pk: TARGET });
  });
});
