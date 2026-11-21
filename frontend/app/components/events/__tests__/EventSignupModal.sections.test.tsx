// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GAME_TYPE } from '~/components/game/constants';
import { EventSignupModal } from '../EventSignupModal';
import type { EventType } from '../schemas';
import { event, Wrapper } from './eventModalFixtures';

vi.mock('~/hooks/useEvent', () => ({
  useSignupMutation: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  }),
}));

function renderModal(
  overrides: Partial<EventType>,
  rankStatus?: 'active' | 'previous' | 'never',
) {
  render(
    <EventSignupModal
      event={{ ...event, ...overrides }}
      intent="rsvp"
      profile={rankStatus ? ({ rank_status: rankStatus } as never) : null}
      steamAccountId={null}
      open
      onOpenChange={() => {}}
    />,
    { wrapper: Wrapper },
  );
}

describe('EventSignupModal sections follow the event configuration', () => {
  it('shows only the friend ID entry on a Deadlock event', () => {
    renderModal({ game_type: GAME_TYPE.DEADLOCK, require_steam_id: true });

    expect(screen.getByTestId('signup-friend-id')).toBeInTheDocument();
    expect(screen.queryByTestId('signup-rank-status')).toBeNull();
    expect(screen.queryByTestId('position-choices')).toBeNull();
  });

  it('shows friend ID, rank status and positions on a Dota event', () => {
    renderModal({ game_type: GAME_TYPE.DOTA2, require_steam_id: true });

    expect(screen.getByTestId('signup-friend-id')).toBeInTheDocument();
    expect(screen.getByTestId('signup-rank-status')).toBeInTheDocument();
    expect(screen.getByTestId('position-choices')).toBeInTheDocument();
  });

  it('uses Steam copy without Dotabuff for the friend ID on a Deadlock event', () => {
    renderModal({ game_type: GAME_TYPE.DEADLOCK, require_steam_id: true });

    const input = screen.getByLabelText('Steam Friend ID');
    expect(input).toHaveAttribute('data-testid', 'signup-friend-id');
    expect(input.getAttribute('placeholder')).not.toMatch(/dotabuff/i);
    expect(screen.queryByText(/dota/i)).toBeNull();
  });

  it('keeps the Dotabuff hint for the friend ID on a Dota event', () => {
    renderModal({ game_type: GAME_TYPE.DOTA2, require_steam_id: true });

    const input = screen.getByLabelText('Dota 2 Friend ID');
    expect(input.getAttribute('placeholder')).toMatch(/dotabuff/i);
  });

  it('hides the friend ID entry when the event does not require it', () => {
    renderModal({ game_type: GAME_TYPE.DOTA2, require_steam_id: false });

    expect(screen.queryByTestId('signup-friend-id')).toBeNull();
    expect(screen.getByTestId('signup-rank-status')).toBeInTheDocument();
  });

  it.each([
    ['active', { discord_require_rank_screenshot: true }, 'MMR Screenshot'],
    [
      'previous',
      { discord_require_previous_rank_screenshot: true },
      'Last Ranked MMR Screenshot',
    ],
  ] as const)(
    'asks a %s rank for a screenshot when the event requires it',
    (rankStatus, flags, heading) => {
      renderModal({ game_type: GAME_TYPE.DOTA2, ...flags }, rankStatus);

      expect(
        screen.getByRole('heading', {
          name: new RegExp(`\\d+\\. ${heading}$`),
        }),
      ).toBeInTheDocument();
    },
  );

  it.each([
    ['active', { discord_require_previous_rank_screenshot: true }],
    ['previous', { discord_require_rank_screenshot: true }],
  ] as const)(
    "does not ask a %s rank for a screenshot under the other rank type's setting",
    (rankStatus, flags) => {
      renderModal({ game_type: GAME_TYPE.DOTA2, ...flags }, rankStatus);

      expect(screen.queryByRole('heading', { name: /Screenshot/ })).toBeNull();
    },
  );
});
