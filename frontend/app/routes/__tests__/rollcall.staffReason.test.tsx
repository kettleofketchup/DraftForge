// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { h, renderRollCall, signup } from './rollcallHarness';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
const key = (key: string, target: HTMLElement | Window = window) =>
  fireEvent.keyDown(target, { key });
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

it('does not advance the selected row until a required Restore succeeds', async () => {
  renderRollCall({
    event: { staff_reason_policy: 'placements' },
    signups: [signup(101, 'cancelled'), signup(102, 'cancelled')],
  });
  key('1');
  expect(screen.getByTestId('rollcall-row-101')).toHaveAttribute(
    'data-focused',
    'true',
  );
  fireEvent.click(screen.getByTestId('staff-reason-cancel'));
  expect(screen.getByTestId('rollcall-row-101')).toHaveAttribute(
    'data-focused',
    'true',
  );
  key('1');
  type('restore');
  await waitFor(() =>
    expect(screen.getByTestId('staff-reason-confirm')).toBeEnabled(),
  );
  fireEvent.click(screen.getByTestId('staff-reason-confirm'));
  await waitFor(() =>
    expect(screen.getByTestId('rollcall-row-102')).toHaveAttribute(
      'data-focused',
      'true',
    ),
  );
});

it('retains an inline reason and focus when the server refuses a change', async () => {
  renderRollCall({ signups: [signup(101), signup(102)] });
  h.actions.confirm.mutateAsync.mockRejectedValueOnce({
    response: { data: { error: 'Cannot confirm this signup.' } },
  });
  key('1');
  type('retain');
  key('Enter', input());
  await waitFor(() =>
    expect(h.actions.confirm.mutateAsync).toHaveBeenCalledTimes(1),
  );
  await waitFor(() =>
    expect(screen.getByTestId('rollcall-confirm-dialog-confirm')).toBeEnabled(),
  );
  expect(input()).toHaveValue('retain');
  expect(screen.getByTestId('rollcall-row-101')).toHaveAttribute(
    'data-focused',
    'true',
  );
});

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

const focused = (id: number) =>
  expect(screen.getByTestId(`rollcall-row-${id}`)).toHaveAttribute(
    'data-focused',
    'true',
  );

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
  '$name advances within the original section after the optimistic move resolves',
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
    act(() =>
      view.rerenderSignups(
        rows.map((s) => (s.id === acted ? signup(s.id, moved) : s)),
      ),
    );
    focused(acted);
    await act(async () => resolve({}));
    await waitFor(() => focused(next));
  },
);
