// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { MmrApprovalModal } from '../MmrApprovalModal';
import type { EventSignupType } from '../schemas';

const signup = {
  id: 7,
  user: 5,
  username: 'player',
  suggested_mmr: 3200,
  org_user_mmr: null,
  user_data: null,
  dota_profile: null,
} as EventSignupType;
afterEach(cleanup);

async function recap() {
  await act(async () => {
    fireEvent.click(screen.getByTestId('mmr-modal-approve'));
  });
}

function setup(
  reasonMode?: 'required' | 'optional',
  onApprove = vi.fn().mockResolvedValue(true),
) {
  const props = {
    signup,
    open: true,
    onOpenChange: vi.fn(),
    onApprove,
    reasonMode,
  };
  const view = render(
    <TooltipProvider>
      <MmrApprovalModal {...props} />
    </TooltipProvider>,
  );
  return { ...view, props, onApprove };
}

describe('MMR approval staff reason recap', () => {
  it('requires a reason before approving and sends the trimmed text', async () => {
    const { onApprove } = setup('required');
    await recap();
    expect(screen.getByTestId('staff-reason-input')).toHaveAccessibleName(
      'Reason (recorded in signup history)',
    );
    expect(screen.getByTestId('mmr-confirm-approve')).toBeDisabled();
    fireEvent.change(screen.getByTestId('staff-reason-input'), {
      target: { value: '  placement correction  ' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('mmr-confirm-approve')).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId('mmr-confirm-approve'));
    await waitFor(() =>
      expect(onApprove).toHaveBeenCalledWith(7, 3200, 'placement correction'),
    );
  });

  it('defaults to an optional inline reason and approves without text', async () => {
    const { onApprove } = setup();
    await recap();
    expect(screen.getByTestId('staff-reason-input')).toHaveAccessibleName(
      'Reason (optional)',
    );
    await waitFor(() =>
      expect(screen.getByTestId('mmr-confirm-approve')).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId('mmr-confirm-approve'));
    await waitFor(() => expect(onApprove).toHaveBeenCalledWith(7, 3200, ''));
  });

  it('retains the recap and reason after a refused approval', async () => {
    const { onApprove } = setup('required', vi.fn().mockResolvedValue(false));
    await recap();
    fireEvent.change(screen.getByTestId('staff-reason-input'), {
      target: { value: 'keep me' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('mmr-confirm-approve')).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId('mmr-confirm-approve'));
    await waitFor(() =>
      expect(screen.getByTestId('mmr-confirm-approve')).toBeEnabled(),
    );
    expect(onApprove).toHaveBeenCalledWith(7, 3200, 'keep me');
    expect(screen.getByTestId('staff-reason-input')).toHaveValue('keep me');
  });

  it('clears the reason when another signup opens', async () => {
    const { rerender, props } = setup('required');
    await recap();
    fireEvent.change(screen.getByTestId('staff-reason-input'), {
      target: { value: 'previous player' },
    });
    rerender(
      <TooltipProvider>
        <MmrApprovalModal {...props} signup={{ ...signup, id: 8 }} />
      </TooltipProvider>,
    );
    await recap();
    expect(screen.getByTestId('staff-reason-input')).toHaveValue('');
    expect(screen.getByTestId('mmr-confirm-approve')).toBeDisabled();
  });

  it('blocks duplicate approvals while the request is in flight', async () => {
    let resolve!: (value: boolean) => void;
    const onApprove = vi.fn(
      () =>
        new Promise<boolean>((done) => {
          resolve = done;
        }),
    );
    setup(undefined, onApprove);
    await recap();
    await waitFor(() =>
      expect(screen.getByTestId('mmr-confirm-approve')).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId('mmr-confirm-approve'));
    await waitFor(() => expect(onApprove).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('mmr-confirm-approve')).toBeDisabled();
    fireEvent.keyDown(screen.getByTestId('staff-reason-input'), {
      key: 'Enter',
    });
    expect(onApprove).toHaveBeenCalledTimes(1);
    await act(async () => resolve(true));
    expect(screen.queryByTestId('mmr-confirm-approve')).toBeNull();
  });
});
