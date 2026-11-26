// @vitest-environment jsdom
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { StaffReasonDialog } from '../StaffReasonDialog';
import type { StaffReasonPolicy } from '../schemas';
import { useStaffAction } from '../useStaffAction';

const { toastError, info } = vi.hoisted(() => ({
  toastError: vi.fn(),
  info: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { error: toastError } }));
vi.mock('~/lib/logger', () => ({
  getLogger: () => ({ info, error: vi.fn() }),
}));

const signup = { id: 12, status: 'approved', user: 42 };
const reasonRequired = {
  isAxiosError: true,
  response: { status: 400, data: { error: 'reason_required' } },
};
const otherError = { response: { data: { error: 'Signup changed' } } };

function setup(policy: StaffReasonPolicy = 'optional', currentUserId = 1) {
  let actions!: ReturnType<typeof useStaffAction>;
  render(<Harness />);
  function Harness() {
    actions = useStaffAction({ policy, currentUserId });
    return (
      <TooltipProvider>
        <StaffReasonDialog {...actions.dialogProps} />
      </TooltipProvider>
    );
  }
  return () => actions;
}
async function submit(reason = 'r') {
  fireEvent.change(screen.getByTestId('staff-reason-input'), {
    target: { value: reason },
  });
  await waitFor(() =>
    expect(screen.getByTestId('staff-reason-confirm')).toBeEnabled(),
  );
  fireEvent.click(screen.getByTestId('staff-reason-confirm'));
}

describe('useStaffAction', () => {
  it('fires once without a dialog under optional policy', async () => {
    const actions = setup();
    const fire = vi.fn(async () => undefined);
    let result: boolean | undefined;
    await act(async () => {
      result = await actions().run('demote', signup, fire);
    });
    expect(result).toBe(true);
    expect(fire).toHaveBeenCalledExactlyOnceWith(undefined);
    expect(actions().isOpen).toBe(false);
  });

  it('collects a required placement reason before firing', async () => {
    const actions = setup('placements');
    const fire = vi.fn(async () => undefined);
    let result!: Promise<boolean>;
    act(() => {
      result = actions().run('demote', signup, fire);
    });
    expect(actions().isOpen).toBe(true);
    expect(actions().isOpen).toBe(actions().dialogProps.open);
    expect(fire).not.toHaveBeenCalled();
    await submit();
    await act(async () => {
      expect(await result).toBe(true);
    });
    expect(fire).toHaveBeenCalledExactlyOnceWith('r');
  });

  it('never prompts staff changing their own signup', async () => {
    const actions = setup('all_staff_changes', 42);
    const fire = vi.fn(async () => undefined);
    await act(async () => {
      expect(await actions().run('demote', signup, fire)).toBe(true);
    });
    expect(fire).toHaveBeenCalledExactlyOnceWith(undefined);
    expect(actions().isOpen).toBe(false);
  });

  it.each([undefined, 'typed'])(
    'recovers server reason_required and seeds %s',
    async (reason) => {
      const actions = setup();
      const fire = vi
        .fn()
        .mockRejectedValueOnce(reasonRequired)
        .mockResolvedValueOnce(undefined);
      let result!: Promise<boolean>;
      await act(async () => {
        result = actions().run('approve', signup, fire, { reason });
      });
      expect(
        screen.getByText('A reason is required for this change.'),
      ).toBeInTheDocument();
      expect(screen.getByTestId('staff-reason-input')).toHaveValue(
        reason ?? '',
      );
      expect(info).toHaveBeenCalledWith('Staff reason required by server', {
        action: 'approve',
        signupId: 12,
      });
      await submit('retried');
      await act(async () => {
        expect(await result).toBe(true);
      });
      expect(fire.mock.calls).toEqual([[reason], ['retried']]);
    },
  );

  it('toasts DRF errors from one-click actions and resolves false', async () => {
    const actions = setup();
    const fire = vi.fn().mockRejectedValue(otherError);
    await act(async () => {
      expect(await actions().run('confirm', signup, fire)).toBe(false);
    });
    expect(toastError).toHaveBeenCalledWith('Signup changed');
  });

  it('preserves the reason on an error inside the dialog, allowing retry', async () => {
    const actions = setup('placements');
    const fire = vi
      .fn()
      .mockRejectedValueOnce(otherError)
      .mockResolvedValueOnce(undefined);
    let result!: Promise<boolean>;
    act(() => {
      result = actions().run('demote', signup, fire);
    });
    await submit('retain');
    await waitFor(() =>
      expect(screen.getByText('Signup changed')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('staff-reason-input')).toHaveValue('retain');
    expect(actions().isOpen).toBe(true);
    await waitFor(() =>
      expect(screen.getByTestId('staff-reason-confirm')).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId('staff-reason-confirm'));
    await act(async () => {
      expect(await result).toBe(true);
    });
  });

  it('collects without firing and resolves null on cancel', async () => {
    const actions = setup('placements');
    let collected!: Promise<string | null>;
    act(() => {
      collected = actions().collect('admin_add', { userId: 3 });
    });
    await submit('add player');
    await act(async () => {
      expect(await collected).toBe('add player');
    });
    act(() => {
      collected = actions().collect('admin_add', {
        userId: 4,
        title: 'Add signup',
      });
    });
    expect(screen.getByTestId('staff-reason-input')).toHaveValue('');
    fireEvent.click(screen.getByTestId('staff-reason-cancel'));
    await act(async () => {
      expect(await collected).toBeNull();
    });
  });
});
