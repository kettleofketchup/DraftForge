// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  contributionsKeys,
  promotionKeys,
  standingKeys,
} from '~/features/org-features/queryKeys';

const api = vi.hoisted(() => ({
  cancelEvent: vi.fn(),
  completeEvent: vi.fn(),
  deleteEvent: vi.fn(),
  openSignups: vi.fn(),
  reopenSignups: vi.fn(),
  restartTournament: vi.fn(),
  setEventStaff: vi.fn(),
  startRollCall: vi.fn(),
  startTournament: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import { signupHistoryKey, useEventActionMutation } from '../useEvent';

const EVENT_ID = 7;
const ORG_ID = 3;
const OTHER_ORG = 4;

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const keys = {
    contribBoard: standingKeys.leaderboard(
      ORG_ID,
      11,
      'contribution',
      'points',
      'all',
    ),
    anonContribBoard: standingKeys.leaderboard(
      ORG_ID,
      null,
      'contribution',
      'points',
      'all',
    ),
    conductBoard: standingKeys.leaderboard(
      ORG_ID,
      11,
      'conduct',
      'show_rate',
      'current',
    ),
    otherOrgBoard: standingKeys.leaderboard(
      OTHER_ORG,
      11,
      'contribution',
      'points',
      'all',
    ),
    member: contributionsKeys.member(ORG_ID, 11, 5, 'all'),
  };
  for (const key of Object.values(keys)) client.setQueryData(key, {});
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(({ eventId }) => useEventActionMutation(eventId), {
    wrapper,
    initialProps: { eventId: EVENT_ID },
  });
  const invalid = (key: readonly unknown[]) =>
    client.getQueryState(key)?.isInvalidated ?? false;
  return { hook, keys, invalid, client };
}

describe('useEventActionMutation contribution invalidation', () => {
  beforeEach(() => {
    api.completeEvent.mockResolvedValue({ pk: EVENT_ID, organization: ORG_ID });
    api.setEventStaff.mockResolvedValue({ pk: EVENT_ID, organization: ORG_ID });
  });

  it.each(['completeEvent', 'setEventStaff'] as const)(
    '%s refreshes contributions for every viewer',
    async (action) => {
      const { hook, keys, invalid } = setup();
      await act(async () => {
        if (action === 'completeEvent') {
          await hook.result.current.completeEvent.mutateAsync();
        } else {
          await hook.result.current.setEventStaff.mutateAsync({
            host: null,
            helpers: [],
          } as never);
        }
      });
      expect(invalid(keys.contribBoard)).toBe(true);
      expect(invalid(keys.anonContribBoard)).toBe(true);
      expect(invalid(keys.member)).toBe(true);
      expect(invalid(keys.conductBoard)).toBe(action === 'completeEvent');
      expect(invalid(keys.otherOrgBoard)).toBe(false);
    },
  );
});

describe('useEventActionMutation signup history invalidation', () => {
  const actions = [
    'openSignups',
    'startRollCall',
    'reopenSignups',
    'startTournament',
    'cancelEvent',
    'restartTournament',
    'completeEvent',
    'setEventStaff',
  ] as const;

  beforeEach(() => {
    api.deleteEvent.mockResolvedValue(undefined);
    for (const action of actions) {
      api[action].mockResolvedValue({ pk: EVENT_ID, organization: ORG_ID });
    }
  });

  it.each(actions)('%s refreshes this event history only', async (action) => {
    const { hook, client, invalid } = setup();
    const keys = {
      all: signupHistoryKey(EVENT_ID, {}),
      member: signupHistoryKey(EVENT_ID, { user: 5 }),
      otherEvent: signupHistoryKey(EVENT_ID + 1, {}),
    };
    for (const key of Object.values(keys)) {
      client.setQueryData(key, { pages: [], pageParams: [] });
    }
    await act(async () => {
      await (
        hook.result.current[action].mutateAsync as (v?: unknown) => unknown
      )({ host: null, helpers: [] });
    });
    expect(invalid(keys.all)).toBe(true);
    expect(invalid(keys.member)).toBe(true);
    expect(invalid(keys.otherEvent)).toBe(false);
  });

  it('deleteEvent drops this event history and keeps other events', async () => {
    const { hook, client } = setup();
    const own = signupHistoryKey(EVENT_ID, { user: 5 });
    const other = signupHistoryKey(EVENT_ID + 1, {});
    client.setQueryData(signupHistoryKey(EVENT_ID, {}), { pages: [] });
    client.setQueryData(own, { pages: [] });
    client.setQueryData(other, { pages: [] });
    await act(async () => {
      await hook.result.current.deleteEvent.mutateAsync();
    });
    expect(
      client.getQueryCache().findAll({
        queryKey: ['event-signup-history', EVENT_ID],
      }),
    ).toHaveLength(0);
    expect(client.getQueryData(other)).toBeDefined();
  });
});

describe('lifecycle preservation mutations', () => {
  beforeEach(() => {
    api.cancelEvent
      .mockReset()
      .mockResolvedValue({ id: EVENT_ID, organization: ORG_ID });
    api.deleteEvent.mockReset().mockResolvedValue(undefined);
  });

  it('propagates delete confirmation explicitly without upgrading default callers', async () => {
    const { hook } = setup();
    await act(async () => {
      await hook.result.current.deleteEvent.mutateAsync();
      await hook.result.current.deleteEvent.mutateAsync({ confirm: false });
      await hook.result.current.deleteEvent.mutateAsync({ confirm: true });
    });
    expect(api.deleteEvent.mock.calls).toEqual([
      [EVENT_ID, undefined],
      [EVENT_ID, { confirm: false }],
      [EVENT_ID, { confirm: true }],
    ]);
  });

  it('refreshes this event signups on cancel and awaits its result', async () => {
    const { hook, client, invalid } = setup();
    const own = ['event-signups', EVENT_ID];
    const other = ['event-signups', EVENT_ID + 1];
    client.setQueryData(own, [{ id: 1 }]);
    client.setQueryData(other, [{ id: 2 }]);
    await act(async () => {
      await hook.result.current.cancelEvent.mutateAsync({
        reason: 'Schedule changed',
      });
    });
    expect(api.cancelEvent).toHaveBeenCalledWith(EVENT_ID, {
      reason: 'Schedule changed',
    });
    expect(invalid(own)).toBe(true);
    expect(invalid(other)).toBe(false);
  });

  it('removes only the deleted event detail, signup and history caches', async () => {
    const { hook, client } = setup();
    const own = [
      ['event', EVENT_ID],
      ['event-signups', EVENT_ID],
      ['event-signup-history', EVENT_ID, {}],
    ];
    const other = [
      ['event', EVENT_ID + 1],
      ['event-signups', EVENT_ID + 1],
      ['event-signup-history', EVENT_ID + 1, {}],
    ];
    for (const key of [...own, ...other]) client.setQueryData(key, {});
    await act(async () => {
      await hook.result.current.deleteEvent.mutateAsync({ confirm: true });
    });
    for (const key of own) expect(client.getQueryData(key)).toBeUndefined();
    for (const key of other) expect(client.getQueryData(key)).toBeDefined();
  });

  it('does not retry a rejected delete or remove caches', async () => {
    const { hook, client } = setup();
    const own = ['event', EVENT_ID];
    client.setQueryData(own, { id: EVENT_ID });
    const failure = {
      response: {
        status: 409,
        data: { error: 'has_signup_records', count: 3 },
      },
    };
    api.deleteEvent.mockRejectedValue(failure);
    await act(async () => {
      await expect(hook.result.current.deleteEvent.mutateAsync()).rejects.toBe(
        failure,
      );
    });
    expect(api.deleteEvent).toHaveBeenCalledOnce();
    expect(client.getQueryData(own)).toEqual({ id: EVENT_ID });
  });
});

describe('lifecycle mutations keep the original event across route changes', () => {
  const nextId = EVENT_ID + 1;
  const nextEvent = {
    id: nextId,
    organization: OTHER_ORG,
    state: 'signups_open',
  };
  const originalEvent = {
    id: EVENT_ID,
    organization: ORG_ID,
    state: 'signups_open',
  };
  const signupA = ['event-signups', EVENT_ID];
  const signupB = ['event-signups', nextId];
  const historyA = signupHistoryKey(EVENT_ID, {});
  const historyB = signupHistoryKey(nextId, {});

  beforeEach(() => {
    api.cancelEvent.mockReset();
    api.deleteEvent.mockReset();
  });

  function seed(client: QueryClient) {
    client.setQueryData(['event', EVENT_ID], originalEvent);
    client.setQueryData(['event', nextId], nextEvent);
    client.setQueryData(signupA, [{ id: 71 }]);
    client.setQueryData(signupB, [{ id: 81 }]);
    client.setQueryData(historyA, { pages: ['A'] });
    client.setQueryData(historyB, { pages: ['B'] });
  }

  it('cancellation updates and invalidates A, not the newly rendered B', async () => {
    const { hook, client, invalid, keys } = setup();
    seed(client);
    const response = { ...originalEvent, state: 'cancelled' };
    let finish!: (data: typeof response) => void;
    api.cancelEvent.mockReturnValue(
      new Promise<typeof response>((resolve) => {
        finish = resolve;
      }),
    );
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    let request!: Promise<unknown>;
    act(() => {
      request = hook.result.current.cancelEvent.mutateAsync({
        reason: 'Schedule changed',
      });
    });
    await waitFor(() => expect(api.cancelEvent).toHaveBeenCalledOnce());
    hook.rerender({ eventId: nextId });
    await act(async () => {
      finish(response);
      await request;
    });

    expect(api.cancelEvent.mock.calls).toEqual([
      [EVENT_ID, { reason: 'Schedule changed' }],
    ]);
    expect(client.getQueryData(['event', EVENT_ID])).toEqual(response);
    expect(client.getQueryData(['event', nextId])).toEqual(nextEvent);
    expect(invalid(signupA)).toBe(true);
    expect(invalid(historyA)).toBe(true);
    expect(invalid(signupB)).toBe(false);
    expect(invalid(historyB)).toBe(false);
    expect(invalid(keys.contribBoard)).toBe(true);
    expect(invalid(keys.otherOrgBoard)).toBe(false);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: signupA });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ['event-signup-history', EVENT_ID],
    });
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: signupB });
    expect(invalidate).not.toHaveBeenCalledWith({
      queryKey: ['event-signup-history', nextId],
    });
  });

  it.each([undefined, { confirm: true }])(
    'deletion %j removes A caches and invalidates A organization, leaving B untouched',
    async (options) => {
      const { hook, client, invalid, keys } = setup();
      seed(client);
      const promotionA = promotionKeys.events(ORG_ID, 11);
      const promotionB = promotionKeys.events(OTHER_ORG, 11);
      client.setQueryData(promotionA, []);
      client.setQueryData(promotionB, []);
      let finish!: () => void;
      api.deleteEvent.mockReturnValue(
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
      );
      const remove = vi.spyOn(client, 'removeQueries');
      let request!: Promise<unknown>;
      act(() => {
        request = hook.result.current.deleteEvent.mutateAsync(options);
      });
      await waitFor(() => expect(api.deleteEvent).toHaveBeenCalledOnce());
      hook.rerender({ eventId: nextId });
      await act(async () => {
        finish();
        await request;
      });

      expect(api.deleteEvent.mock.calls).toEqual([[EVENT_ID, options]]);
      for (const key of [['event', EVENT_ID], signupA, historyA]) {
        expect(client.getQueryData(key)).toBeUndefined();
      }
      expect(client.getQueryData(['event', nextId])).toEqual(nextEvent);
      expect(client.getQueryData(signupB)).toEqual([{ id: 81 }]);
      expect(client.getQueryData(historyB)).toEqual({ pages: ['B'] });
      expect(invalid(keys.contribBoard)).toBe(true);
      expect(invalid(keys.otherOrgBoard)).toBe(false);
      expect(invalid(promotionA)).toBe(true);
      expect(invalid(promotionB)).toBe(false);
      expect(remove).toHaveBeenCalledWith({ queryKey: ['event', EVENT_ID] });
      expect(remove).toHaveBeenCalledWith({ queryKey: signupA });
      expect(remove).toHaveBeenCalledWith({
        queryKey: ['event-signup-history', EVENT_ID],
      });
      expect(remove).not.toHaveBeenCalledWith({ queryKey: ['event', nextId] });
    },
  );

  it.each(['cancelEvent', 'deleteEvent'] as const)(
    '%s keeps A as network target if the route changes before dispatch',
    async (action) => {
      const { hook, client } = setup();
      seed(client);
      let release!: () => void;
      let entered!: () => void;
      const started = new Promise<void>((resolve) => {
        entered = resolve;
      });
      const barrier = new Promise<void>((resolve) => {
        release = resolve;
      });
      client.getMutationCache().config.onMutate = async () => {
        entered();
        await barrier;
      };
      api.cancelEvent.mockResolvedValue({
        ...originalEvent,
        state: 'cancelled',
      });
      api.deleteEvent.mockResolvedValue(undefined);
      let request!: Promise<unknown>;
      act(() => {
        request = hook.result.current[action].mutateAsync();
      });
      await started;
      hook.rerender({ eventId: nextId });
      await act(async () => {
        release();
        await request;
      });
      expect(api[action].mock.calls).toEqual([[EVENT_ID, undefined]]);
      expect(client.getQueryData(['event', nextId])).toEqual(nextEvent);
    },
  );
});
