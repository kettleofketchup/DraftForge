// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventSignupType, EventType } from '~/components/events/schemas';

const api = vi.hoisted(() => ({
  signupForEvent: vi.fn(),
  openSignups: vi.fn(),
  startRollCall: vi.fn(),
  startTournament: vi.fn(),
  reopenSignups: vi.fn(),
  cancelEvent: vi.fn(),
  deleteEvent: vi.fn(),
  restartTournament: vi.fn(),
  completeEvent: vi.fn(),
  approveSignup: vi.fn(),
  confirmSignup: vi.fn(),
  cancelSignup: vi.fn(),
  getEvent: vi.fn(),
  getEventSignups: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  ...api,
}));

import {
  useEventActionMutation,
  useSignupActionMutations,
  useSignupMutation,
} from '../useEvent';

const EVENT = 5;
const event = { pk: EVENT, organization: 3 } as unknown as EventType;
const signup = { id: 3, status: 'confirmed', user: 3 } as EventSignupType;
const LIST_KEYS = [
  ['events', { states: ['upcoming', 'signups_open'] }],
  ['events', { organization: 3 }],
  ['events', { event_repeater: 8 }],
] as const;

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  for (const key of LIST_KEYS) client.setQueryData(key, [event]);
  client.setQueryData(['event', EVENT], event);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(
    () => ({
      signup: useSignupMutation(EVENT),
      event: useEventActionMutation(EVENT),
      signups: useSignupActionMutations(EVENT),
    }),
    { wrapper },
  );
  const listsInvalid = () =>
    LIST_KEYS.every((key) => client.getQueryState(key)?.isInvalidated);
  return { hook, listsInvalid };
}

describe('event mutations refresh every events list', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const name of [
      'openSignups',
      'startRollCall',
      'startTournament',
      'reopenSignups',
      'cancelEvent',
      'restartTournament',
      'completeEvent',
      'getEvent',
    ] as const)
      api[name].mockResolvedValue(event);
    api.deleteEvent.mockResolvedValue(undefined);
    api.signupForEvent.mockResolvedValue(signup);
    api.approveSignup.mockResolvedValue(signup);
    api.confirmSignup.mockResolvedValue(signup);
    api.cancelSignup.mockResolvedValue(signup);
    api.getEventSignups.mockResolvedValue([signup]);
  });

  it.each([
    'openSignups',
    'startRollCall',
    'startTournament',
    'reopenSignups',
    'cancelEvent',
    'deleteEvent',
    'restartTournament',
    'completeEvent',
  ] as const)('%s', async (name) => {
    const { hook, listsInvalid } = setup();
    expect(listsInvalid()).toBe(false);
    await act(async () => {
      await hook.result.current.event[name].mutateAsync();
    });
    expect(listsInvalid()).toBe(true);
  });

  it('self signup', async () => {
    const { hook, listsInvalid } = setup();
    await act(() => hook.result.current.signup.mutateAsync({ intent: 'rsvp' }));
    expect(listsInvalid()).toBe(true);
  });

  it.each(['confirm', 'cancel'] as const)(
    'staff signup action %s',
    async (name) => {
      const { hook, listsInvalid } = setup();
      await act(() => hook.result.current.signups[name].mutateAsync(3));
      expect(listsInvalid()).toBe(true);
    },
  );

  it('staff approve', async () => {
    const { hook, listsInvalid } = setup();
    await act(() =>
      hook.result.current.signups.approve.mutateAsync({ id: 3, mmr: 3000 }),
    );
    expect(listsInvalid()).toBe(true);
  });

  it('a failed signup action still refreshes the lists once it settles', async () => {
    api.confirmSignup.mockRejectedValueOnce(new Error('nope'));
    const { hook, listsInvalid } = setup();
    await act(async () => {
      await hook.result.current.signups.confirm.mutateAsync(3).catch(() => {});
    });
    expect(listsInvalid()).toBe(true);
  });
});
