// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventType } from '~/components/events/schemas';
import {
  contributionsKeys,
  leadershipKeys,
  standingKeys,
} from '~/features/org-features/queryKeys';

const api = vi.hoisted(() => ({
  completeEvent: vi.fn(),
  cancelEvent: vi.fn(),
  reopenSignups: vi.fn(),
  deleteEvent: vi.fn(),
  updateEvent: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import { useEventActionMutation, useUpdateEventMutation } from '../useEvent';

const EVENT = 5;
const ORG = 3;
const OTHER_ORG = 4;
const event = { pk: EVENT, organization: ORG } as unknown as EventType;

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const keys = {
    leadershipBoard: standingKeys.leaderboard(
      ORG,
      11,
      'leadership',
      'points',
      'all',
    ),
    anonLeadershipBoard: standingKeys.leaderboard(
      ORG,
      null,
      'leadership',
      'rating',
      'current',
    ),
    leadershipPending: leadershipKeys.pending(ORG, 11, EVENT),
    contribEntries: contributionsKeys.entries(ORG, 11, { page: 1 }),
    otherLeadershipBoard: standingKeys.leaderboard(
      OTHER_ORG,
      11,
      'leadership',
      'points',
      'all',
    ),
  };
  for (const key of Object.values(keys)) client.setQueryData(key, {});
  client.setQueryData(['event', EVENT], event);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(
    () => ({
      event: useEventActionMutation(EVENT),
      update: useUpdateEventMutation(EVENT),
    }),
    { wrapper },
  );
  const invalid = (key: readonly unknown[]) =>
    client.getQueryState(key)?.isInvalidated ?? false;
  const thisOrgInvalid = () =>
    invalid(keys.leadershipBoard) &&
    invalid(keys.anonLeadershipBoard) &&
    invalid(keys.leadershipPending) &&
    invalid(keys.contribEntries);
  return { hook, keys, invalid, thisOrgInvalid };
}

describe('event mutations refresh the org standing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const name of [
      'completeEvent',
      'cancelEvent',
      'reopenSignups',
      'updateEvent',
    ] as const)
      api[name].mockResolvedValue(event);
    api.deleteEvent.mockResolvedValue(undefined);
  });

  it.each([
    'completeEvent',
    'cancelEvent',
    'reopenSignups',
    'deleteEvent',
  ] as const)(
    '%s refreshes this org’s leadership and contributions only',
    async (name) => {
      const { hook, keys, invalid, thisOrgInvalid } = setup();
      await act(async () => {
        await hook.result.current.event[name].mutateAsync();
      });
      expect(thisOrgInvalid()).toBe(true);
      expect(invalid(keys.otherLeadershipBoard)).toBe(false);
    },
  );

  it('editing the event refreshes this org’s leadership and contributions', async () => {
    const { hook, keys, invalid, thisOrgInvalid } = setup();
    await act(() =>
      hook.result.current.update.mutateAsync({ name: 'Renamed' } as never),
    );
    expect(thisOrgInvalid()).toBe(true);
    expect(invalid(keys.otherLeadershipBoard)).toBe(false);
  });
});
