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
import { useState } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SearchUserResult } from '~/components/api/api';
import type { SpotTransferResponse } from '~/components/api/eventsAPI';
import type { OverrideRequired } from '~/components/api/overridesAPI';
import { TooltipProvider } from '~/components/ui/tooltip';
import { useSignupActionMutations } from '~/hooks/useEvent';

import { OverrideWarningDialog } from '../OverrideWarningDialog';
import type { EventSignupType, EventType, StaffReasonPolicy } from '../schemas';
import { StaffReasonDialog } from '../StaffReasonDialog';
import { TransferSpotDialog } from '../TransferSpotDialog';
import { useSignupOverride } from '../useSignupOverride';
import { useStaffAction } from '../useStaffAction';

const h = vi.hoisted(() => ({
  transferSpot: vi.fn(),
  search: vi.fn(),
  results: [] as unknown[],
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: h.toastSuccess, error: h.toastError },
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  transferSpot: h.transferSpot,
}));
vi.mock('~/hooks/useUserSearch', () => ({
  useUserSearch: (query: string, opts: unknown) => {
    h.search(query, opts);
    return { term: query, results: h.results, status: 'done', error: null };
  },
}));

const EVENT_ID = 42;
const ORG_ID = 7;

function user(pk: number, username: string, membership?: string) {
  return {
    pk,
    username,
    nickname: null,
    avatarUrl: null,
    membership: membership ?? null,
  } as unknown as SearchUserResult;
}

function row(
  id: number,
  userPk: number,
  status: string,
  lineRank: number | null,
): EventSignupType {
  return {
    id,
    event: EVENT_ID,
    user: userPk,
    username: `user${userPk}`,
    user_avatar: null,
    user_data: null,
    status,
    line_rank: lineRank,
    commitment: 'main',
  } as unknown as EventSignupType;
}

const GIVER = row(101, 21, 'approved', 3);
const SAM = user(31, 'Sam', 'org');
const LEE = user(41, 'Lee', 'other_org');
const SAM_ROW = row(102, 31, 'waitlisted', 7);
const LEE_ROW = row(103, 41, 'approved', 1);

const event = (autoApprove = true) =>
  ({
    id: EVENT_ID,
    auto_approve: autoApprove,
    allow_spot_transfer: true,
    state: 'signups_open',
    organization: ORG_ID,
  }) as unknown as EventType;

function axiosError(status: number, data: unknown): AxiosError {
  return new AxiosError('fail', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    statusText: '',
    data,
    headers: {},
    config: { headers: new AxiosHeaders() },
  });
}

function response(mode: 'transfer' | 'swap'): SpotTransferResponse {
  return {
    mode,
    correlation_id: 'xfer:abc',
    giver: { ...GIVER, status: mode === 'swap' ? 'waitlisted' : 'cancelled' },
    recipient: { ...row(102, 31, 'approved', 3), username: 'Sam' },
  } as SpotTransferResponse;
}

const overrideBody: OverrideRequired = {
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
};

interface HarnessProps {
  mode: 'member' | 'staff';
  signups?: EventSignupType[];
  autoApprove?: boolean;
  policy?: StaffReasonPolicy;
  onTransferred?: (r: SpotTransferResponse) => void;
}

function Harness({
  mode,
  signups = [GIVER],
  autoApprove = true,
  policy = 'optional',
  onTransferred,
}: HarnessProps) {
  const [open, setOpen] = useState(true);
  const actions = useSignupActionMutations(EVENT_ID);
  const staffAction = useStaffAction({ policy, currentUserId: 1 });
  const signupOverride = useSignupOverride(actions);
  return (
    <>
      <span data-testid="harness-open">{String(open)}</span>
      <TransferSpotDialog
        open={open}
        onOpenChange={setOpen}
        signup={GIVER}
        event={event(autoApprove)}
        signups={signups}
        mode={mode}
        orgId={ORG_ID}
        transfer={actions.transfer}
        staffAction={mode === 'staff' ? staffAction : undefined}
        signupOverride={mode === 'staff' ? signupOverride : undefined}
        onTransferred={onTransferred}
      />
      <StaffReasonDialog {...staffAction.dialogProps} />
      <OverrideWarningDialog {...signupOverride.dialogProps} />
    </>
  );
}

