// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { describe, expect, it } from 'vitest';
import type { z } from 'zod';
import { Form } from '~/components/ui/form';
import { SignupRulesSection } from '../SignupRulesSection';
import { SIGNUP_RULES_DEFAULTS, type signupRulesSchema } from '../schemas';

type Values = z.input<typeof signupRulesSchema>;

function Harness({ onValues }: { onValues?: (v: Values) => void }) {
  const form = useForm<Values>({ defaultValues: { ...SIGNUP_RULES_DEFAULTS } });
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit((v) => onValues?.(v))}>
        <SignupRulesSection control={form.control} />
        <button type="submit">go</button>
      </form>
    </Form>
  );
}

describe('SignupRulesSection', () => {
  it('renders the self sign-up control', () => {
    render(<Harness />);
    expect(
      screen.getByLabelText('Members can sign themselves up'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('When off, only organizers can add players.'),
    ).toBeInTheDocument();
  });

  it('leaves the roster rule to the ready check section', () => {
    render(<Harness />);
    expect(
      screen.queryByTestId('signup-rules-roll_call_enabled'),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('roll-call-mode-select')).toBeNull();
  });

  it('writes the flag to the form', async () => {
    let submitted: Values | undefined;
    render(<Harness onValues={(v) => (submitted = v)} />);
    fireEvent.click(screen.getByLabelText('Members can sign themselves up'));
    fireEvent.click(screen.getByText('go'));
    await screen.findByText('go');
    await new Promise((r) => setTimeout(r, 0));
    expect(submitted).toMatchObject({ allow_user_signups: false });
  });
});
