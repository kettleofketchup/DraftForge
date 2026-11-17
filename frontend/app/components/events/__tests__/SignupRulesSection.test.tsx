// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { describe, expect, it } from 'vitest';
import type { z } from 'zod';
import { Form } from '~/components/ui/form';
import { SignupRulesSection } from '../SignupRulesSection';
import { SIGNUP_RULES_DEFAULTS, type signupRulesSchema } from '../schemas';

type Values = z.input<typeof signupRulesSchema>;

function Harness({
  modes,
  onValues,
}: {
  modes?: readonly string[];
  onValues?: (v: Values) => void;
}) {
  const form = useForm<Values>({ defaultValues: { ...SIGNUP_RULES_DEFAULTS } });
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit((v) => onValues?.(v))}>
        <SignupRulesSection control={form.control} modes={modes} />
        <button type="submit">go</button>
      </form>
    </Form>
  );
}

describe('SignupRulesSection', () => {
  it('renders the roster and self sign-up controls', () => {
    render(<Harness />);
    expect(
      screen.getByLabelText('Players join the roster only after confirming'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Approved players wait for roll-call confirmation before they are added to the tournament.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText('Members can sign themselves up'),
    ).toBeInTheDocument();
  });

  it('hides the roll-call mode select with the default single mode', () => {
    render(<Harness />);
    expect(screen.queryByTestId('roll-call-mode-select')).toBeNull();
  });

  it('shows the roll-call mode select when more than one mode is offered', () => {
    render(<Harness modes={['manual', 'auto']} />);
    expect(screen.getByTestId('roll-call-mode-select')).toBeInTheDocument();
  });

  it('writes both flags to the form', async () => {
    let submitted: Values | undefined;
    render(<Harness onValues={(v) => (submitted = v)} />);
    fireEvent.click(
      screen.getByLabelText('Players join the roster only after confirming'),
    );
    fireEvent.click(screen.getByLabelText('Members can sign themselves up'));
    fireEvent.click(screen.getByText('go'));
    await screen.findByText('go');
    await new Promise((r) => setTimeout(r, 0));
    expect(submitted).toMatchObject({
      roll_call_enabled: true,
      allow_user_signups: false,
    });
  });
});
