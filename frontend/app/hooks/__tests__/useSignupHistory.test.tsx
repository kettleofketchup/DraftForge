// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SignupHistoryPage } from '~/components/events/schemas';

const api = vi.hoisted(() => ({
  getEventSignupHistory: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import {
  invalidateSignupHistory,
  removeSignupHistoryQueries,
  signupHistoryKey,
  useSignupHistory,
  type SignupHistoryFilters,
} from '../useEvent';

const EVENT_ID = 42;

function page(ids: number[], next: string | null): SignupHistoryPage {
  return {
    count: 3,
    next,
    previous: null,
    results: ids.map((id) => ({ id })),
  } as unknown as SignupHistoryPage;
}

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function render(
  client: QueryClient,
  eventId: number | undefined,
  filters: SignupHistoryFilters,
  enabled: boolean,
) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useSignupHistory(eventId, filters, enabled), {
    wrapper,
  });
}

describe('signupHistoryKey', () => {
  it('is the documented key shape', () => {
    expect(signupHistoryKey(EVENT_ID, { user: 5 })).toEqual([
      'event-signup-history',
      EVENT_ID,
      { user: 5 },
    ]);
  });
});

describe('useSignupHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('makes no request when disabled', async () => {
    const client = makeClient();
    const hook = render(client, EVENT_ID, {}, false);
    await act(async () => undefined);
    expect(api.getEventSignupHistory).not.toHaveBeenCalled();
    expect(hook.result.current.fetchStatus).toBe('idle');
  });

  it('makes no request without an event id', async () => {
    const client = makeClient();
    render(client, undefined, {}, true);
    await act(async () => undefined);
    expect(api.getEventSignupHistory).not.toHaveBeenCalled();
  });

  it('passes filters and then the cursor taken from next', async () => {
    api.getEventSignupHistory
      .mockResolvedValueOnce(
        page(
          [3, 2],
          'https://localhost/api/events/42/signup-history/?cursor=abc%7C2&user=5',
        ),
      )
      .mockResolvedValueOnce(page([1], null));
    const client = makeClient();
    const hook = render(client, EVENT_ID, { user: 5 }, true);

    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true));
    expect(api.getEventSignupHistory).toHaveBeenNthCalledWith(1, EVENT_ID, {
      user: 5,
    });
    expect(hook.result.current.hasNextPage).toBe(true);

    await act(async () => {
      await hook.result.current.fetchNextPage();
    });
    expect(api.getEventSignupHistory).toHaveBeenNthCalledWith(2, EVENT_ID, {
      user: 5,
      cursor: 'abc|2',
    });
    await waitFor(() =>
      expect(
        hook.result.current.data?.pages.flatMap((p) =>
          p.results.map((r) => r.id),
        ),
      ).toEqual([3, 2, 1]),
    );
    expect(hook.result.current.hasNextPage).toBe(false);
  });
});

describe('history cache helpers', () => {
  function seed(client: QueryClient) {
    const keys = {
      all: signupHistoryKey(EVENT_ID, {}),
      member: signupHistoryKey(EVENT_ID, { user: 5 }),
      action: signupHistoryKey(EVENT_ID, { action: 'withdrew' }),
      otherEvent: signupHistoryKey(EVENT_ID + 1, {}),
    };
    for (const key of Object.values(keys)) {
      client.setQueryData(key, { pages: [], pageParams: [] });
    }
    return keys;
  }

  it('invalidateSignupHistory marks every filter of the event only', () => {
    const client = makeClient();
    const keys = seed(client);
    invalidateSignupHistory(client, EVENT_ID);
    const invalid = (key: readonly unknown[]) =>
      client.getQueryState(key)?.isInvalidated ?? false;
    expect(invalid(keys.all)).toBe(true);
    expect(invalid(keys.member)).toBe(true);
    expect(invalid(keys.action)).toBe(true);
    expect(invalid(keys.otherEvent)).toBe(false);
  });

  it('removeSignupHistoryQueries drops every filter of the event only', () => {
    const client = makeClient();
    const keys = seed(client);
    removeSignupHistoryQueries(client, EVENT_ID);
    expect(client.getQueryData(keys.all)).toBeUndefined();
    expect(client.getQueryData(keys.member)).toBeUndefined();
    expect(client.getQueryData(keys.action)).toBeUndefined();
    expect(client.getQueryData(keys.otherEvent)).toBeDefined();
  });
});
