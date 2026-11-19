// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventSignupType, EventType } from '~/components/events/schemas';

const api = vi.hoisted(() => ({
  signupForEvent: vi.fn(),
  cancelEvent: vi.fn(),
  reopenSignups: vi.fn(),
  restartTournament: vi.fn(),
  completeEvent: vi.fn(),
  setEventStaff: vi.fn(),
  confirmSignup: vi.fn(),
  cancelSignup: vi.fn(),
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
} from '../useEvent';

const EVENT_ID = 9;
const CONDUCT_KEY = ['org-conduct', 5, 1, 'forecast', EVENT_ID];
const event = { id: EVENT_ID, organization: 5 } as unknown as EventType;
const signup = { id: 3, status: 'confirmed', user: 3 } as EventSignupType;

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(CONDUCT_KEY, { members: {} });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(
    () => ({
      signup: useSignupMutation(EVENT_ID),
      event: useEventActionMutation(EVENT_ID),
      signups: useSignupActionMutations(EVENT_ID),
    }),
    { wrapper },
  );
  const conductInvalidated = () =>
    client.getQueryState(CONDUCT_KEY)?.isInvalidated === true;
  return { hook, conductInvalidated };
}

describe('event mutations invalidate conduct queries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.signupForEvent.mockResolvedValue(signup);
    api.cancelEvent.mockResolvedValue(event);
    api.reopenSignups.mockResolvedValue(event);
    api.restartTournament.mockResolvedValue(event);
    api.completeEvent.mockResolvedValue(event);
    api.setEventStaff.mockResolvedValue(event);
    api.confirmSignup.mockResolvedValue(signup);
    api.cancelSignup.mockResolvedValue(signup);
    api.getEventSignups.mockResolvedValue([signup]);
    api.getEvent.mockResolvedValue(event);
  });

  it('after a signup', async () => {
    const { hook, conductInvalidated } = setup();
    await act(() => hook.result.current.signup.mutateAsync({ intent: 'rsvp' }));
    expect(conductInvalidated()).toBe(true);
  });

  it.each([
    'cancelEvent',
    'reopenSignups',
    'restartTournament',
    'completeEvent',
  ] as const)('after %s', async (name) => {
    const { hook, conductInvalidated } = setup();
    await act(() => hook.result.current.event[name].mutateAsync());
    expect(conductInvalidated()).toBe(true);
  });

  it('after setEventStaff', async () => {
    const { hook, conductInvalidated } = setup();
    await act(() =>
      hook.result.current.event.setEventStaff.mutateAsync({
        host_id: null,
        helper_ids: [],
      }),
    );
    expect(conductInvalidated()).toBe(true);
  });

  it.each(['confirm', 'cancel'] as const)(
    'after the %s signup action',
    async (name) => {
      const { hook, conductInvalidated } = setup();
      await act(() => hook.result.current.signups[name].mutateAsync(3));
      expect(conductInvalidated()).toBe(true);
    },
  );
});
