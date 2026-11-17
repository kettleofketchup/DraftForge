// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MySignupActions } from '../MySignupActions';
import type { EventSignupType } from '../schemas';

function signup(status: string): EventSignupType {
  return { id: 7, user: 3, status } as unknown as EventSignupType;
}

function renderActions(
  mySignup: EventSignupType | undefined,
  overrides: Partial<Parameters<typeof MySignupActions>[0]> = {},
) {
  const props = {
    mySignup,
    signupsOpen: true,
    signupDisabled: false,
    cancelPending: false,
    onSignup: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  };
  render(<MySignupActions {...props} />);
  return props;
}

describe('MySignupActions', () => {
  it('shows the dropped notice with no Cancel or Tentative action', () => {
    renderActions(signup('dropped'));
    expect(screen.getByText('You were dropped from this event')).toBeTruthy();
    expect(screen.getByText('Dropped')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /cancel/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /tentative/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /sign up/i })).toBeNull();
  });

  it('shows the dropped notice after signups close', () => {
    renderActions(signup('dropped'), { signupsOpen: false });
    expect(screen.getByText('You were dropped from this event')).toBeTruthy();
  });

  it('still offers Cancel RSVP to an approved signup', () => {
    const props = renderActions(signup('approved'));
    fireEvent.click(screen.getByTestId('event-cancel-rsvp-btn'));
    expect(props.onCancel).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('You were dropped from this event')).toBeNull();
  });

  it('offers Sign Up and Tentative when not signed up', () => {
    const props = renderActions(undefined);
    fireEvent.click(screen.getByTestId('event-signup-btn'));
    fireEvent.click(screen.getByTestId('event-tentative-btn'));
    expect(props.onSignup).toHaveBeenNthCalledWith(1, 'rsvp');
    expect(props.onSignup).toHaveBeenNthCalledWith(2, 'tentative');
  });

  it('offers upgrade and Cancel to a tentative signup', () => {
    const props = renderActions(signup('tentative'));
    fireEvent.click(screen.getByTestId('event-upgrade-rsvp-btn'));
    fireEvent.click(screen.getByTestId('event-cancel-tentative-btn'));
    expect(props.onSignup).toHaveBeenCalledWith('rsvp');
    expect(props.onCancel).toHaveBeenCalledTimes(1);
  });

  it('renders no actions while signups are closed', () => {
    const { container } = render(
      <MySignupActions
        mySignup={signup('approved')}
        signupsOpen={false}
        signupDisabled={false}
        cancelPending={false}
        onSignup={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(container.textContent).toBe('');
  });
});
