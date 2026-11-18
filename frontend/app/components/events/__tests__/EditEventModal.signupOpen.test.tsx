// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventType } from '../schemas';
import { event, submit, Wrapper } from './eventModalFixtures';

const mutateAsync = vi.hoisted(() => vi.fn());

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  fetchCurrentUser: vi.fn().mockResolvedValue({}),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getLeagues: vi.fn().mockResolvedValue([]),
}));

vi.mock('~/hooks/useEvent', () => ({
  useUpdateEventMutation: () => ({ mutateAsync, isPending: false }),
}));

vi.mock('~/hooks/useLobbyPassword', () => ({
  useEventLobbyPassword: () => ({ data: undefined }),
  useRegenerateEventLobbyPassword: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import { EditEventModal } from '../EditEventModal';

const upcoming: EventType = {
  ...event,
  state: 'upcoming',
  signup_open_mode: 'scheduled',
  signups_open_hours_before: 48,
  signups_open_at: '2026-11-29T19:00:00Z',
};

function renderModal(e: EventType) {
  render(<EditEventModal event={e} open onOpenChange={() => {}} />, {
    wrapper: Wrapper,
  });
}

beforeEach(() => {
  mutateAsync.mockReset();
  mutateAsync.mockResolvedValue({});
});

describe('EditEventModal signup open policy', () => {
  it('loads the policy and sends edits while upcoming', async () => {
    renderModal(upcoming);
    expect(screen.getByTestId('signup-open-days-input')).toHaveValue(2);
    fireEvent.change(screen.getByTestId('signup-open-days-input'), {
      target: { value: '3' },
    });
    submit();
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      signup_open_mode: 'scheduled',
      signups_open_hours_before: 72,
    });
  });

  it('shows the computed open time read-only', () => {
    renderModal(upcoming);
    expect(screen.getByTestId('signup-open-at')).not.toHaveTextContent(
      /not scheduled/i,
    );
    expect(screen.getByTestId('signup-open-at').tagName).not.toBe('INPUT');
  });

  it('says when no open time is scheduled', () => {
    renderModal({
      ...upcoming,
      signup_open_mode: 'manual',
      signups_open_at: null,
    });
    expect(screen.getByTestId('signup-open-at')).toHaveTextContent(
      /not scheduled/i,
    );
  });

  it('locks the policy and leaves it out of the payload once signups opened', async () => {
    renderModal({ ...upcoming, state: 'signups_open' });
    expect(screen.getByLabelText('Open manually')).toBeDisabled();
    submit();
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const body = mutateAsync.mock.calls[0][0];
    expect(body).not.toHaveProperty('signup_open_mode');
    expect(body).not.toHaveProperty('signups_open_hours_before');
  });

  it('explains the series cascade for a series event', () => {
    renderModal({ ...upcoming, event_repeater: 7, event_repeater_name: 'S' });
    expect(screen.getByText(/series policy recalculates/i)).toBeInTheDocument();
  });

  it('never renders the signup deadline', () => {
    renderModal(upcoming);
    expect(screen.queryByText(/deadline/i)).toBeNull();
  });
});
