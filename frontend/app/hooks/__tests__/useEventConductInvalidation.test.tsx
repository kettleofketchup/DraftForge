// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventSignupType, EventType } from '~/components/events/schemas';
import { conductKeys, standingKeys } from '~/features/org-features/queryKeys';

const api = vi.hoisted(() => ({
  signupForEvent: vi.fn(),
  openSignups: vi.fn(),
  startRollCall: vi.fn(),
  startTournament: vi.fn(),
  cancelEvent: vi.fn(),
  deleteEvent: vi.fn(),
  reopenSignups: vi.fn(),
  restartTournament: vi.fn(),
  completeEvent: vi.fn(),
  setEventStaff: vi.fn(),
  updateEvent: vi.fn(),
  confirmSignup: vi.fn(),
  getEventSignups: vi.fn(),
  getEvent: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import {
  useEventActionMutation,
  useSignupActionMutations,
  useSignupMutation,
  useUpdateEventMutation,
} from '../useEvent';

const EVENT = 5;
const ORG = 3;
const OTHER_ORG = 4;
const event = { pk: EVENT, organization: ORG } as unknown as EventType;
const signup = { id: 3, status: 'confirmed', user: 3 } as EventSignupType;

function setup(seedEvent = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const keys = {
    forecast: conductKeys.forecast(ORG, 11, EVENT),
    attendance: conductKeys.attendance(ORG, 11, EVENT),
    conductBoard: standingKeys.leaderboard(
      ORG,
      11,
      'conduct',
      'show_rate',
      'current',
    ),
    contribBoard: standingKeys.leaderboard(
      ORG,
      11,
      'contribution',
      'points',
      'all',
    ),
    otherForecast: conductKeys.forecast(OTHER_ORG, 11, 9),
  };
  for (const key of Object.values(keys)) client.setQueryData(key, {});
  if (seedEvent) client.setQueryData(['event', EVENT], event);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(
    () => ({
      signup: useSignupMutation(EVENT),
      event: useEventActionMutation(EVENT),
      update: useUpdateEventMutation(EVENT),
      signups: useSignupActionMutations(EVENT),
    }),
    { wrapper },
  );
  const invalid = (key: readonly unknown[]) =>
    client.getQueryState(key)?.isInvalidated ?? false;
  const thisOrgConductInvalid = () =>
    invalid(keys.forecast) &&
    invalid(keys.attendance) &&
    invalid(keys.conductBoard);
  return { hook, keys, invalid, thisOrgConductInvalid };
}

describe('event mutations refresh conduct queries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const name of [
      'openSignups',
      'startRollCall',
      'startTournament',
      'cancelEvent',
      'reopenSignups',
      'restartTournament',
      'completeEvent',
      'setEventStaff',
      'updateEvent',
      'getEvent',
    ] as const)
      api[name].mockResolvedValue(event);
    api.deleteEvent.mockResolvedValue(undefined);
    api.signupForEvent.mockResolvedValue(signup);
    api.confirmSignup.mockResolvedValue(signup);
    api.getEventSignups.mockResolvedValue([signup]);
  });

  it.each([
    'startRollCall',
    'startTournament',
    'reopenSignups',
    'cancelEvent',
    'restartTournament',
    'completeEvent',
  ] as const)('%s refreshes this org’s conduct queries only', async (name) => {
    const { hook, keys, invalid, thisOrgConductInvalid } = setup();
    await act(() => hook.result.current.event[name].mutateAsync());
    expect(thisOrgConductInvalid()).toBe(true);
    expect(invalid(keys.otherForecast)).toBe(false);
  });

  it('updating the event (capacity, approval mode) refreshes this org’s conduct queries', async () => {
    const { hook, keys, invalid, thisOrgConductInvalid } = setup();
    await act(() =>
      hook.result.current.update.mutateAsync({ max_players: 20 } as never),
    );
    expect(thisOrgConductInvalid()).toBe(true);
    expect(invalid(keys.otherForecast)).toBe(false);
  });

  it('deleteEvent refreshes conduct queries', async () => {
    const { hook, keys, invalid } = setup();
    await act(() => hook.result.current.event.deleteEvent.mutateAsync());
    expect(invalid(keys.forecast)).toBe(true);
    expect(invalid(keys.conductBoard)).toBe(true);
  });

  it('openSignups and setEventStaff leave conduct alone', async () => {
    const { hook, keys, invalid } = setup();
    await act(() => hook.result.current.event.openSignups.mutateAsync());
    await act(() =>
      hook.result.current.event.setEventStaff.mutateAsync({
        host_id: null,
        helper_ids: [],
      } as never),
    );
    expect(invalid(keys.forecast)).toBe(false);
    expect(invalid(keys.attendance)).toBe(false);
    expect(invalid(keys.conductBoard)).toBe(false);
  });

  it('a signup action refreshes the event org’s forecast once the last action settles', async () => {
    let releaseFirst: (value: EventSignupType) => void = () => {};
    api.confirmSignup
      .mockImplementationOnce(
        () =>
          new Promise<EventSignupType>((resolve) => {
            releaseFirst = resolve;
          }),
      )
      .mockResolvedValueOnce(signup);
    const { hook, keys, invalid, thisOrgConductInvalid } = setup(true);
    let first: Promise<unknown> = Promise.resolve();
    act(() => {
      first = hook.result.current.signups.confirm.mutateAsync(3);
    });
    await act(() => hook.result.current.signups.confirm.mutateAsync(4));
    expect(invalid(keys.forecast)).toBe(false);
    await act(async () => {
      releaseFirst(signup);
      await first;
    });
    expect(thisOrgConductInvalid()).toBe(true);
    expect(invalid(keys.otherForecast)).toBe(false);
  });

  it('self signup refreshes the event org’s conduct queries', async () => {
    const { hook, keys, invalid, thisOrgConductInvalid } = setup(true);
    await act(() => hook.result.current.signup.mutateAsync({ intent: 'rsvp' }));
    expect(thisOrgConductInvalid()).toBe(true);
    expect(invalid(keys.otherForecast)).toBe(false);
  });
});
