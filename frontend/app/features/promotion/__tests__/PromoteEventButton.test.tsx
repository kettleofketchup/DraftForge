// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import { PromoteEventButton } from '../PromoteEventButton';

const promoter = { settled: true, canUsePromotion: true };

function renderButton(
  state: string,
  access: { settled: boolean; canUsePromotion: boolean },
): void {
  render(
    <MemoryRouter>
      <PromoteEventButton
        event={{ id: 9, organization: 4, state }}
        access={access}
      />
    </MemoryRouter>,
  );
}

describe('PromoteEventButton', () => {
  it('renders nothing before the access flags settle', () => {
    renderButton('upcoming', { settled: false, canUsePromotion: true });
    expect(screen.queryByTestId('event-promote-btn')).toBeNull();
  });

  it('renders nothing without promotion access (locked org admin or plain member)', () => {
    renderButton('upcoming', { settled: true, canUsePromotion: false });
    expect(screen.queryByTestId('event-promote-btn')).toBeNull();
  });

  it('renders nothing once the event is past signups', () => {
    renderButton('roll_call', promoter);
    expect(screen.queryByTestId('event-promote-btn')).toBeNull();
  });

  it('links a settled promoter to the org promotion tab for an upcoming event', () => {
    renderButton('upcoming', promoter);
    expect(screen.getByTestId('event-promote-btn')).toHaveAttribute(
      'href',
      '/organizations/4?tab=promotion&event=9',
    );
  });

  it('shows for an event with signups open', () => {
    renderButton('signups_open', promoter);
    expect(screen.getByTestId('event-promote-btn')).toBeInTheDocument();
  });
});
