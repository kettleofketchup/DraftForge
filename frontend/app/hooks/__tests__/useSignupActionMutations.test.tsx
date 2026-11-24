// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventSignupType } from '~/components/events/schemas';

const api = vi.hoisted(() => ({
  getEventSignups: vi.fn(),
  confirmSignup: vi.fn(),
  rejectSignup: vi.fn(),
  signupForEvent: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import {
  signupHistoryKey,
  useOptimisticEventSignups,
  useSignupActionMutations,
  useSignupMutation,
} from '../useEvent';

const EVENT_ID = 42;

function signup(id: number, status: string): EventSignupType {
  return { id, status, user: id } as unknown as EventSignupType;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(
    () => ({
      list: useOptimisticEventSignups(EVENT_ID, 'roll_call'),
      actions: useSignupActionMutations(EVENT_ID),
    }),
    { wrapper },
  );
  return { client, hook };
}

const statuses = (list: EventSignupType[]) => list.map((s) => s.status);

describe('signup actions update rows before the server answers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getEventSignups.mockResolvedValue([
      signup(1, 'approved'),
      signup(2, 'approved'),
      signup(3, 'approved'),
    ]);
  });

  it('applies several in-flight actions at once and refetches only after the last', async () => {
    const { hook } = setup();
    await waitFor(() =>
      expect(hook.result.current.list.signups).toHaveLength(3),
    );
    expect(api.getEventSignups).toHaveBeenCalledTimes(1);

    const first = deferred<EventSignupType>();
    const second = deferred<EventSignupType>();
    api.confirmSignup
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    act(() => {
      hook.result.current.actions.confirm.mutate(1);
      hook.result.current.actions.confirm.mutate(2);
    });

    await waitFor(() =>
      expect(statuses(hook.result.current.list.signups)).toEqual([
        'confirmed',
        'confirmed',
        'approved',
      ]),
    );
    expect([...hook.result.current.list.pendingIds].sort()).toEqual([1, 2]);

    const untouched = hook.result.current.list.signups[2];

    await act(async () => first.resolve(signup(1, 'confirmed')));
    await waitFor(() =>
      expect([...hook.result.current.list.pendingIds]).toEqual([2]),
    );
    expect(api.getEventSignups).toHaveBeenCalledTimes(1);
    expect(statuses(hook.result.current.list.signups)).toEqual([
      'confirmed',
      'confirmed',
      'approved',
    ]);
    expect(hook.result.current.list.signups[2]).toBe(untouched);

    api.getEventSignups.mockResolvedValue([
      signup(1, 'confirmed'),
      signup(2, 'confirmed'),
      signup(3, 'approved'),
    ]);
    await act(async () => second.resolve(signup(2, 'confirmed')));
    await waitFor(() => expect(api.getEventSignups).toHaveBeenCalledTimes(2));
    expect(hook.result.current.list.pendingIds.size).toBe(0);
  });

  it('rolls a failed row back without touching the others', async () => {
    const { hook } = setup();
    await waitFor(() =>
      expect(hook.result.current.list.signups).toHaveLength(3),
    );

    const fails = deferred<EventSignupType>();
    const holds = deferred<EventSignupType>();
    api.rejectSignup.mockReturnValueOnce(fails.promise);
    api.confirmSignup.mockReturnValueOnce(holds.promise);

    act(() => {
      hook.result.current.actions.reject.mutate(1);
      hook.result.current.actions.confirm.mutate(2);
    });
    await waitFor(() =>
      expect(statuses(hook.result.current.list.signups)).toEqual([
        'rejected',
        'confirmed',
        'approved',
      ]),
    );

    await act(async () => {
      fails.reject(new Error('boom'));
      await fails.promise.catch(() => undefined);
    });
    await waitFor(() =>
      expect(statuses(hook.result.current.list.signups)).toEqual([
        'approved',
        'confirmed',
        'approved',
      ]),
    );
    expect(api.getEventSignups).toHaveBeenCalledTimes(1);

    await act(async () => holds.resolve(signup(2, 'confirmed')));
    await waitFor(() => expect(api.getEventSignups).toHaveBeenCalledTimes(2));
  });
});

describe('signup mutations refresh the signup history', () => {
  const historyKeys = {
    all: signupHistoryKey(EVENT_ID, {}),
    member: signupHistoryKey(EVENT_ID, { user: 5, action: 'withdrew' }),
    otherEvent: signupHistoryKey(EVENT_ID + 1, {}),
  };

  function seedHistory(client: QueryClient) {
    for (const key of Object.values(historyKeys)) {
      client.setQueryData(key, { pages: [], pageParams: [] });
    }
    return (key: readonly unknown[]) =>
      client.getQueryState(key)?.isInvalidated ?? false;
  }

  beforeEach(() => {
    vi.clearAllMocks();
    api.getEventSignups.mockResolvedValue([signup(1, 'approved')]);
  });

  it('invalidates every filter of this event after a staff action settles', async () => {
    const { client, hook } = setup();
    const invalid = seedHistory(client);
    api.confirmSignup.mockResolvedValueOnce(signup(1, 'confirmed'));

    await act(async () => {
      await hook.result.current.actions.confirm.mutateAsync(1);
    });

    await waitFor(() => expect(invalid(historyKeys.all)).toBe(true));
    expect(invalid(historyKeys.member)).toBe(true);
    expect(invalid(historyKeys.otherEvent)).toBe(false);
  });

  it('invalidates every filter of this event after a failed staff action', async () => {
    const { client, hook } = setup();
    const invalid = seedHistory(client);
    api.rejectSignup.mockRejectedValueOnce(new Error('boom'));

    await act(async () => {
      await hook.result.current.actions.reject
        .mutateAsync(1)
        .catch(() => undefined);
    });

    await waitFor(() => expect(invalid(historyKeys.all)).toBe(true));
    expect(invalid(historyKeys.member)).toBe(true);
    expect(invalid(historyKeys.otherEvent)).toBe(false);
  });

  it('invalidates every filter of this event after a signup succeeds', async () => {
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const invalid = seedHistory(client);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const hook = renderHook(() => useSignupMutation(EVENT_ID), { wrapper });
    api.signupForEvent.mockResolvedValueOnce(signup(9, 'rsvp'));

    await act(async () => {
      await hook.result.current.mutateAsync({} as never);
    });

    expect(invalid(historyKeys.all)).toBe(true);
    expect(invalid(historyKeys.member)).toBe(true);
    expect(invalid(historyKeys.otherEvent)).toBe(false);
  });
});
