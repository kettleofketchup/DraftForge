// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
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
import { baseEvent } from '~/components/events/__tests__/readyCheckModalFixtures';
import type {
  EventSignupType,
  StaffReasonPolicy,
} from '~/components/events/schemas';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/index';
import { useUserStore } from '~/store/userStore';

const h = vi.hoisted(() => ({
  policy: 'optional' as StaffReasonPolicy,
  manage: true,
  status: 'rsvp',
  canVoid: true,
  actions: Object.fromEntries(
    [
      'approve',
      'reject',
      'demote',
      'confirm',
      'unconfirm',
      'reinstate',
      'voidWithdrawal',
      'cancel',
      'adminAdd',
    ].map((name) => [
      name,
      { mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false },
    ]),
  ),
  toastError: vi.fn(),
  added: vi.fn(),
  addError: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { error: h.toastError, success: vi.fn() } }));
vi.mock('~/hooks/useEvent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/hooks/useEvent')>()),
  useEvent: () => ({
    data: {
      ...baseEvent,
      state: 'signups_open',
      user_can_manage: h.manage,
      staff_reason_policy: h.policy,
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
        status: h.status,
        can_void_withdrawal: h.canVoid,
        holds_seat: true,
        org_user_mmr: null,
        suggested_mmr: 3200,
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
  useSignupActionMutations: () => h.actions,
  useSignupMutation: () => ({ mutate: vi.fn(), isPending: false }),
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
vi.mock('~/components/events/MySignupActions', () => ({
  MySignupActions: () => null,
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
vi.mock('~/components/user/AddUserModal', () => ({
  AddUserModal: ({
    onAdd,
  }: {
    onAdd: (p: { user_id: number }) => Promise<unknown>;
  }) => (
    <div>
      {[5, 6].map((id) => (
        <button
          key={id}
          data-testid={`mock-add-${id}`}
          onClick={() => void onAdd({ user_id: id }).then(h.added, h.addError)}
        >
          add {id}
        </button>
      ))}
    </div>
  ),
}));

import EventPage from '../event';

function renderPage() {
  const tab =
    h.status === 'waitlisted'
      ? 'waitlist'
      : ['cancelled', 'rejected', 'dropped'].includes(h.status)
        ? 'removed'
        : 'signups';
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/events/${baseEvent.id}/${tab}`]}>
          <Routes>
            <Route path="events/:eventId/:tab?" element={<EventPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}
function rowButton(label: string) {
  return within(screen.getByTestId('event-signup-row-101')).getByRole(
    'button',
    { name: label },
  );
}
async function sendReason(reason = 'correction') {
  fireEvent.change(screen.getByTestId('staff-reason-input'), {
    target: { value: reason },
  });
  await waitFor(() =>
    expect(screen.getByTestId('staff-reason-confirm')).toBeEnabled(),
  );
  fireEvent.click(screen.getByTestId('staff-reason-confirm'));
}
async function openRecap() {
  fireEvent.click(screen.getByTestId('approve-signup-101'));
  await act(async () => {
    fireEvent.click(screen.getByTestId('mmr-modal-approve'));
  });
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
const overCapacity = () =>
  axiosError(409, {
    code: 'override_required',
    blocked: false,
    violations: [
      {
        code: 'over_capacity',
        rule: 'capacity',
        category: 'seating',
        message:
          'Event is at capacity; restoring seats this member over capacity.',
        blocking: false,
        params: { capacity: 10, seated: 10 },
      },
    ],
  });
async function confirmOverride(reason: string) {
  const dialog = await screen.findByTestId('override-warning-dialog');
  fireEvent.change(within(dialog).getByRole('textbox'), {
    target: { value: reason },
  });
  await act(async () => {
    fireEvent.click(within(dialog).getByRole('button', { name: /override/i }));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  for (const action of Object.values(h.actions))
    action.mutateAsync.mockReset().mockResolvedValue({ user_data: null });
  h.policy = 'optional';
  h.manage = true;
  h.status = 'rsvp';
  h.canVoid = true;
  useUserStore.setState({
    currentUser: { pk: 1, username: 'viewer' } as UserType,
  } as never);
});
afterEach(cleanup);

describe('event signup staff reasons', () => {
  it.each([
    ['rsvp', 'Waitlist', 'demote'],
    ['approved', 'Confirm', 'confirm'],
    ['confirmed', 'Unconfirm', 'unconfirm'],
    ['cancelled', 'Restore', 'reinstate'],
  ])('optional %s %s fires without a prompt', async (status, label, action) => {
    h.status = status;
    renderPage();
    fireEvent.click(rowButton(label));
    await waitFor(() =>
      expect(h.actions[action].mutateAsync).toHaveBeenCalledWith({ id: 101 }),
    );
    expect(screen.queryByTestId('staff-reason-dialog')).toBeNull();
  });

  it.each([
    ['approved', 'Confirm', 'confirm'],
    ['confirmed', 'Unconfirm', 'unconfirm'],
    ['cancelled', 'Restore', 'reinstate'],
  ])('all_staff_changes gates %s %s', async (status, label, action) => {
    h.policy = 'all_staff_changes';
    h.status = status;
    renderPage();
    fireEvent.click(rowButton(label));
    expect(h.actions[action].mutateAsync).not.toHaveBeenCalled();
    await sendReason();
    await waitFor(() =>
      expect(h.actions[action].mutateAsync).toHaveBeenCalledWith({
        id: 101,
        reason: 'correction',
      }),
    );
  });

  it('exempts staff changing their own signup under a strict policy', async () => {
    h.policy = 'all_staff_changes';
    useUserStore.setState({
      currentUser: { pk: 21, username: 'player' } as UserType,
    } as never);
    renderPage();
    fireEvent.click(rowButton('Waitlist'));
    await waitFor(() =>
      expect(h.actions.demote.mutateAsync).toHaveBeenCalledWith({ id: 101 }),
    );
    expect(screen.queryByTestId('staff-reason-dialog')).toBeNull();
  });

  it('requires a placement reason for Waitlist', async () => {
    h.policy = 'placements';
    renderPage();
    fireEvent.click(rowButton('Waitlist'));
    expect(screen.getByTestId('staff-reason-dialog')).toBeTruthy();
    expect(h.actions.demote.mutateAsync).not.toHaveBeenCalled();
    await sendReason();
    await waitFor(() =>
      expect(h.actions.demote.mutateAsync).toHaveBeenCalledWith({
        id: 101,
        reason: 'correction',
      }),
    );
  });

  it.each(['placements', 'optional'] as const)(
    'waitlist approval recap follows %s policy',
    async (policy) => {
      h.policy = policy;
      h.status = 'waitlisted';
      renderPage();
      await openRecap();
      expect(screen.getByTestId('staff-reason-input')).toHaveAccessibleName(
        policy === 'placements'
          ? 'Reason (recorded in signup history)'
          : 'Reason (optional)',
      );
      if (policy === 'placements') {
        expect(screen.getByTestId('mmr-confirm-approve')).toBeDisabled();
      } else {
        await waitFor(() =>
          expect(screen.getByTestId('mmr-confirm-approve')).toBeEnabled(),
        );
      }
      fireEvent.change(screen.getByTestId('staff-reason-input'), {
        target: { value: 'seat correction' },
      });
      await waitFor(() =>
        expect(screen.getByTestId('mmr-confirm-approve')).toBeEnabled(),
      );
      fireEvent.click(screen.getByTestId('mmr-confirm-approve'));
      await waitFor(() =>
        expect(h.actions.approve.mutateAsync).toHaveBeenCalledWith({
          id: 101,
          mmr: 3200,
          reason: 'seat correction',
        }),
      );
    },
  );

  it('records the inline Remove reason', async () => {
    renderPage();
    fireEvent.click(rowButton('Remove'));
    expect(screen.getByTestId('staff-reason-input')).toHaveAccessibleName(
      'Reason (optional)',
    );
    await sendReason('withdrawn by staff');
    await waitFor(() =>
      expect(h.actions.cancel.mutateAsync).toHaveBeenCalledWith({
        id: 101,
        reason: 'withdrawn by staff',
      }),
    );
  });

  it.each(['all_staff_changes', 'optional'] as const)(
    'MMR reject follows %s policy',
    async (policy) => {
      h.policy = policy;
      renderPage();
      fireEvent.click(screen.getByTestId('approve-signup-101'));
      fireEvent.click(screen.getByTestId('mmr-modal-reject'));
      if (policy === 'all_staff_changes') {
        expect(screen.getByTestId('staff-reason-dialog')).toBeTruthy();
        await sendReason();
      }
      await waitFor(() =>
        expect(h.actions.reject.mutateAsync).toHaveBeenCalledWith(
          policy === 'optional'
            ? { id: 101 }
            : { id: 101, reason: 'correction' },
        ),
      );
    },
  );

  it('prompts separately for each staff add', async () => {
    h.policy = 'placements';
    renderPage();
    fireEvent.click(screen.getByTestId('admin-add-signup-btn'));
    for (const id of [5, 6]) {
      fireEvent.click(screen.getByTestId(`mock-add-${id}`));
      await sendReason(`reason ${id}`);
      await waitFor(() =>
        expect(h.actions.adminAdd.mutateAsync).toHaveBeenCalledWith({
          userId: id,
          reason: `reason ${id}`,
        }),
      );
      await waitFor(() =>
        expect(screen.queryByTestId('staff-reason-dialog')).toBeNull(),
      );
    }
    expect(h.actions.adminAdd.mutateAsync).toHaveBeenCalledTimes(2);
  });

  it('cancelling the required staff-add reason refuses the add', async () => {
    h.policy = 'placements';
    renderPage();
    fireEvent.click(screen.getByTestId('admin-add-signup-btn'));
    fireEvent.click(screen.getByTestId('mock-add-5'));
    fireEvent.click(screen.getByTestId('staff-reason-cancel'));
    await waitFor(() =>
      expect(h.addError).toHaveBeenCalledWith(
        new Error('Not added: a reason is required.'),
      ),
    );
    expect(h.actions.adminAdd.mutateAsync).not.toHaveBeenCalled();
  });

  it('optional staff add has no extra prompt', async () => {
    renderPage();
    fireEvent.click(screen.getByTestId('admin-add-signup-btn'));
    fireEvent.click(screen.getByTestId('mock-add-5'));
    await waitFor(() =>
      expect(h.actions.adminAdd.mutateAsync).toHaveBeenCalledWith({
        userId: 5,
      }),
    );
    expect(screen.queryByTestId('staff-reason-dialog')).toBeNull();
  });

  it('requires a nonblank reason and retries once when admin-add sees a stale policy', async () => {
    h.policy = 'optional';
    h.actions.adminAdd.mutateAsync.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 400, data: { error: 'reason_required' } },
    });
    renderPage();
    fireEvent.click(screen.getByTestId('admin-add-signup-btn'));
    fireEvent.click(screen.getByTestId('mock-add-5'));
    await screen.findByTestId('staff-reason-dialog');
    expect(screen.getByLabelText('Reason (recorded in signup history)')).toBe(
      screen.getByTestId('staff-reason-input'),
    );
    expect(screen.getByTestId('staff-reason-confirm')).toBeDisabled();
    fireEvent.change(screen.getByTestId('staff-reason-input'), {
      target: { value: '   ' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('staff-reason-confirm')).toBeDisabled(),
    );
    expect(h.actions.adminAdd.mutateAsync).toHaveBeenCalledTimes(1);
    await sendReason('updated policy');
    await waitFor(() =>
      expect(h.actions.adminAdd.mutateAsync).toHaveBeenLastCalledWith({
        userId: 5,
        reason: 'updated policy',
      }),
    );
    expect(h.actions.adminAdd.mutateAsync).toHaveBeenCalledTimes(2);
  });

  it('does not retry admin-add again when the recovery request is refused', async () => {
    const error = {
      isAxiosError: true,
      response: { status: 400, data: { error: 'reason_required' } },
    };
    h.actions.adminAdd.mutateAsync.mockRejectedValue(error);
    renderPage();
    fireEvent.click(screen.getByTestId('admin-add-signup-btn'));
    fireEvent.click(screen.getByTestId('mock-add-5'));
    await screen.findByTestId('staff-reason-dialog');
    await sendReason('updated policy');
    await waitFor(() => expect(h.addError).toHaveBeenCalledWith(error));
    expect(h.actions.adminAdd.mutateAsync).toHaveBeenCalledTimes(2);
    expect(h.added).not.toHaveBeenCalled();
  });

  it('retains the Remove reason after a refused request', async () => {
    h.actions.cancel.mutateAsync.mockRejectedValueOnce({
      response: { data: { error: 'Cannot remove this signup.' } },
    });
    renderPage();
    fireEvent.click(rowButton('Remove'));
    await sendReason('retain this');
    await waitFor(() =>
      expect(h.toastError).toHaveBeenCalledWith('Cannot remove this signup.'),
    );
    expect(screen.getByTestId('staff-reason-input')).toHaveValue('retain this');
    expect(screen.getByTestId('staff-reason-dialog')).toBeTruthy();
  });

  it('shows server validation errors instead of silently dropping them', async () => {
    h.actions.demote.mutateAsync.mockRejectedValueOnce({
      response: { data: { error: 'Cannot demote this signup.' } },
    });
    renderPage();
    fireEvent.click(rowButton('Waitlist'));
    await waitFor(() =>
      expect(h.toastError).toHaveBeenCalledWith('Cannot demote this signup.'),
    );
  });
});

describe('event page void withdrawal', () => {
  it.each(['cancelled', 'rejected'])(
    'Void withdrawal shows for staff on %s rows',
    (status) => {
      h.status = status;
      renderPage();
      const row = screen.getByTestId('event-signup-row-101');
      expect(
        within(row).getByTestId('event-void-withdrawal-btn'),
      ).toHaveAccessibleName('Void withdrawal');
    },
  );

  it.each(['dropped', 'approved', 'waitlisted'])(
    'Void withdrawal is hidden on %s rows',
    (status) => {
      h.status = status;
      renderPage();
      expect(screen.queryByTestId('event-void-withdrawal-btn')).toBeNull();
    },
  );

  it('Void withdrawal is hidden when the server would refuse the void', () => {
    h.status = 'cancelled';
    h.canVoid = false;
    renderPage();
    expect(screen.queryByTestId('event-void-withdrawal-btn')).toBeNull();
    expect(rowButton('Restore')).toBeTruthy();
  });

  it('Void withdrawal is hidden from members', () => {
    h.status = 'cancelled';
    h.manage = false;
    renderPage();
    expect(screen.queryByTestId('event-void-withdrawal-btn')).toBeNull();
  });

  it('optional Void fires without a prompt', async () => {
    h.status = 'cancelled';
    renderPage();
    fireEvent.click(screen.getByTestId('event-void-withdrawal-btn'));
    await waitFor(() =>
      expect(h.actions.voidWithdrawal.mutateAsync).toHaveBeenCalledWith({
        id: 101,
      }),
    );
    expect(screen.queryByTestId('staff-reason-dialog')).toBeNull();
  });

  it('Void under placements policy asks for a reason then posts it', async () => {
    h.policy = 'placements';
    h.status = 'cancelled';
    renderPage();
    fireEvent.click(screen.getByTestId('event-void-withdrawal-btn'));
    expect(screen.getByTestId('staff-reason-dialog')).toBeTruthy();
    expect(h.actions.voidWithdrawal.mutateAsync).not.toHaveBeenCalled();
    await sendReason('mistaken');
    await waitFor(() =>
      expect(h.actions.voidWithdrawal.mutateAsync).toHaveBeenCalledWith({
        id: 101,
        reason: 'mistaken',
      }),
    );
  });

  it('409 on Void opens the override dialog and confirm retries with acknowledged_codes and reason', async () => {
    h.policy = 'placements';
    h.status = 'cancelled';
    h.actions.voidWithdrawal.mutateAsync.mockRejectedValueOnce(overCapacity());
    renderPage();
    fireEvent.click(screen.getByTestId('event-void-withdrawal-btn'));
    await sendReason('mistaken');
    const dialog = await screen.findByTestId('override-warning-dialog');
    expect(
      within(dialog).getByText(
        'Event is at capacity; restoring seats this member over capacity.',
      ),
    ).toBeTruthy();
    expect(within(dialog).getByRole('textbox')).toHaveValue('mistaken');
    await confirmOverride('mistaken');
    await waitFor(() =>
      expect(h.actions.voidWithdrawal.mutateAsync).toHaveBeenLastCalledWith({
        id: 101,
        reason: 'mistaken',
        acknowledged_codes: ['over_capacity'],
      }),
    );
    expect(h.actions.voidWithdrawal.mutateAsync).toHaveBeenCalledTimes(2);
    await waitFor(() =>
      expect(screen.queryByTestId('override-warning-dialog')).toBeNull(),
    );
    expect(h.toastError).not.toHaveBeenCalled();
  });

  it('server reason_required after Void opens the recovery prompt', async () => {
    h.status = 'cancelled';
    h.actions.voidWithdrawal.mutateAsync.mockRejectedValueOnce(
      axiosError(400, { error: 'reason_required' }),
    );
    renderPage();
    fireEvent.click(screen.getByTestId('event-void-withdrawal-btn'));
    await screen.findByTestId('staff-reason-dialog');
    expect(h.toastError).not.toHaveBeenCalled();
    await sendReason('policy changed');
    await waitFor(() =>
      expect(h.actions.voidWithdrawal.mutateAsync).toHaveBeenLastCalledWith({
        id: 101,
        reason: 'policy changed',
      }),
    );
  });

  it('non-override error toasts exactly once', async () => {
    h.status = 'cancelled';
    h.actions.voidWithdrawal.mutateAsync.mockRejectedValueOnce(
      axiosError(400, {
        error: 'This withdrawal has no recorded place to restore.',
      }),
    );
    renderPage();
    fireEvent.click(screen.getByTestId('event-void-withdrawal-btn'));
    await waitFor(() =>
      expect(h.toastError).toHaveBeenCalledWith(
        'This withdrawal has no recorded place to restore.',
      ),
    );
    expect(h.toastError).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('override-warning-dialog')).toBeNull();
  });

  it('Restore refused at capacity toasts once and never asks to override', async () => {
    const refusal =
      'Event is at capacity; use Void withdrawal to restore this member over capacity.';
    h.status = 'cancelled';
    h.actions.reinstate.mutateAsync.mockRejectedValueOnce(
      axiosError(400, { error: refusal }),
    );
    renderPage();
    fireEvent.click(rowButton('Restore'));
    await waitFor(() =>
      expect(h.toastError).toHaveBeenCalledExactlyOnceWith(refusal),
    );
    expect(h.actions.reinstate.mutateAsync).toHaveBeenCalledExactlyOnceWith({
      id: 101,
    });
    expect(screen.queryByTestId('override-warning-dialog')).toBeNull();
    expect(h.actions.voidWithdrawal.mutateAsync).not.toHaveBeenCalled();
  });

  it('an error after confirming the override toasts once', async () => {
    h.status = 'cancelled';
    h.actions.voidWithdrawal.mutateAsync
      .mockRejectedValueOnce(overCapacity())
      .mockRejectedValueOnce(
        axiosError(400, {
          error: 'Only withdrawn or rejected signups can be voided.',
        }),
      );
    renderPage();
    fireEvent.click(screen.getByTestId('event-void-withdrawal-btn'));
    await confirmOverride('mistaken');
    await waitFor(() =>
      expect(h.toastError).toHaveBeenCalledWith(
        'Only withdrawn or rejected signups can be voided.',
      ),
    );
    expect(h.toastError).toHaveBeenCalledTimes(1);
  });
});
