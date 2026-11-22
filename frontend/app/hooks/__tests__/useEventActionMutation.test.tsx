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
  completeEvent: vi.fn(),
  setEventStaff: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import { useEventActionMutation } from '../useEvent';

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
  return { hook, keys, invalid };
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
