// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReasonDialog } from '../ReasonDialog';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderDialog(
  props: Partial<React.ComponentProps<typeof ReasonDialog>> = {},
) {
  const onConfirm = vi.fn();
  const onOpenChange = vi.fn();
  const utils = render(
    <ReasonDialog
      open
      onOpenChange={onOpenChange}
      changeCount={2}
      pending={false}
      onConfirm={onConfirm}
      {...props}
    />,
  );
  return { ...utils, onConfirm, onOpenChange };
}

function type(value: string) {
  fireEvent.change(screen.getByTestId('conduct-reason-input'), {
    target: { value },
  });
}

describe('ReasonDialog', () => {
  it('Save stays disabled for a padded two-character reason', () => {
    renderDialog();
    expect(screen.getByTestId('conduct-reason-confirm')).toBeDisabled();
    type('  ab  ');
    expect(screen.getByTestId('conduct-reason-confirm')).toBeDisabled();
  });

  it('confirms with the trimmed reason', () => {
    const { onConfirm } = renderDialog();
    type('  no show  ');
    const confirm = screen.getByTestId('conduct-reason-confirm');
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith('no show');
  });

  it('pads the header clear of the close button', () => {
    renderDialog();
    const title = screen.getByText('Why are you changing attendance?');
    expect(title.parentElement).toHaveClass('px-8', 'sm:pl-0');
  });

  it('the input is capped at 500', () => {
    renderDialog();
    expect(screen.getByTestId('conduct-reason-input')).toHaveAttribute(
      'maxLength',
      '500',
    );
  });

  it('clears the reason when reopened', () => {
    const { rerender, onConfirm, onOpenChange } = renderDialog();
    type('late again');
    const props = {
      onOpenChange,
      changeCount: 2,
      pending: false,
      onConfirm,
    };
    rerender(<ReasonDialog open={false} {...props} />);
    rerender(<ReasonDialog open {...props} />);
    expect(screen.getByTestId('conduct-reason-input')).toHaveValue('');
  });

  it('keeps the reason while open after a failed save', () => {
    const { rerender, onConfirm, onOpenChange } = renderDialog();
    type('late again');
    const props = { onOpenChange, changeCount: 2, onConfirm };
    rerender(<ReasonDialog open pending {...props} />);
    rerender(<ReasonDialog open pending={false} {...props} />);
    expect(screen.getByTestId('conduct-reason-input')).toHaveValue(
      'late again',
    );
  });

  it('shows the change count', () => {
    renderDialog();
    expect(screen.getByTestId('conduct-reason-dialog')).toHaveTextContent(
      '2 changes',
    );
  });
});
