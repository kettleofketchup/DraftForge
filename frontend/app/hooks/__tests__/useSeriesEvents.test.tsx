// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  getEvents: vi.fn(),
  cancelEvent: vi.fn(),
  deleteEvent: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import { useEventActionMutation, useEvents } from '../useEvent';

const SERIES_ID = 9;
const EVENT_ID = 21;
const ORG_ID = 3;

function setup(enabled = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const list = renderHook(
    () => useEvents({ event_repeater: SERIES_ID }, { enabled }),
    { wrapper },
  );
  const actions = renderHook(() => useEventActionMutation(EVENT_ID), {
    wrapper,
  });
  return { client, list, actions };
}

describe('series page events list', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getEvents.mockResolvedValue([]);
    api.cancelEvent.mockResolvedValue({ pk: EVENT_ID, organization: ORG_ID });
    api.deleteEvent.mockResolvedValue(undefined);
  });

  it('fetches the series events under the shared events key', async () => {
    const { client, list } = setup();
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true));
    expect(api.getEvents).toHaveBeenCalledWith({ event_repeater: SERIES_ID });
    expect(
      client.getQueryData(['events', { event_repeater: SERIES_ID }]),
    ).toEqual([]);
  });

  it.each(['cancelEvent', 'deleteEvent'] as const)(
    '%s refetches the series events',
    async (action) => {
      const { list, actions } = setup();
      await waitFor(() => expect(list.result.current.isSuccess).toBe(true));
      expect(api.getEvents).toHaveBeenCalledTimes(1);

      await act(async () => {
        await actions.result.current[action].mutateAsync();
      });

      await waitFor(() => expect(api.getEvents).toHaveBeenCalledTimes(2));
    },
  );

  it('does not fetch without a series id', () => {
    setup(false);
    expect(api.getEvents).not.toHaveBeenCalled();
  });
});
