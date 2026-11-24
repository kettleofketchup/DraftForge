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
