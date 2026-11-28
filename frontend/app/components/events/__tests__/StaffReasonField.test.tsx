// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Form } from '~/components/ui/form';
import { StaffReasonField, useStaffReasonForm } from '../StaffReasonField';

function Harness({
  required = true,
  resetKey = 1,
  open = true,
  onSubmit = vi.fn(),
}) {
  const form = useStaffReasonForm(required, resetKey, open);
  return (
    <Form {...form}>
      <StaffReasonField form={form} required={required} onSubmit={onSubmit} />
    </Form>
  );
}

describe('StaffReasonField', () => {
  it.each([true, false])(
    'labels required=%s and counts characters',
    async (required) => {
      render(<Harness required={required} />);
      const input = screen.getByLabelText(
        required ? 'Reason (recorded in signup history)' : 'Reason (optional)',
      );
      fireEvent.change(input, { target: { value: 'x'.repeat(31) } });
      expect(screen.getByText('31/500')).toBeInTheDocument();
      expect(document.querySelector('form')).toBeNull();
    },
  );

  it('submits Enter only with valid text', async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    const input = screen.getByTestId('staff-reason-input');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: 'abc' } });
    await waitFor(() =>
      expect(screen.queryByTestId('staff-reason-error')).toBeNull(),
    );
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  });

  it('resets when the target changes and when reopened', async () => {
    const { rerender } = render(<Harness />);
    const input = screen.getByTestId('staff-reason-input');
    fireEvent.change(input, { target: { value: 'abc' } });
    rerender(<Harness resetKey={2} />);
    await waitFor(() => expect(input).toHaveValue(''));
    fireEvent.change(input, { target: { value: 'def' } });
    rerender(<Harness resetKey={2} open={false} />);
    rerender(<Harness resetKey={2} open />);
    await waitFor(() => expect(input).toHaveValue(''));
  });
});
