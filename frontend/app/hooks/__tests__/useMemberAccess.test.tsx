// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { type MemberAccessSource, useMemberAccess } from '../useMemberAccess';

function setViewer(pk: number | null) {
  useUserStore.setState({
    currentUser: (pk == null ? {} : { pk, username: `u${pk}` }) as UserType,
  });
}

function render(source: MemberAccessSource | null, onStale = vi.fn()) {
  const hook = renderHook(
    ({ src }: { src: MemberAccessSource | null }) => useMemberAccess(src, onStale),
    { initialProps: { src: source } },
  );
  return { ...hook, onStale };
}

describe('useMemberAccess', () => {
  beforeEach(() => setViewer(null));

  it('is settled when the payload was computed for the current viewer', () => {
    setViewer(5);
    const { result } = render({ can_view_members: true, members_viewer_pk: 5 });
    expect(result.current).toEqual({ canView: true, settled: true });
  });

  it('does not refetch when the store catches up to the payload viewer', () => {
    const { result, onStale } = render({ can_view_members: true, members_viewer_pk: 5 });
    expect(result.current.settled).toBe(false);
    act(() => setViewer(5));
    expect(onStale).not.toHaveBeenCalled();
    expect(result.current).toEqual({ canView: true, settled: true });
  });

  it('marks a pre-login payload stale on login', () => {
    const { result, onStale } = render({ can_view_members: false, members_viewer_pk: null });
    expect(result.current.settled).toBe(true);
    act(() => setViewer(7));
    expect(onStale).toHaveBeenCalledTimes(1);
    expect(result.current.settled).toBe(false);
  });

  it('marks a staff payload stale on logout', () => {
    setViewer(5);
    const { result, onStale } = render({ can_view_members: true, members_viewer_pk: 5 });
    act(() => setViewer(null));
    expect(onStale).toHaveBeenCalledTimes(1);
    expect(result.current.settled).toBe(false);
  });

  it('keeps the last known answer when a payload omits the flag', () => {
    setViewer(5);
    const { result, rerender } = render({ can_view_members: true, members_viewer_pk: 5 });
    rerender({ src: {} });
    expect(result.current).toEqual({ canView: true, settled: false });
  });
});
