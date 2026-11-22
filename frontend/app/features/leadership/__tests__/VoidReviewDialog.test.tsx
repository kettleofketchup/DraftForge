// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { VoidReviewDialog } from '../VoidReviewDialog';

function renderDialog(
  props: Partial<Parameters<typeof VoidReviewDialog>[0]> = {},
) {
  const onConfirm = vi.fn();
  render(
    <VoidReviewDialog
      open
      onOpenChange={vi.fn()}
      pending={false}
      error={null}
      onConfirm={onConfirm}
      {...props}
    />,
  );
  return { onConfirm };
}

describe('VoidReviewDialog', () => {
  it('needs a non-blank reason and confirms it trimmed', () => {
    const { onConfirm } = renderDialog();
    const confirm = screen.getByTestId('leadership-void-confirm');
    expect(confirm).toBeDisabled();
    const input = screen.getByTestId('leadership-void-reason');
    fireEvent.change(input, { target: { value: '   ' } });
    expect(confirm).toBeDisabled();
    fireEvent.change(input, { target: { value: '  spam ' } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith('spam');
  });

  it('caps the reason at 500 characters', () => {
    renderDialog();
    expect(screen.getByTestId('leadership-void-reason')).toHaveAttribute(
      'maxLength',
      '500',
    );
  });

  it('shows the error as an alert', () => {
    renderDialog({ error: 'That review no longer exists.' });
    expect(screen.getByRole('alert')).toHaveTextContent(
      'That review no longer exists.',
    );
  });

  it('keeps the close button clear of the title', () => {
    renderDialog();
    expect(
      screen.getByRole('heading', { name: 'Void this review?' }).parentElement,
    ).toHaveClass('pr-8');
  });
});
