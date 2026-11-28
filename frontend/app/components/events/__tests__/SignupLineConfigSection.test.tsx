// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { beforeAll, describe, expect, it } from 'vitest';
import { Form } from '~/components/ui/form';
import { SignupLineConfigSection } from '../SignupLineConfigSection';
import {
  SIGNUP_LINE_DEFAULTS,
  STAFF_REASON_POLICIES,
  STAFF_REASON_POLICY_LABELS,
  type SignupLineFields,
} from '../schemas';

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

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

  it('shows the default policy and saves the selected policy', async () => {
    let submitted: SignupLineFields | undefined;
    render(<Harness onValues={(v) => (submitted = v)} />);
    const select = screen.getByRole('combobox', { name: 'Staff reasons' });
    expect(select).toHaveTextContent('Optional');
    expect(select).toHaveAttribute(
      'data-testid',
      'signup-line-staff_reason_policy',
    );
    fireEvent.pointerDown(select, {
      button: 0,
      ctrlKey: false,
      pointerType: 'mouse',
    });
    for (const policy of STAFF_REASON_POLICIES) {
      expect(
        screen.getByTestId(`signup-line-staff_reason_policy-${policy}`),
      ).toHaveTextContent(STAFF_REASON_POLICY_LABELS[policy]);
    }
    fireEvent.click(
      screen.getByRole('option', { name: 'Required for placements' }),
    );
    expect(select).toHaveTextContent('Required for placements');
    fireEvent.click(screen.getByText('go'));
    await waitFor(() =>
      expect(submitted).toEqual({
        ...SIGNUP_LINE_DEFAULTS,
        staff_reason_policy: 'placements',
      }),
    );
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

  it('renders spot transfer unchecked by default', () => {
    render(<Harness />);
    const box = screen.getByTestId('signup-line-allow_spot_transfer');
    expect(box).not.toBeChecked();
    expect(screen.getByLabelText('Allow spot transfer')).toBe(box);
    expect(
      screen.getByText(
        'Members can give their place to another eligible member. If that member already has a place, the two swap.',
      ),
    ).toBeInTheDocument();
  });

  it('submits allow_spot_transfer as true once checked', async () => {
    let submitted: SignupLineFields | undefined;
    render(<Harness onValues={(v) => (submitted = v)} />);
    fireEvent.click(screen.getByTestId('signup-line-allow_spot_transfer'));
    fireEvent.click(screen.getByText('go'));
    await waitFor(() => expect(submitted).toBeDefined());
    expect(submitted).toEqual({
      ...SIGNUP_LINE_DEFAULTS,
      allow_spot_transfer: true,
    });
  });
});
