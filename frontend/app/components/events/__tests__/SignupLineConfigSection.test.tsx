// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { describe, expect, it } from 'vitest';
import { Form } from '~/components/ui/form';
import { SignupLineConfigSection } from '../SignupLineConfigSection';
import { SIGNUP_LINE_DEFAULTS, type SignupLineFields } from '../schemas';

function Harness({ onValues }: { onValues?: (v: SignupLineFields) => void }) {
  const form = useForm<SignupLineFields>({
    defaultValues: { ...SIGNUP_LINE_DEFAULTS },
  });
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit((v) => onValues?.(v))}>
        <SignupLineConfigSection control={form.control} />
        <button type="submit">go</button>
      </form>
    </Form>
  );
}

describe('SignupLineConfigSection', () => {
  it('renders both line rules with their descriptions', () => {
    render(<Harness />);
    expect(screen.getByText('Signup Line')).toBeInTheDocument();
    expect(
      screen.getByLabelText('Withdrawing gives up your place'),
    ).toBeChecked();
    expect(
      screen.getByText(
        'A member who withdraws, declines or is rejected and signs up again goes to the back of the line. When off, they get their old place back.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText('Switching Main/Maybe gives up your place'),
    ).toBeChecked();
    expect(
      screen.getByText(
        'Moving between Main and Maybe sends the signup to the back of the line. When off, it keeps its place.',
      ),
    ).toBeInTheDocument();
  });

  it('renders no form of its own', () => {
    render(<Harness />);
    const root = screen.getByTestId('signup-line-section');
    expect(root.querySelector('form')).toBeNull();
  });

  it.each(['line_withdraw_forfeits', 'line_switch_restamps'] as const)(
    'submits %s as false once unchecked',
    async (name) => {
      let submitted: SignupLineFields | undefined;
      render(<Harness onValues={(v) => (submitted = v)} />);
      fireEvent.click(screen.getByTestId(`signup-line-${name}`));
      fireEvent.click(screen.getByText('go'));
      await waitFor(() => expect(submitted).toBeDefined());
      expect(submitted).toEqual({ ...SIGNUP_LINE_DEFAULTS, [name]: false });
    },
  );
});
