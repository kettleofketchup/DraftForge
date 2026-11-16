// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { refreshActivityCredential } from '~/lib/activity-session';
import { useTournamentStore } from '~/store/tournamentStore';

const mocks = vi.hoisted(() => ({
  initializeDiscord: vi.fn(),
  get: vi.fn(),
}));

vi.mock('~/lib/discord', () => ({
  initializeDiscord: mocks.initializeDiscord,
  releaseDiscordSession: vi.fn(),
}));
vi.mock('~/components/api/axios', () => ({ default: { get: mocks.get } }));
vi.mock('~/lib/hydrateTournament', () => ({
  hydrateTournament: (data: unknown) => data,
}));
vi.mock('~/components/teamdraft/draftModal', () => ({
  DraftModal: () => <div data-testid="team-draft" />,
}));
vi.mock('~/components/herodraft/HeroDraftModal', () => ({
  HeroDraftModal: () => <div data-testid="hero-draft" />,
}));

import DraftActivity from '../activity';

beforeEach(() => {
  useTournamentStore.setState({ autoAdvance: false, live: false });
  mocks.get.mockResolvedValue({
    data: { pk: 5, draft: { pk: 9, draft_rounds: [] } },
  });
});
afterEach(() => vi.resetAllMocks());

describe('Discord Activity route', () => {
  it('follows the latest team draft pick like the live website view', async () => {
    mocks.initializeDiscord.mockResolvedValue({
      token: 't',
      kind: 'team',
      draft_id: 9,
      tournament_id: 5,
      user: { pk: 1 },
    });
    render(<DraftActivity />);
    await screen.findByTestId('team-draft');
    expect(useTournamentStore.getState().live).toBe(true);
    expect(useTournamentStore.getState().autoAdvance).toBe(true);
  });
  it('keeps the refresh throttle across re-handshakes', async () => {
    mocks.initializeDiscord.mockResolvedValue({
      token: 't',
      kind: 'team',
      draft_id: 9,
      tournament_id: 5,
      user: { pk: 1 },
    });
    render(<DraftActivity />);
    await screen.findByTestId('team-draft');
    await expect(refreshActivityCredential()).resolves.toBe(true);
    await waitFor(() =>
      expect(mocks.initializeDiscord).toHaveBeenCalledTimes(2),
    );
    await expect(refreshActivityCredential()).resolves.toBe(false);
    expect(mocks.initializeDiscord).toHaveBeenCalledTimes(2);
  });
});
