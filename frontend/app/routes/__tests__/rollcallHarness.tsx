import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { vi } from 'vitest';
import { baseEvent } from '~/components/events/__tests__/readyCheckModalFixtures';
import type { EventSignupType, EventType } from '~/components/events/schemas';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/index';
import { useUserStore } from '~/store/userStore';

const h = vi.hoisted(() => ({
  event: {} as EventType,
  signups: [] as EventSignupType[],
  actions: Object.fromEntries(
    ['approve', 'reject', 'confirm', 'cancel', 'reinstate'].map((name) => [
      name,
      { mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false },
    ]),
  ),
  start: { mutateAsync: vi.fn(), isPending: false },
}));
vi.mock('~/hooks/useEvent', () => ({
  useEvent: () => ({ data: h.event, isLoading: false }),
  useOptimisticEventSignups: () => ({
    data: h.signups,
    signups: h.signups,
    pendingIds: new Set(),
  }),
  useEventSignupUsers: () => undefined,
  useSignupActionMutations: () => h.actions,
  useEventActionMutation: () => ({ startTournament: h.start }),
}));
vi.mock('~/components/organization', () => ({
  useOrganization: () => ({ organization: null, refetch: vi.fn() }),
}));
vi.mock('~/features/org-features', () => ({
  useOrgFeatureAccess: () => ({ settled: false }),
  removeFeatureQueries: vi.fn(),
}));
vi.mock('~/features/conduct', () => ({
  ConductBadge: () => null,
  useEventConduct: () => ({ memberFor: () => undefined }),
}));
vi.mock('~/hooks/useMemberAccess', () => ({
  useMemberAccess: () => ({ settled: false }),
}));
vi.mock('~/hooks/useResolvedUsers', () => ({ useResolvedUsers: () => [] }));
vi.mock('~/hooks/useUserProfile', () => ({
  useUserDotaProfile: () => ({
    data: undefined,
    status: 'pending',
    refetch: vi.fn(),
  }),
}));
vi.mock('~/components/user', () => ({
  UserStrip: ({ actionSlot }: { actionSlot?: ReactNode }) => (
    <div>{actionSlot}</div>
  ),
}));

import RollCallPage from '../rollcall';

export { h };

export function signup(
  id = 101,
  status: EventSignupType['status'] = 'approved',
): EventSignupType {
  return {
    id,
    user: id + 100,
    username: `player_${id}`,
    status,
    event: baseEvent.id,
    suggested_mmr: 3200,
    org_user_mmr: null,
    user_data: null,
  } as EventSignupType;
}

export function renderRollCall({
  event = {},
  signups = [signup()],
  currentUser = { pk: 1, username: 'staff' } as UserType,
}: {
  event?: Partial<EventType>;
  signups?: EventSignupType[];
  currentUser?: UserType;
} = {}) {
  h.event = {
    ...baseEvent,
    state: 'roll_call',
    user_can_manage: true,
    ...event,
  };
  h.signups = signups;
  useUserStore.setState({ currentUser } as never);
  for (const action of Object.values(h.actions)) {
    action.mutateAsync.mockReset().mockResolvedValue({});
    action.mutate.mockReset().mockImplementation((variables, options) => {
      void action
        .mutateAsync(variables)
        .then(options?.onSuccess, options?.onError);
    });
  }
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const page = () => (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/events/${baseEvent.id}/rollcall`]}>
          <Routes>
            <Route path="events/:eventId/rollcall" element={<RollCallPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
  const view = render(page());
  return {
    ...view,
    rerenderSignups(nextSignups: EventSignupType[]) {
      h.signups = nextSignups;
      view.rerender(page());
    },
  };
}
