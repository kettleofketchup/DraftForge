// @vitest-environment jsdom
import { act, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router')>()),
  useNavigate: () => vi.fn(),
}));

import { HeroDraftModal } from '~/components/herodraft/HeroDraftModal';
import type { UserType } from '~/index';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { type CurrentUserStatus, useUserStore } from '~/store/userStore';

const original = useHeroDraftStore.getState();
const originalUser = useUserStore.getState().currentUser;
const originalStatus = useUserStore.getState().currentUserStatus;

afterEach(() => {
  useHeroDraftStore.setState(original, true);
  useUserStore.setState({
    currentUser: originalUser,
    currentUserStatus: originalStatus,
  });
});

function setUser(user: Partial<UserType>, status?: CurrentUserStatus): void {
  useUserStore.setState({
    currentUser: user as UserType,
    ...(status ? { currentUserStatus: status } : {}),
  });
}

function mountModal(
  user: Partial<UserType>,
  status: CurrentUserStatus,
): { calls: string[]; rerender: (open: boolean) => void } {
  const calls: string[] = [];
  useHeroDraftStore.setState({
    connect: vi.fn((id: number) => {
      calls.push(`connect:${id}`);
    }),
    disconnect: vi.fn(() => {
      calls.push('disconnect');
    }),
    reset: vi.fn(() => {
      calls.push('reset');
    }),
    startHeartbeat: vi.fn(),
  });
  setUser(user, status);
  const view = render(<HeroDraftModal draftId={7} open onClose={() => {}} />);
  expect(calls).toEqual(['connect:7']);
  return {
    calls,
    rerender: (open) =>
      view.rerender(
        <HeroDraftModal draftId={7} open={open} onClose={() => {}} />,
      ),
  };
}

const RECONNECT = ['connect:7', 'reset', 'connect:7'];

describe('HeroDraftModal close', () => {
  it('resets the store so the next open starts a fresh chat', () => {
    const { calls, rerender } = mountModal({ pk: 1 }, 'resolved');

    act(() => rerender(false));
    expect(calls).toEqual(['connect:7', 'reset']);
  });
});

describe('HeroDraftModal user change (T19)', () => {
  it('reconnects when the logged-in user changes', () => {
    const { calls } = mountModal({ pk: 1 }, 'resolved');

    act(() => setUser({ pk: 2 }));
    expect(calls).toEqual(RECONNECT);

    act(() => setUser({ pk: 2 }));
    expect(calls).toEqual(RECONNECT);
  });

  it('does not reconnect when the store first resolves to a user', () => {
    const { calls } = mountModal({ pk: 0 }, 'loading');

    act(() => setUser({ pk: 5 }));
    act(() => setUser({ pk: 5 }, 'resolved'));
    expect(calls).toEqual(['connect:7']);
  });

  it('does not reconnect when the store resolves to logged out', () => {
    const { calls } = mountModal({ pk: 0 }, 'unknown');

    act(() => setUser({}, 'loading'));
    act(() => setUser({}, 'resolved'));
    expect(calls).toEqual(['connect:7']);
  });

  it('reconnects on a login after resolving logged out', () => {
    const { calls } = mountModal({}, 'resolved');

    act(() => setUser({ pk: 5 }));
    expect(calls).toEqual(RECONNECT);
  });

  it('reconnects on a login after the first resolve', () => {
    const { calls } = mountModal({ pk: 0 }, 'loading');

    act(() => setUser({}, 'resolved'));
    act(() => setUser({ pk: 5 }));
    expect(calls).toEqual(RECONNECT);
  });
});
