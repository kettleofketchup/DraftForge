// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  contributionsKeys,
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
  const hook = renderHook(() => useEventActionMutation(EVENT_ID), { wrapper });
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
