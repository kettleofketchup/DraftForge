// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { h, renderRollCall, signup } from './rollcallHarness';

afterEach(() => {
  cleanup();
  h.actions.confirm.isPending = false;
  vi.clearAllMocks();
});
const key = (key: string, target: HTMLElement | Window = window) =>
  fireEvent.keyDown(target, { key });
const focused = (id: number) =>
  expect(screen.getByTestId(`rollcall-row-${id}`)).toHaveAttribute(
    'data-focused',
    'true',
  );
const input = () => screen.getByTestId('staff-reason-input');
const type = (value: string) =>
  fireEvent.change(input(), { target: { value } });

it('optional confirm keeps the field unfocused and accepts Enter without a reason', async () => {
  renderRollCall();
  key('1');
  expect(input()).not.toHaveFocus();
  key('Enter', screen.getByRole('alertdialog'));
  await waitFor(() =>
    expect(h.actions.confirm.mutateAsync).toHaveBeenCalledExactlyOnceWith({
      id: 101,
    }),
  );
});

it('required confirm focuses the reason, blocks empty Enter and ignores action keys in the field', async () => {
  renderRollCall({ event: { staff_reason_policy: 'all_staff_changes' } });
  key('1');
  await waitFor(() => expect(input()).toHaveFocus());
  key('Enter', input());
  expect(h.actions.confirm.mutateAsync).not.toHaveBeenCalled();
  key('1', input());
  key('2', input());
  expect(screen.getAllByRole('alertdialog')).toHaveLength(1);
  expect(h.actions.reject.mutateAsync).not.toHaveBeenCalled();
  type('late');
  key('Enter', input());
  await waitFor(() =>
    expect(h.actions.confirm.mutateAsync).toHaveBeenCalledExactlyOnceWith({
      id: 101,
      reason: 'late',
    }),
  );
});

it('does not leak a rejected row reason to the next row', async () => {
  renderRollCall({ signups: [signup(101), signup(102)] });
  key('2');
  type('x');
  fireEvent.click(screen.getByTestId('rollcall-reject-dialog-cancel'));
  fireEvent.click(
    within(screen.getByTestId('rollcall-row-102')).getByTestId(
      'rollcall-reject-btn',
    ),
  );
  expect(input()).toHaveValue('');
});

it.each(['optional', 'placements'] as const)(
  'Restore follows %s policy',
  async (policy) => {
    renderRollCall({
      event: { staff_reason_policy: policy },
      signups: [signup(101, 'cancelled')],
    });
    key('1');
    if (policy === 'placements') {
      expect(h.actions.reinstate.mutateAsync).not.toHaveBeenCalled();
      type('restore seat');
      await waitFor(() =>
        expect(screen.getByTestId('staff-reason-confirm')).toBeEnabled(),
      );
      fireEvent.click(screen.getByTestId('staff-reason-confirm'));
    }
    await waitFor(() =>
      expect(h.actions.reinstate.mutateAsync).toHaveBeenCalledExactlyOnceWith(
        policy === 'placements'
          ? { id: 101, reason: 'restore seat' }
          : { id: 101 },
      ),
    );
  },
);

it('recovers from server policy changes with the inline reason preserved', async () => {
  renderRollCall();
  h.actions.confirm.mutateAsync.mockRejectedValueOnce({
    isAxiosError: true,
    response: { status: 400, data: { error: 'reason_required' } },
  });
  key('1');
  type('typed before refresh');
  await waitFor(() =>
    expect(screen.getByTestId('rollcall-confirm-dialog-confirm')).toBeEnabled(),
  );
  fireEvent.click(screen.getByTestId('rollcall-confirm-dialog-confirm'));
  await screen.findByTestId('staff-reason-dialog');
  const recoveryInput = within(
    screen.getByTestId('staff-reason-dialog'),
  ).getByTestId('staff-reason-input');
  expect(recoveryInput).toHaveValue('typed before refresh');
  fireEvent.click(screen.getByTestId('staff-reason-confirm'));
  await waitFor(() =>
    expect(h.actions.confirm.mutateAsync).toHaveBeenCalledTimes(2),
  );
  expect(h.actions.confirm.mutateAsync).toHaveBeenLastCalledWith({
    id: 101,
    reason: 'typed before refresh',
  });
});