function setup(props: HarnessProps) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <Harness {...props} />
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function pick(pk: number) {
  fireEvent.click(screen.getByTestId(`transfer-spot-option-${pk}`));
}

function confirmButton() {
  return screen.getByTestId('transfer-spot-confirm');
}

describe('TransferSpotDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.results = [user(21, 'Giver'), SAM, LEE];
  });
  afterEach(cleanup);

  it('excludes the giver from results', () => {
    setup({ mode: 'member' });
    expect(screen.queryByTestId('transfer-spot-option-21')).toBeNull();
    expect(screen.getByTestId('transfer-spot-option-31')).toBeTruthy();
    expect(screen.getByTestId('transfer-spot-option-41')).toBeTruthy();
  });

  it('member mode searches without orgId', () => {
    setup({ mode: 'member' });
    expect(h.search).toHaveBeenCalledWith(
      '',
      expect.objectContaining({ orgId: undefined, enabled: true }),
    );
  });

  it('staff mode passes orgId', () => {
    setup({ mode: 'staff' });
    expect(h.search).toHaveBeenCalledWith(
      '',
      expect.objectContaining({ orgId: ORG_ID, enabled: true }),
    );
  });

  it('staff mode lists org members first with a badge', () => {
    h.results = [LEE, SAM];
    setup({ mode: 'staff' });
    const options = screen
      .getAllByTestId(/^transfer-spot-option-/)
      .map((el) => el.getAttribute('data-testid'));
    expect(options).toEqual([
      'transfer-spot-option-31',
      'transfer-spot-option-41',
    ]);
    expect(
      within(screen.getByTestId('transfer-spot-option-31')).getByText('Member'),
    ).toBeTruthy();
  });

  it('shows transfer copy', () => {
    setup({ mode: 'member' });
    pick(31);
    expect(screen.getByTestId('transfer-spot-copy').textContent).toBe(
      "Give your place (#3, Approved) to Sam? You will be withdrawn. This can't be undone by you.",
    );
    expect(screen.queryByText('Staff will need to approve them.')).toBeNull();
  });

  it('adds the manual approval note in member mode', () => {
    setup({ mode: 'member', autoApprove: false });
    pick(31);
    expect(screen.getByText('Staff will need to approve them.')).toBeTruthy();
  });

  it('shows swap copy', () => {
    setup({ mode: 'member', signups: [GIVER, SAM_ROW] });
    pick(31);
    expect(screen.getByTestId('transfer-spot-copy').textContent).toBe(
      'Swap places with Sam? You take their place (#7, Waitlisted) and they take yours (#3, Approved).',
    );
    expect((confirmButton() as HTMLButtonElement).disabled).toBe(false);
  });

  it('member cannot pick a better place', () => {
    setup({ mode: 'member', signups: [GIVER, LEE_ROW] });
    pick(41);
    expect(
      screen.getByText(
        'You can only swap with someone whose place is behind yours',
      ),
    ).toBeTruthy();
    expect((confirmButton() as HTMLButtonElement).disabled).toBe(true);
  });

  it('staff may swap with a better place', () => {
    setup({ mode: 'staff', signups: [GIVER, LEE_ROW] });
    pick(41);
    expect(
      screen.queryByText(
        'You can only swap with someone whose place is behind yours',
      ),
    ).toBeNull();
    expect((confirmButton() as HTMLButtonElement).disabled).toBe(false);
  });

  it('renders ineligible requirements', async () => {
    h.transferSpot.mockRejectedValueOnce(
      axiosError(400, {
        code: 'recipient_ineligible',
        error: 'Sam is not eligible for this event.',
        reasons: [
          {
            code: 'steam_missing',
            rule: 'steam',
            message: 'Steam friend ID missing',
          },
          { code: 'mmr_missing', rule: 'mmr', message: 'MMR not verified' },
        ],
      }),
    );
    setup({ mode: 'member' });
    pick(31);
    fireEvent.click(confirmButton());
    const list = await screen.findByTestId('transfer-spot-reasons');
    expect(within(list).getByText('Steam friend ID missing')).toBeTruthy();
    expect(within(list).getByText('MMR not verified')).toBeTruthy();
    expect(screen.getByTestId('harness-open').textContent).toBe('true');
    expect(h.toastSuccess).not.toHaveBeenCalled();
  });

  it('shows server refusal message', async () => {
    h.transferSpot.mockRejectedValueOnce(
      axiosError(400, {
        code: 'transfer_disabled',
        error: 'Spot transfer is turned off for this event.',
      }),
    );
    setup({ mode: 'member' });
    pick(31);
    fireEvent.click(confirmButton());
    expect(
      (await screen.findByTestId('transfer-spot-refusal')).textContent,
    ).toContain('Spot transfer is turned off for this event.');
    expect(screen.queryByTestId('transfer-spot-reasons')).toBeNull();
  });

  it('member transfer posts without a reason and toasts by response mode', async () => {
    h.transferSpot.mockResolvedValueOnce(response('swap'));
    const onTransferred = vi.fn();
    setup({ mode: 'member', onTransferred });
    pick(31);
    fireEvent.click(confirmButton());
    await waitFor(() => expect(onTransferred).toHaveBeenCalledTimes(1));
    expect(h.transferSpot).toHaveBeenCalledWith(101, {
      recipient_user_id: 31,
    });
    expect(onTransferred.mock.calls[0][0].mode).toBe('swap');
    expect(h.toastSuccess).toHaveBeenCalledWith('You swapped places with Sam');
    expect(screen.getByTestId('harness-open').textContent).toBe('false');
  });

  it('staff mode collects a reason before calling the API', async () => {
    h.transferSpot.mockResolvedValueOnce(response('transfer'));
    setup({ mode: 'staff', policy: 'placements' });
    pick(31);
    fireEvent.click(confirmButton());
    const reason = await screen.findByTestId('staff-reason-input');
    expect(h.transferSpot).not.toHaveBeenCalled();
    fireEvent.change(reason, { target: { value: 'Swapped by request' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() =>
      expect(h.transferSpot).toHaveBeenCalledWith(101, {
        recipient_user_id: 31,
        reason: 'Swapped by request',
      }),
    );
    await waitFor(() =>
      expect(h.toastSuccess).toHaveBeenCalledWith("Gave user21's place to Sam"),
    );
  });

  it('staff 409 hands off to override dialog and toasts after the retry', async () => {
    h.transferSpot
      .mockRejectedValueOnce(axiosError(409, overrideBody))
      .mockResolvedValueOnce(response('transfer'));
    const onTransferred = vi.fn();
    setup({ mode: 'staff', onTransferred });
    pick(31);
    fireEvent.click(confirmButton());
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));
    const dialog = await screen.findByTestId('override-warning-dialog');
    expect(screen.getByTestId('harness-open').textContent).toBe('false');
    expect(h.toastSuccess).not.toHaveBeenCalled();
    fireEvent.change(within(dialog).getByTestId('override-reason'), {
      target: { value: 'Guest from partner organization' },
    });
    fireEvent.click(within(dialog).getByTestId('override-confirm'));
    await waitFor(() => expect(onTransferred).toHaveBeenCalledTimes(1));
    expect(h.transferSpot).toHaveBeenLastCalledWith(101, {
      recipient_user_id: 31,
      reason: 'Guest from partner organization',
      acknowledged_codes: ['not_org_member'],
    });
    expect(onTransferred.mock.calls[0][0].mode).toBe('transfer');
    expect(h.toastSuccess).toHaveBeenCalledWith("Gave user21's place to Sam");
  });

  it('contains no form element', () => {
    const { container } = setup({ mode: 'member', signups: [GIVER, SAM_ROW] });
    pick(31);
    const dialog = screen.getByTestId('transfer-spot-dialog');
    expect(dialog.querySelector('form')).toBeNull();
    expect(container.querySelector('form')).toBeNull();
  });
});
