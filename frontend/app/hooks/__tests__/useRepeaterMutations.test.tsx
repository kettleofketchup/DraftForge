// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { conductKeys } from '~/features/org-features/queryKeys';

const api = vi.hoisted(() => ({
  createEvent: vi.fn(),
  createEventRepeater: vi.fn(),
  deleteEventRepeater: vi.fn(),
  subscribeToRepeater: vi.fn(),
  unsubscribeFromRepeater: vi.fn(),
  updateEventRepeater: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import {
  repeaterKeys,
  useCreateEventMutation,
  useCreateEventRepeaterMutation,
  useDeleteEventRepeaterMutation,
  useRepeaterSubscriptionMutation,
  useUpdateEventRepeaterMutation,
} from '../useEvent';

const ORG = 3;
const REPEATER = 7;
const OTHER = 8;

const KEYS = {
  allEvents: ['events', { ordering: 'closest' }],
  orgEvents: ['events', { organization: ORG, ordering: 'closest' }],
  allRepeaters: repeaterKeys.list(undefined),
  orgRepeaters: repeaterKeys.list({ organization: ORG }),
  detail: repeaterKeys.detail(REPEATER),
  subscribers: repeaterKeys.subscribers(REPEATER),
  repeaterEvents: repeaterKeys.events(REPEATER),
  otherDetail: repeaterKeys.detail(OTHER),
  forecast: conductKeys.forecast(ORG, 11, 5),
};

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  for (const key of Object.values(KEYS)) client.setQueryData(key, {});
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

function isStale(client: QueryClient, key: readonly unknown[]) {
  return client.getQueryState(key)?.isInvalidated ?? false;
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset().mockResolvedValue({}));
});

describe('repeater mutations', () => {
  it('subscribe refreshes every series view for that repeater', async () => {
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useRepeaterSubscriptionMutation(), {
      wrapper,
    });

    await act(() => result.current.subscribe.mutateAsync(REPEATER));

    expect(api.subscribeToRepeater).toHaveBeenCalledWith(REPEATER);
    expect(isStale(client, KEYS.allRepeaters)).toBe(true);
    expect(isStale(client, KEYS.orgRepeaters)).toBe(true);
    expect(isStale(client, KEYS.detail)).toBe(true);
    expect(isStale(client, KEYS.subscribers)).toBe(true);
    expect(isStale(client, KEYS.otherDetail)).toBe(false);
  });

  it('unsubscribe refreshes every series view for that repeater', async () => {
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useRepeaterSubscriptionMutation(), {
      wrapper,
    });

    await act(() => result.current.unsubscribe.mutateAsync(REPEATER));

    expect(api.unsubscribeFromRepeater).toHaveBeenCalledWith(REPEATER);
    expect(isStale(client, KEYS.orgRepeaters)).toBe(true);
    expect(isStale(client, KEYS.detail)).toBe(true);
    expect(isStale(client, KEYS.subscribers)).toBe(true);
  });

  it('update refreshes both series lists and the detail', async () => {
    const { client, wrapper } = setup();
    const { result } = renderHook(
      () => useUpdateEventRepeaterMutation(REPEATER),
      { wrapper },
    );

    await act(() => result.current.mutateAsync({ name: 'Renamed' }));

    expect(isStale(client, KEYS.allRepeaters)).toBe(true);
    expect(isStale(client, KEYS.orgRepeaters)).toBe(true);
    expect(isStale(client, KEYS.detail)).toBe(true);
    expect(isStale(client, KEYS.allEvents)).toBe(true);
  });

  it('delete drops the series and refreshes the event lists', async () => {
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useDeleteEventRepeaterMutation(), {
      wrapper,
    });

    await act(() =>
      result.current.mutateAsync({ id: REPEATER, organization: ORG }),
    );

    expect(api.deleteEventRepeater).toHaveBeenCalledWith(REPEATER);
    expect(client.getQueryState(KEYS.detail)).toBeUndefined();
    expect(client.getQueryState(KEYS.repeaterEvents)).toBeUndefined();
    expect(isStale(client, KEYS.allEvents)).toBe(true);
    expect(isStale(client, KEYS.orgEvents)).toBe(true);
    expect(isStale(client, KEYS.allRepeaters)).toBe(true);
    expect(isStale(client, KEYS.orgRepeaters)).toBe(true);
    expect(isStale(client, KEYS.forecast)).toBe(true);
    expect(isStale(client, KEYS.otherDetail)).toBe(false);
  });

  it('creating a series refreshes every event and series list', async () => {
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useCreateEventRepeaterMutation(), {
      wrapper,
    });

    await act(() => result.current.mutateAsync({ name: 'Weekly' }));

    expect(isStale(client, KEYS.allEvents)).toBe(true);
    expect(isStale(client, KEYS.orgEvents)).toBe(true);
    expect(isStale(client, KEYS.allRepeaters)).toBe(true);
    expect(isStale(client, KEYS.orgRepeaters)).toBe(true);
  });

  it('creating an event refreshes the unfiltered list and passes openSignups', async () => {
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useCreateEventMutation(), { wrapper });

    await act(() =>
      result.current.mutateAsync({
        payload: { name: 'Night 5' },
        openSignups: true,
      }),
    );

    expect(api.createEvent).toHaveBeenCalledWith({ name: 'Night 5' }, true);
    expect(isStale(client, KEYS.allEvents)).toBe(true);
    expect(isStale(client, KEYS.orgEvents)).toBe(true);
    expect(isStale(client, KEYS.orgRepeaters)).toBe(true);
  });
});