it('blocks row and tournament shortcuts while Restore reason dialog is open on a non-input control', async () => {
  renderRollCall({
    event: { staff_reason_policy: 'placements' },
    signups: [signup(101, 'cancelled')],
  });
  key('1');
  const cancel = screen.getByTestId('staff-reason-cancel');
  cancel.focus();
  key('2', cancel);
  key('S', cancel);
  expect(screen.getAllByRole('alertdialog')).toHaveLength(1);
  expect(screen.queryByTestId('rollcall-start-dialog-confirm')).toBeNull();
  expect(screen.queryByTestId('rollcall-reject-dialog-confirm')).toBeNull();
  for (const action of Object.values(h.actions))
    expect(action.mutateAsync).not.toHaveBeenCalled();
  expect(h.start.mutateAsync).not.toHaveBeenCalled();
});

it.each(['approved', 'confirmed'] as const)(
  'records a required %s removal reason',
  async (status) => {
    renderRollCall({
      event: { staff_reason_policy: 'all_staff_changes' },
      signups: [signup(101, status)],
    });
    key('2');
    type('staff correction');
    key('Enter', input());
    await waitFor(() =>
      expect(
        h.actions[status === 'approved' ? 'reject' : 'cancel'].mutateAsync,
      ).toHaveBeenCalledExactlyOnceWith({
        id: 101,
        reason: 'staff correction',
      }),
    );
  },
);

it('keeps the row on a cancelled Restore prompt and advances once the reason is valid', async () => {
  renderRollCall({
    event: { staff_reason_policy: 'placements' },
    signups: [signup(101, 'cancelled'), signup(102, 'cancelled')],
  });
  h.actions.reinstate.mutateAsync.mockImplementation(
    () => new Promise(() => {}),
  );
  key('1');
  focused(101);
  fireEvent.click(screen.getByTestId('staff-reason-cancel'));
  focused(101);
  expect(h.actions.reinstate.mutateAsync).not.toHaveBeenCalled();
  key('1');
  type('restore');
  await waitFor(() =>
    expect(screen.getByTestId('staff-reason-confirm')).toBeEnabled(),
  );
  fireEvent.click(screen.getByTestId('staff-reason-confirm'));
  await waitFor(() => focused(102));
  expect(h.actions.reinstate.mutateAsync).toHaveBeenCalledExactlyOnceWith({
    id: 101,
    reason: 'restore',
  });
  await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
});

it('closes and advances at once, then toasts when the server refuses a change', async () => {
  renderRollCall({ signups: [signup(101), signup(102)] });
  let reject!: (error: unknown) => void;
  h.actions.confirm.mutateAsync.mockImplementationOnce(
    () => new Promise((_, r) => (reject = r)),
  );
  key('1');
  type('retain');
  key('Enter', input());
  await waitFor(() => focused(102));
  expect(screen.queryByRole('alertdialog')).toBeNull();
  expect(h.actions.confirm.mutateAsync).toHaveBeenCalledExactlyOnceWith({
    id: 101,
    reason: 'retain',
  });
  await act(async () =>
    reject({ response: { data: { error: 'Cannot confirm this signup.' } } }),
  );
  expect(h.toastError).toHaveBeenCalledWith('Cannot confirm this signup.');
  expect(screen.queryByRole('alertdialog')).toBeNull();
});

it.each(['optional', 'all_staff_changes'] as const)(
  '%s keeps confirming the next rows while earlier requests are in flight',
  async (policy) => {
    renderRollCall({
      event: { staff_reason_policy: policy },
      signups: [signup(101), signup(102)],
    });
    h.actions.confirm.isPending = true;
    h.actions.confirm.mutateAsync.mockImplementation(
      () => new Promise(() => {}),
    );
    const required = policy === 'all_staff_changes';
    for (const id of [101, 102]) {
      key('1');
      if (required) type(`here ${id}`);
      await waitFor(() =>
        expect(
          screen.getByTestId('rollcall-confirm-dialog-confirm'),
        ).toBeEnabled(),
      );
      key('Enter', required ? input() : screen.getByRole('alertdialog'));
      await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
      if (id === 101) focused(102);
    }
    expect(h.actions.confirm.mutateAsync.mock.calls).toEqual([
      [{ id: 101, ...(required ? { reason: 'here 101' } : {}) }],
      [{ id: 102, ...(required ? { reason: 'here 102' } : {}) }],
    ]);
    key('s');
    expect(
      await screen.findByTestId('rollcall-start-dialog-confirm'),
    ).toBeInTheDocument();
  },
);

