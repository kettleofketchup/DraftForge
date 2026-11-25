// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SignupBody } from '~/components/api/eventsAPI';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';

const api = vi.hoisted(() => ({ signupForEvent: vi.fn() }));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import { useSignupMutation } from '../useEvent';

const EVENT = 5;
const USER_PK = 7;
const POSITIONS = {
  carry: 2,
  mid: 1,
  offlane: 4,
  soft_support: 5,
  hard_support: 3,
};

async function signUp(body: SignupBody) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(['userProfile', USER_PK], { pk: USER_PK });
  client.setQueryData(['user', USER_PK], { pk: USER_PK });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useSignupMutation(EVENT), { wrapper });
  await act(() => result.current.mutateAsync(body));
  return client;
}

describe('useSignupMutation profile caches', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.signupForEvent.mockResolvedValue({ id: 1, status: 'confirmed' });
    useUserStore.setState({
      currentUser: { pk: USER_PK, username: 'player' } as UserType,
    });
  });

  it('drops the Edit Profile query and invalidates the profile page when positions are submitted', async () => {
    const client = await signUp({
      intent: 'rsvp',
      profile: { positions: POSITIONS },
    });
    expect(client.getQueryState(['userProfile', USER_PK])).toBeUndefined();
    expect(client.getQueryState(['user', USER_PK])?.isInvalidated).toBe(true);
  });

  it('keeps both caches when no positions are submitted', async () => {
    const client = await signUp({ intent: 'rsvp', profile: {} });
    expect(client.getQueryData(['userProfile', USER_PK])).toEqual({
      pk: USER_PK,
    });
    expect(client.getQueryState(['user', USER_PK])?.isInvalidated).toBe(false);
  });
});
