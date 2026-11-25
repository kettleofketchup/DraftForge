// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { SignupInLineSince } from '~/components/events/SignupInLineSince';
import type { EventSignupType } from '~/components/events/schemas';
import { TooltipProvider } from '~/components/ui/tooltip';

const ISO = '2026-11-25T19:42:00Z';

function signup(overrides: Partial<EventSignupType> = {}): EventSignupType {
  return {
    id: 7,
    status: 'waitlisted',
    signed_up_at: ISO,
    ...overrides,
  } as EventSignupType;
}

function renderLine(s: EventSignupType) {
  return render(
    <TooltipProvider>
      <SignupInLineSince signup={s} eventTimezone="UTC" />
    </TooltipProvider>,
  );
}

afterEach(cleanup);

describe('SignupInLineSince', () => {
  it('shows when a waitlisted signup joined the line', () => {
    renderLine(signup());
    const line = screen.getByTestId('signup-in-line-since-7');
    expect(line).toHaveTextContent(/in line since/i);
    expect(line.querySelector('time')).toHaveAttribute('dateTime', ISO);
    expect(line).toHaveTextContent('Nov 25');
  });

  it('renders nothing for a removed signup', () => {
    renderLine(signup({ status: 'cancelled' }));
    expect(screen.queryByTestId('signup-in-line-since-7')).toBeNull();
  });

  it.each([null, undefined])('renders nothing when signed_up_at is %s', (v) => {
    renderLine(signup({ signed_up_at: v as unknown as string | null }));
    expect(screen.queryByTestId('signup-in-line-since-7')).toBeNull();
  });
});