it('waitlist approval recap requires and sends a placement reason', async () => {
  renderRollCall({
    event: { staff_reason_policy: 'placements' },
    signups: [signup(101, 'waitlisted')],
  });
  key('1');
  await act(async () => {
    fireEvent.click(screen.getByTestId('mmr-modal-approve'));
  });
  expect(input()).toHaveAccessibleName('Reason (recorded in signup history)');
  expect(screen.getByTestId('mmr-confirm-approve')).toBeDisabled();
  type('seat correction');
  await waitFor(() =>
    expect(screen.getByTestId('mmr-confirm-approve')).toBeEnabled(),
  );
  fireEvent.click(screen.getByTestId('mmr-confirm-approve'));
  await waitFor(() =>
    expect(h.actions.approve.mutateAsync).toHaveBeenCalledExactlyOnceWith({
      id: 101,
      mmr: 3200,
      reason: 'seat correction',
    }),
  );
});

it.each([
  {
    name: 'confirm',
    action: 'confirm',
    rows: [signup(100, 'confirmed'), signup(101), signup(102)],
    keys: ['Home', 'j', '1'],
    submit: 'rollcall-confirm-dialog-confirm',
    moved: 'confirmed',
    acted: 101,
    next: 102,
  },
  {
    name: 'reject',
    action: 'reject',
    rows: [signup(101), signup(102), signup(103, 'rejected')],
    keys: ['Home', '2'],
    submit: 'rollcall-reject-dialog-confirm',
    moved: 'rejected',
    acted: 101,
    next: 102,
  },
  {
    name: 'remove',
    action: 'cancel',
    rows: [signup(100, 'confirmed'), signup(101, 'confirmed'), signup(102)],
    keys: ['Home', '2'],
    submit: 'rollcall-cancel-dialog-confirm',
    moved: 'cancelled',
    acted: 100,
    next: 101,
  },
  {
    name: 'Restore',
    action: 'reinstate',
    rows: [
      signup(101, 'cancelled'),
      signup(102, 'cancelled'),
      signup(103, 'approved'),
    ],
    keys: ['End', 'k', '1'],
    submit: null,
    moved: 'approved',
    acted: 101,
    next: 102,
  },
  {
    name: 'approve',
    action: 'approve',
    rows: [
      signup(101, 'waitlisted'),
      signup(102, 'waitlisted'),
      signup(103, 'approved'),
    ],
    keys: ['End', 'k', '1'],
    submit: 'mmr-modal-approve',
    moved: 'approved',
    acted: 101,
    next: 102,
  },
] as const)(
  '$name closes and advances within the original section before the server answers',
  async ({ action, rows, keys, submit, moved, acted, next }) => {
    const view = renderRollCall({ signups: [...rows] });
    let resolve!: (value: unknown) => void;
    h.actions[action].mutateAsync.mockImplementationOnce(
      () => new Promise((r) => (resolve = r)),
    );
    for (const k of keys) key(k);
    if (submit) {
      await act(async () => {
        fireEvent.click(screen.getByTestId(submit));
      });
      if (action === 'approve') {
        await waitFor(() =>
          expect(screen.getByTestId('mmr-confirm-approve')).toBeEnabled(),
        );
        fireEvent.click(screen.getByTestId('mmr-confirm-approve'));
      }
    }
    await waitFor(() =>
      expect(h.actions[action].mutateAsync).toHaveBeenCalledTimes(1),
    );
    await waitFor(() => focused(next));
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).toBeNull();
      expect(screen.queryByRole('dialog')).toBeNull();
    });
    act(() =>
      view.rerenderSignups(
        rows.map((s) => (s.id === acted ? signup(s.id, moved) : s)),
      ),
    );
    focused(next);
    await act(async () => resolve({}));
    focused(next);
  },
);

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
const voidButton = (id: number) =>
  within(screen.getByTestId(`rollcall-row-${id}`)).getByTestId(
    'rollcall-void-withdrawal-btn',
  );

