// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SpotTransferResponse } from '~/components/api/eventsAPI';
import { baseEvent } from '~/components/events/__tests__/readyCheckModalFixtures';
import type { EventSignupType } from '~/components/events/schemas';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/index';
import { useUserStore } from '~/store/userStore';

const h = vi.hoisted(() => ({
  manage: false,
  allowTransfer: true,
  state: 'signups_open',
  transferSpot: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));
vi.mock('sonner', () => ({
  toast: { error: h.toastError, success: h.toastSuccess },
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  transferSpot: h.transferSpot,
}));
vi.mock('~/hooks/useEvent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/hooks/useEvent')>()),
  useEvent: () => ({
    data: {
      ...baseEvent,
      state: h.state,
      allow_spot_transfer: h.allowTransfer,
      user_can_manage: h.manage,
      staff_reason_policy: 'optional',
    },
    isLoading: false,
    error: null,
  }),
  useEventSignups: () => ({
    data: [
      {
        id: 101,
        event: baseEvent.id,
        user: 21,
        username: 'player',
        user_avatar: null,
        user_data: null,
        dota_profile: null,
        status: 'approved',
        holds_seat: true,
        line_rank: 3,
        org_user_mmr: null,
      } as EventSignupType,
    ],
  }),
  useEventSignupUsers: () => undefined,
  useEventActionMutation: () =>
    new Proxy(
      {},
      {
        get: () => ({
          mutate: vi.fn(),
          mutateAsync: vi.fn(),
          isPending: false,
        }),
      },
    ),
  useSignupMutation: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('~/hooks/useUserSearch', () => ({
  useUserSearch: (query: string) => ({
    term: query,
    results: [
      {
        pk: 31,
        username: 'Sam',
        nickname: null,
        avatarUrl: null,
        membership: 'org',
      },
    ],
    status: 'done',
    error: null,
  }),
}));
vi.mock('~/components/organization', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/organization')>()),
  useOrganization: () => ({ organization: null, refetch: vi.fn() }),
}));
vi.mock('~/features/org-features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/features/org-features')>()),
  useOrgFeatureAccess: () => ({ settled: false }),
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
  useMemberAccess: () => ({ canView: false, settled: false }),
}));
vi.mock('~/hooks/usePageNav', () => ({ usePageNav: () => undefined }));
vi.mock('~/hooks/useResolvedUsers', () => ({
  useResolvedUsers: (pks: number[]) =>
    pks.map((pk) => ({ pk, username: `user_${pk}` })),
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
vi.mock('~/components/lobby/EventLobbyPassword', () => ({
  EventLobbyPassword: () => null,
}));
vi.mock('~/components/user', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/user')>()),
  UserEventStrip: ({
    actionSlot,
    ...rest
  }: {
    actionSlot?: ReactNode;
    'data-testid'?: string;
  }) => <div data-testid={rest['data-testid']}>{actionSlot}</div>,
}));

import EventPage from '../event';

function renderPage(viewerPk: number) {
  useUserStore.setState({
    currentUser: { pk: viewerPk, username: 'viewer' } as UserType,
  } as never);
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/events/${baseEvent.id}/signups`]}>
          <Routes>
            <Route path="events/:eventId/:tab?" element={<EventPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function axiosError(status: number, data: unknown): AxiosError {
  return new AxiosError('fail', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    statusText: '',
    data,
    headers: {},
    config: { headers: new AxiosHeaders() },
  });
}

const transferred = {
  mode: 'transfer',
  correlation_id: 'xfer:abc',
  giver: {
    id: 101,
    event: baseEvent.id,
    user: 21,
    username: 'player',
    status: 'cancelled',
  },
  recipient: {
    id: 102,
    event: baseEvent.id,
    user: 31,
    username: 'Sam',
    status: 'approved',
    line_rank: 3,
  },
} as unknown as SpotTransferResponse;

beforeEach(() => {
  vi.clearAllMocks();
  h.manage = false;
  h.allowTransfer = true;
  h.state = 'signups_open';
});
afterEach(cleanup);

describe('event page member spot transfer', () => {
  it.each(['signups_open', 'roll_call'])(
    'shows Give my place in %s with the setting on',
    (state) => {
      h.state = state;
      renderPage(21);
      expect(screen.getByTestId('event-transfer-spot-btn')).toBeTruthy();
    },
  );

  it.each(['draft', 'in_progress'])('hides Give my place in %s', (state) => {
    h.state = state;
    renderPage(21);
    expect(screen.queryByTestId('event-transfer-spot-btn')).toBeNull();
  });

  it('hides Give my place with the setting off', () => {
    h.allowTransfer = false;
    renderPage(21);
    expect(screen.queryByTestId('event-cancel-rsvp-btn')).toBeTruthy();
    expect(screen.queryByTestId('event-transfer-spot-btn')).toBeNull();
  });

  it('opens the dialog in member mode and transfers', async () => {
    h.transferSpot.mockResolvedValueOnce(transferred);
    renderPage(21);
    fireEvent.click(screen.getByTestId('event-transfer-spot-btn'));
    const dialog = await screen.findByTestId('transfer-spot-dialog');
    expect(within(dialog).getByText('Give your place')).toBeTruthy();
    fireEvent.click(screen.getByTestId('transfer-spot-option-31'));
    fireEvent.click(screen.getByTestId('transfer-spot-confirm'));
    await waitFor(() =>
      expect(h.toastSuccess).toHaveBeenCalledWith('You gave your place to Sam'),
    );
    expect(h.transferSpot).toHaveBeenCalledWith(101, {
      recipient_user_id: 31,
    });
    await waitFor(() =>
      expect(screen.queryByTestId('transfer-spot-dialog')).toBeNull(),
    );
  });
});

describe('event page staff spot transfer', () => {
  it('toasts after an override retry with the dialog closed', async () => {
    h.manage = true;
    h.transferSpot
      .mockRejectedValueOnce(
        axiosError(409, {
          code: 'override_required',
          blocked: false,
          violations: [
            {
              code: 'not_org_member',
              rule: 'membership',
              category: 'eligibility',
              message: 'Not a member of this organization',
              blocking: false,
              params: {},
            },
          ],
        }),
      )
      .mockResolvedValueOnce(transferred);
    renderPage(1);
    fireEvent.click(screen.getByTestId('signup-transfer-btn'));
    await screen.findByTestId('transfer-spot-dialog');
    fireEvent.click(screen.getByTestId('transfer-spot-option-31'));
    fireEvent.click(screen.getByTestId('transfer-spot-confirm'));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));
    const override = await screen.findByTestId('override-warning-dialog');
    await waitFor(() =>
      expect(screen.queryByTestId('transfer-spot-dialog')).toBeNull(),
    );
    expect(h.toastSuccess).not.toHaveBeenCalled();
    fireEvent.change(within(override).getByTestId('override-reason'), {
      target: { value: 'Guest from partner organization' },
    });
    fireEvent.click(within(override).getByTestId('override-confirm'));
    await waitFor(() =>
      expect(h.toastSuccess).toHaveBeenCalledWith("Gave player's place to Sam"),
    );
    expect(h.transferSpot).toHaveBeenLastCalledWith(101, {
      recipient_user_id: 31,
      reason: 'Guest from partner organization',
      acknowledged_codes: ['not_org_member'],
    });
    expect(screen.queryByTestId('transfer-spot-dialog')).toBeNull();
  });
});
