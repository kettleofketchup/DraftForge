// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import {
  StaffReasonDialog,
  type StaffReasonDialogProps,
} from '../StaffReasonDialog';

function Harness(props: Partial<StaffReasonDialogProps>) {
  const [open, setOpen] = useState(true);
  return (
    <TooltipProvider>
      <StaffReasonDialog
        open={open}
        onOpenChange={setOpen}
        title="Demote signup"
        actionLabel="Demote"
        required
        submitting={false}
        onConfirm={async () => true}
        {...props}
      />
    </TooltipProvider>
  );
}

const input = () => screen.getByTestId('staff-reason-input');
const confirm = () => screen.getByTestId('staff-reason-confirm');

describe('StaffReasonDialog', () => {
  it('requires nonblank text and enforces the shared 500 character limit', async () => {
    render(<Harness />);
    expect(confirm()).toBeDisabled();
    fireEvent.change(input(), { target: { value: '   ' } });
    await waitFor(() =>
      expect(screen.getByTestId('staff-reason-error')).toBeInTheDocument(),
    );
    expect(confirm()).toBeDisabled();
    fireEvent.change(input(), { target: { value: 'x'.repeat(500) } });
    await waitFor(() => expect(confirm()).toBeEnabled());
    fireEvent.change(input(), { target: { value: 'x'.repeat(501) } });
    await waitFor(() => expect(confirm()).toBeDisabled());
    expect(screen.getByTestId('staff-reason-error')).toBeInTheDocument();
  });

  it('allows an empty optional reason and uses only the shared dialog buttons, without a form', async () => {
    const onConfirm = vi.fn(async () => true);
    render(<Harness required={false} onConfirm={onConfirm} />);
    await waitFor(() => expect(confirm()).toBeEnabled());
    expect(document.querySelector('form')).toBeNull();
    expect(
      screen
        .getAllByRole('button')
        .map((button) => button.dataset.testid)
        .sort(),
    ).toEqual(['staff-reason-cancel', 'staff-reason-confirm']);
    fireEvent.click(confirm());
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith(''));
    await waitFor(() =>
      expect(screen.queryByTestId('staff-reason-dialog')).toBeNull(),
    );
  });

  it('keeps text and server error visible when confirmation returns false', async () => {
    const onConfirm = vi.fn(async () => false);
    render(<Harness serverError="Signup changed" onConfirm={onConfirm} />);
    expect(screen.getByText('Signup changed')).toBeInTheDocument();
    fireEvent.change(input(), { target: { value: 'keep me' } });
    await waitFor(() => expect(confirm()).toBeEnabled());
    fireEvent.click(confirm());
    await waitFor(() => expect(onConfirm).toHaveBeenCalledOnce());
    expect(input()).toHaveValue('keep me');
    expect(screen.getByTestId('staff-reason-dialog')).toBeInTheDocument();
  });

  it('disables an empty required prompt immediately after an optional prompt was valid', async () => {
    const view = render(<Harness required={false} />);
    await waitFor(() => expect(confirm()).toBeEnabled());
    view.rerender(<Harness required resetKey={1} />);
    expect(input()).toHaveValue('');
    expect(confirm()).toBeDisabled();
  });

  it('guards repeated Enter while a request is pending', async () => {
    let finish!: (value: boolean) => void;
    const onConfirm = vi.fn(
      () =>
        new Promise<boolean>((resolve) => {
          finish = resolve;
        }),
    );
    render(<Harness onConfirm={onConfirm} initialReason="already typed" />);
    await waitFor(() => expect(confirm()).toBeEnabled());
    fireEvent.keyDown(input(), { key: 'Enter' });
    fireEvent.keyDown(input(), { key: 'Enter' });
    await waitFor(() => expect(onConfirm).toHaveBeenCalledOnce());
    expect(screen.getByTestId('staff-reason-cancel')).toBeDisabled();
    finish(true);
    await waitFor(() =>
      expect(screen.queryByTestId('staff-reason-dialog')).toBeNull(),
    );
  });
});