describe('Void withdrawal and override-aware Restore', () => {
  it('shows Void on cancelled and rejected rows only', () => {
    renderRollCall({
      signups: [
        signup(101, 'cancelled'),
        signup(102, 'rejected'),
        signup(103, 'approved'),
        signup(104, 'dropped'),
      ],
    });
    expect(voidButton(101)).toHaveTextContent('Void');
    expect(voidButton(102)).toBeInTheDocument();
    for (const id of [103, 104])
      expect(
        within(screen.getByTestId(`rollcall-row-${id}`)).queryByTestId(
          'rollcall-void-withdrawal-btn',
        ),
      ).toBeNull();
  });

  it.each(['optional', 'placements'] as const)(
    'Void dispatches void_withdrawal under %s policy and moves focus',
    async (policy) => {
      renderRollCall({
        event: { staff_reason_policy: policy },
        signups: [signup(101, 'cancelled'), signup(102, 'cancelled')],
      });
      focused(101);
      fireEvent.click(voidButton(101));
      if (policy === 'placements') {
        expect(h.actions.voidWithdrawal.mutateAsync).not.toHaveBeenCalled();
        expect(screen.getByRole('alertdialog')).toHaveTextContent(
          'Void withdrawal',
        );
        type('mistaken');
        await waitFor(() =>
          expect(screen.getByTestId('staff-reason-confirm')).toBeEnabled(),
        );
        fireEvent.click(screen.getByTestId('staff-reason-confirm'));
      }
      await waitFor(() =>
        expect(
          h.actions.voidWithdrawal.mutateAsync,
        ).toHaveBeenCalledExactlyOnceWith(
          policy === 'placements'
            ? { id: 101, reason: 'mistaken' }
            : { id: 101 },
        ),
      );
      await waitFor(() => focused(102));
      expect(h.actions.reinstate.mutateAsync).not.toHaveBeenCalled();
    },
  );

  it('Void 409 opens the override dialog and confirm retries with acknowledged codes', async () => {
    renderRollCall({ signups: [signup(101, 'cancelled')] });
    h.actions.voidWithdrawal.mutateAsync.mockRejectedValueOnce(overCapacity());
    fireEvent.click(voidButton(101));
    const dialog = await screen.findByTestId('override-warning-dialog');
    fireEvent.change(within(dialog).getByRole('textbox'), {
      target: { value: 'mistaken' },
    });
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole('button', { name: /override/i }),
      );
    });
    await waitFor(() =>
      expect(h.actions.voidWithdrawal.mutateAsync).toHaveBeenLastCalledWith({
        id: 101,
        reason: 'mistaken',
        acknowledged_codes: ['over_capacity'],
      }),
    );
    expect(h.toastError).not.toHaveBeenCalled();
  });

  it('keyboard 1 Restore with a 409 opens the override dialog', async () => {
    renderRollCall({ signups: [signup(101, 'cancelled')] });
    h.actions.reinstate.mutateAsync.mockRejectedValueOnce(overCapacity());
    key('1');
    expect(
      await screen.findByTestId('override-warning-dialog'),
    ).toHaveTextContent('Event is at capacity');
    expect(h.actions.reinstate.mutateAsync).toHaveBeenCalledExactlyOnceWith({
      id: 101,
    });
    expect(h.toastError).not.toHaveBeenCalled();
  });

  it('Restore 409 leaves the row in its Removed group and blocks keys while the override dialog is open', async () => {
    renderRollCall({
      signups: [
        signup(101, 'cancelled'),
        signup(102, 'cancelled'),
        signup(103, 'approved'),
      ],
    });
    h.actions.reinstate.mutateAsync.mockRejectedValueOnce(overCapacity());
    key('End');
    key('k');
    focused(101);
    key('1');
    await screen.findByTestId('override-warning-dialog');
    await waitFor(() => focused(102));
    const removed = screen.getByText(/^Other \(/).parentElement!;
    expect(within(removed).getByTestId('rollcall-row-101')).toBeInTheDocument();
    const awaiting = screen.getByTestId(
      'rollcall-awaiting-section',
    ).parentElement!;
    expect(within(awaiting).queryByTestId('rollcall-row-101')).toBeNull();
    for (const k of ['k', 'ArrowUp', 'Home', '1', '2', 's']) key(k);
    focused(102);
    expect(h.actions.reinstate.mutateAsync).toHaveBeenCalledTimes(1);
    for (const action of ['approve', 'confirm', 'reject', 'cancel'] as const)
      expect(h.actions[action].mutateAsync).not.toHaveBeenCalled();
    expect(screen.queryByTestId('rollcall-start-dialog-confirm')).toBeNull();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('Void is not bound to a key', async () => {
    renderRollCall({ signups: [signup(101, 'cancelled')] });
    for (const k of ['2', '3', 'v', 'V', 'Enter']) key(k);
    key('1');
    await waitFor(() =>
      expect(h.actions.reinstate.mutateAsync).toHaveBeenCalledTimes(1),
    );
    expect(h.actions.voidWithdrawal.mutateAsync).not.toHaveBeenCalled();
    expect(voidButton(101).querySelector('kbd')).toBeNull();
  });

  it('retries the row whose in-flight Restore hit the 409, not the later row', async () => {
    renderRollCall({
      signups: [signup(101, 'cancelled'), signup(102, 'cancelled')],
    });
    let rejectFirst!: (err: unknown) => void;
    h.actions.reinstate.mutateAsync
      .mockImplementationOnce(
        () => new Promise((_, reject) => (rejectFirst = reject)),
      )
      .mockResolvedValueOnce({});
    focused(101);
    key('1');
    await waitFor(() => focused(102));
    key('1');
    await waitFor(() =>
      expect(h.actions.reinstate.mutateAsync).toHaveBeenCalledTimes(2),
    );
    await act(async () => rejectFirst(overCapacity()));
    const dialog = await screen.findByTestId('override-warning-dialog');
    expect(dialog).toHaveTextContent('player_101');
    expect(dialog).not.toHaveTextContent('player_102');
    fireEvent.change(within(dialog).getByRole('textbox'), {
      target: { value: 'seat them' },
    });
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole('button', { name: /override/i }),
      );
    });
    expect(h.actions.reinstate.mutateAsync.mock.calls).toEqual([
      [{ id: 101 }],
      [{ id: 102 }],
      [{ id: 101, reason: 'seat them', acknowledged_codes: ['over_capacity'] }],
    ]);
    await waitFor(() =>
      expect(screen.queryByTestId('override-warning-dialog')).toBeNull(),
    );
    expect(h.toastError).not.toHaveBeenCalled();
  });

  it('queues a second 409 behind the first and retries each with its own kind', async () => {
    renderRollCall({
      signups: [signup(101, 'cancelled'), signup(102, 'cancelled')],
    });
    h.actions.reinstate.mutateAsync.mockRejectedValueOnce(overCapacity());
    h.actions.voidWithdrawal.mutateAsync.mockRejectedValueOnce(overCapacity());
    fireEvent.click(voidButton(102));
    fireEvent.click(
      within(screen.getByTestId('rollcall-row-101')).getByTestId(
        'rollcall-restore-btn',
      ),
    );
    let dialog = await screen.findByTestId('override-warning-dialog');
    await waitFor(() =>
      expect(h.actions.reinstate.mutateAsync).toHaveBeenCalledTimes(1),
    );
    expect(dialog).toHaveTextContent("voiding player_102's withdrawal");
    fireEvent.change(within(dialog).getByRole('textbox'), {
      target: { value: 'first' },
    });
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole('button', { name: /override/i }),
      );
    });
    expect(h.actions.voidWithdrawal.mutateAsync).toHaveBeenLastCalledWith({
      id: 102,
      reason: 'first',
      acknowledged_codes: ['over_capacity'],
    });
    dialog = await screen.findByTestId('override-warning-dialog');
    await waitFor(() =>
      expect(dialog).toHaveTextContent('restoring player_101'),
    );
    expect(within(dialog).getByRole('textbox')).toHaveValue('');
    fireEvent.change(within(dialog).getByRole('textbox'), {
      target: { value: 'second' },
    });
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole('button', { name: /override/i }),
      );
    });
    expect(h.actions.reinstate.mutateAsync).toHaveBeenLastCalledWith({
      id: 101,
      reason: 'second',
      acknowledged_codes: ['over_capacity'],
    });
    await waitFor(() =>
      expect(screen.queryByTestId('override-warning-dialog')).toBeNull(),
    );
  });

  it('names the void in the fallback toast when an acknowledged retry fails', async () => {
    renderRollCall({ signups: [signup(101, 'cancelled')] });
    h.actions.voidWithdrawal.mutateAsync
      .mockRejectedValueOnce(overCapacity())
      .mockRejectedValueOnce(axiosError(500, {}));
    fireEvent.click(voidButton(101));
    const dialog = await screen.findByTestId('override-warning-dialog');
    fireEvent.change(within(dialog).getByRole('textbox'), {
      target: { value: 'why' },
    });
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole('button', { name: /override/i }),
      );
    });
    await waitFor(() =>
      expect(h.toastError).toHaveBeenCalledWith('Failed to void withdrawal'),
    );
  });
});
