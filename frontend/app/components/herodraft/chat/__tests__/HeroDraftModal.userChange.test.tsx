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
import { useUserStore } from '~/store/userStore';

const original = useHeroDraftStore.getState();
const originalUser = useUserStore.getState().currentUser;

afterEach(() => {
  useHeroDraftStore.setState(original, true);
  useUserStore.setState({ currentUser: originalUser });
});

describe('HeroDraftModal user change (T19)', () => {
  it('reconnects when the logged-in user changes', () => {
    const calls: string[] = [];
    const connect = vi.fn((id: number) => {
      calls.push(`connect:${id}`);
    });
    const disconnect = vi.fn(() => {
      calls.push('disconnect');
    });
    const clearChatError = vi.fn(() => {
      calls.push('clearChatError');
    });
    useHeroDraftStore.setState({
      connect,
      disconnect,
      clearChatError,
      startHeartbeat: vi.fn(),
    });
    useUserStore.setState({ currentUser: { pk: 1 } as UserType });

    render(<HeroDraftModal draftId={7} open onClose={() => {}} />);
    expect(calls).toEqual(['connect:7']);

    act(() => useUserStore.setState({ currentUser: { pk: 2 } as UserType }));
    expect(calls).toEqual([
      'connect:7',
      'disconnect',
      'clearChatError',
      'connect:7',
    ]);

    act(() => useUserStore.setState({ currentUser: { pk: 2 } as UserType }));
    expect(calls).toHaveLength(4);
  });
});
