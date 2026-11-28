// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router';
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';

import { baseEvent } from '~/components/events/__tests__/readyCheckModalFixtures';
import type { EventSignupType, EventType } from '~/components/events/schemas';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/index';
import { useUserStore } from '~/store/userStore';
import { resetGameType } from '~/test-utils/gameType';

const h = vi.hoisted(() => ({
  event: null as unknown,
  signups: [] as unknown[],
  onStale: null as null | (() => void),
  pageNav: null as null | { value: string }[],
  pageNavActive: null as null | string,
  getEventSignupHistory: vi.fn(),
  adminAddSignup: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  getEventSignupHistory: h.getEventSignupHistory,
  adminAddSignup: h.adminAddSignup,
}));

vi.mock('~/hooks/useEvent', async (importOriginal) => {
  const actual = await importOriginal<typeof import('~/hooks/useEvent')>();
  const mutation = () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
  });
  const signupActions = {
    approve: mutation(),
    reject: mutation(),
    demote: mutation(),
    confirm: mutation(),
    unconfirm: mutation(),
    reinstate: mutation(),
    voidWithdrawal: mutation(),
    transfer: mutation(),
    cancel: mutation(),
  };
  return {
    ...actual,
    useEvent: () => ({ data: h.event, isLoading: false, error: null }),
    useEventSignups: () => ({ data: h.signups }),
    useEventSignupUsers: () => undefined,
    useEventActionMutation: () => new Proxy({}, { get: () => mutation() }),
    useSignupActionMutations: (eventId: number) => ({
      ...signupActions,
      adminAdd: actual.useSignupActionMutations(eventId).adminAdd,
    }),
    useSignupMutation: () => mutation(),
  };
});

vi.mock('~/components/organization', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/organization')>()),
  useOrganization: () => ({ organization: null, refetch: vi.fn() }),
}));

vi.mock('~/features/org-features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/features/org-features')>()),
  useOrgFeatureAccess: () => ({ settled: false }),
  removeFeatureQueries: vi.fn(),
  invalidateConductQueries: vi.fn(async () => undefined),
}));

vi.mock('~/features/conduct', () => ({
  ConductBadge: () => null,
  EventConductSection: () => null,
  useEventConduct: () => ({ memberFor: undefined }),
}));
vi.mock('~/features/leadership', () => ({
  EventLeadershipBanner: () => null,
  EventLeadershipSection: () => null,
}));
vi.mock('~/features/promotion', () => ({
  canPromoteEvent: () => false,
  PromoteEventButton: () => null,
}));

vi.mock('~/hooks/useMemberAccess', () => ({
  useMemberAccess: (_source: unknown, onStale: () => void) => {
    h.onStale = onStale;
    return { canView: false, settled: false };
  },
}));
vi.mock('~/hooks/usePageNav', () => ({
  usePageNav: (options: { value: string }[] | null, active: string) => {
    h.pageNav = options;
    h.pageNavActive = active;
  },
}));
vi.mock('~/hooks/useResolvedUsers', () => ({
  useResolvedUsers: (pks: number[]) =>
    pks.map((pk) => ({ pk, username: `user_${pk}`, nickname: `Nick${pk}` })),
}));
vi.mock('~/hooks/useUserProfile', () => ({
  useUserDotaProfile: () => ({
    data: undefined,
    status: 'pending',
    refetch: vi.fn(),
  }),
}));

vi.mock('~/components/events/EventAdminActions', () => ({
  EventAdminActions: () => null,
}));
vi.mock('~/components/events/OpsNoticesCard', () => ({
  OpsNoticesCard: () => null,
}));
vi.mock('~/components/events/EventStaffCard', () => ({
  EventStaffSection: () => null,
}));
vi.mock('~/components/events/SubscriberList', () => ({
  SubscriberList: () => null,
}));
vi.mock('~/components/events/DiscordLogSection', () => ({
  DiscordLogSection: () => null,
}));
vi.mock('~/components/events/EditEventModal', () => ({
  EditEventModal: () => null,
}));
vi.mock('~/components/events/EventSignupModal', () => ({
  EventSignupModal: () => null,
}));
vi.mock('~/components/events/MmrApprovalModal', () => ({
  MmrApprovalModal: () => null,
}));
vi.mock('~/components/events/MySignupActions', () => ({
  MySignupActions: () => null,
}));
vi.mock('~/components/lobby/EventLobbyPassword', () => ({
  EventLobbyPassword: () => null,
}));
vi.mock('~/components/user/AddUserModal', () => ({
  AddUserModal: ({
    onAdd,
  }: {
    onAdd: (p: { user_id: number }) => Promise<unknown>;
  }) => (
    <button
      data-testid="mock-add-user"
      onClick={() => void onAdd({ user_id: 5 })}
    >
      add
    </button>
  ),
}));
vi.mock('~/components/user', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/user')>()),
  UserEventStrip: ({
    contextSlot,
    actionSlot,
    ...rest
  }: {
    contextSlot?: ReactNode;
    actionSlot?: ReactNode;
    'data-testid'?: string;
  }) => (
    <div data-testid={rest['data-testid']}>
      {contextSlot}
      {actionSlot}
    </div>
  ),
}));

import EventPage from '../event';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

const EVENT_ID = baseEvent.id;

function makeEvent(overrides: Partial<EventType> = {}): EventType {
  return {
    ...baseEvent,
    state: 'signups_open',
    user_can_manage: true,
    ...overrides,
  };
}

function signup(id: number, user: number): EventSignupType {
  return {
    id,
    event: EVENT_ID,
    user,
    username: `user_${user}`,
    user_avatar: null,
    user_data: null,
    dota_profile: null,
    status: 'approved',
    holds_seat: true,
    waitlist_position: null,
    org_user_mmr: null,
  } as unknown as EventSignupType;
}

function renderPage(tab = 'signups') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/events/${EVENT_ID}/${tab}`]}>
          <Routes>
            <Route path="events/:eventId/:tab?" element={<EventPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  vi.clearAllMocks();
  h.event = makeEvent();
  h.signups = [signup(101, 21), signup(102, 22)];
  h.onStale = null;
  h.pageNav = null;
  h.pageNavActive = null;
  h.getEventSignupHistory.mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    results: [],
  });
  h.adminAddSignup.mockResolvedValue({ user_data: null });
  useUserStore.setState({
    currentUser: { pk: 1, username: 'viewer' } as UserType,
  } as never);
});

afterEach(() => {
  cleanup();
  resetGameType();
});

describe('EventPage in line since', () => {
  it('shows when a waitlisted signup joined the line', () => {
    h.signups = [
      {
        ...signup(103, 23),
        status: 'waitlisted',
        holds_seat: false,
        waitlist_position: 1,
        signed_up_at: '2026-11-25T19:42:00Z',
      },
    ];
    renderPage('waitlist');

    const line = screen.getByTestId('signup-in-line-since-103');
    expect(line).toHaveTextContent(/in line since/i);
    expect(line.querySelector('time')).toHaveAttribute(
      'dateTime',
      '2026-11-25T19:42:00Z',
    );
  });
});
