// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { useMembership } from '../useMembership';

vi.mock('~/components/api/api', () => ({
  fetchCurrentUser: vi.fn(() => new Promise(() => undefined)),
}));

let getCurrentUser: ReturnType<typeof vi.fn<() => Promise<void>>>;

beforeEach(() => {
  getCurrentUser = vi.fn(() => Promise.resolve());
  useUserStore.setState({
    currentUserStatus: 'unknown',
    currentUser: {} as UserType,
    getCurrentUser,
  });
});

describe('useMembership', () => {
  it('fetches the current user on mount when the status is unknown', () => {
    const { result } = renderHook(() => useMembership());
    expect(getCurrentUser).toHaveBeenCalledTimes(1);
    expect(result.current.membershipPending).toBe(true);
  });

  it('does not fetch when another caller is already loading', () => {
    useUserStore.setState({ currentUserStatus: 'loading' });
    const { result } = renderHook(() => useMembership());
    expect(getCurrentUser).not.toHaveBeenCalled();
    expect(result.current.membershipPending).toBe(true);
  });

  it('is logged out and not pending when resolved without a user', () => {
    useUserStore.setState({ currentUserStatus: 'resolved' });
    const { result } = renderHook(() => useMembership());
    expect(getCurrentUser).not.toHaveBeenCalled();
    expect(result.current).toEqual({
      memberOrgIds: undefined,
      isLoggedIn: false,
      membershipPending: false,
    });
  });

  it('returns ids without refetching when the user already has them', () => {
    useUserStore.setState({
      currentUserStatus: 'resolved',
      currentUser: { pk: 7, member_organization_ids: [30] } as UserType,
    });
    const { result } = renderHook(() => useMembership());
    expect(getCurrentUser).not.toHaveBeenCalled();
    expect(result.current).toEqual({
      memberOrgIds: [30],
      isLoggedIn: true,
      membershipPending: false,
    });
  });

  it('refetches once for a user without ids and stops pending after it settles', async () => {
    useUserStore.setState({
      currentUserStatus: 'resolved',
      currentUser: { pk: 7 } as UserType,
    });
    const { result, rerender } = renderHook(() => useMembership());
    expect(getCurrentUser).toHaveBeenCalledTimes(1);
    expect(result.current.membershipPending).toBe(true);
    await waitFor(() => expect(result.current.membershipPending).toBe(false));
    rerender();
    expect(getCurrentUser).toHaveBeenCalledTimes(1);
    expect(result.current.memberOrgIds).toBeUndefined();
    expect(result.current.isLoggedIn).toBe(true);
  });
});
