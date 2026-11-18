// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { describe, expect, it } from 'vitest';
import type { z } from 'zod';
import { Form } from '~/components/ui/form';
import { SignupOpenSection } from '../SignupOpenSection';
import { SIGNUP_OPEN_DEFAULTS, type signupOpenSchema } from '../schemas';
// Radix radio measures itself with ResizeObserver, which jsdom lacks.
import './eventModalFixtures';

type Values = z.input<typeof signupOpenSchema>;

function Harness({
  initial = SIGNUP_OPEN_DEFAULTS,
  disabled,
  helpText,
  onValues,
}: {
  initial?: Values;
  disabled?: boolean;
  helpText?: string;
  onValues?: (v: Values) => void;
}) {
  const form = useForm<Values>({ defaultValues: { ...initial } });
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit((v) => onValues?.(v))}>
        <SignupOpenSection
          control={form.control}
          disabled={disabled}
          helpText={helpText}
        />
        <button type="submit">go</button>
      </form>
    </Form>
  );
}

describe('SignupOpenSection', () => {
  it('offers manual, immediate and scheduled', () => {
    render(<Harness />);
    expect(screen.getByLabelText('Open manually')).toBeChecked();
    expect(screen.getByLabelText('Open immediately')).toBeInTheDocument();
    expect(screen.getByLabelText('Open days before event')).toBeInTheDocument();
    expect(screen.queryByTestId('signup-open-days-input')).toBeNull();
  });

  it('shows stored hours as days', () => {
    render(
      <Harness
        initial={{
          signup_open_mode: 'scheduled',
          signups_open_hours_before: 72,
        }}
      />,
    );
    expect(screen.getByTestId('signup-open-days-input')).toHaveValue(3);
  });

  it('stores typed days as hours', async () => {
    let submitted: Values | undefined;
    render(<Harness onValues={(v) => (submitted = v)} />);
    fireEvent.click(screen.getByLabelText('Open days before event'));
    fireEvent.change(screen.getByTestId('signup-open-days-input'), {
      target: { value: '2' },
    });
    fireEvent.click(screen.getByText('go'));
    await waitFor(() =>
      expect(submitted).toEqual({
        signup_open_mode: 'scheduled',
        signups_open_hours_before: 48,
      }),
    );
  });

  it('accepts zero days (open at the start time)', async () => {
    let submitted: Values | undefined;
    render(
      <Harness
        initial={{
          signup_open_mode: 'scheduled',
          signups_open_hours_before: 72,
        }}
        onValues={(v) => (submitted = v)}
      />,
    );
    fireEvent.change(screen.getByTestId('signup-open-days-input'), {
      target: { value: '0' },
    });
    fireEvent.click(screen.getByText('go'));
    await waitFor(() => expect(submitted?.signups_open_hours_before).toBe(0));
  });

  it('renders the help text', () => {
    render(<Harness helpText="Series note" />);
    expect(screen.getByText('Series note')).toBeInTheDocument();
  });

  it('disables every control when disabled', () => {
    render(
      <Harness
        disabled
        initial={{
          signup_open_mode: 'scheduled',
          signups_open_hours_before: 24,
        }}
      />,
    );
    expect(screen.getByLabelText('Open manually')).toBeDisabled();
    expect(screen.getByTestId('signup-open-days-input')).toBeDisabled();
  });

  it('never renders the signup deadline', () => {
    render(
      <Harness
        initial={{
          signup_open_mode: 'scheduled',
          signups_open_hours_before: 24,
        }}
      />,
    );
    expect(screen.queryByText(/deadline/i)).toBeNull();
  });
});
