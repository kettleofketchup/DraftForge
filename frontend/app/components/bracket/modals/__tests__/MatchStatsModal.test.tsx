// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { BracketMatch } from '../../types';
import { MatchStatsModal } from '../MatchStatsModal';

// jsdom has no layout, so this checks the structure that keeps the dialog
// inside the viewport: a height-capped flex column whose header and close
// button sit outside the one scrolling body.

vi.mock('~/store/userStore', async () => {
  const { create } = await import('zustand');
  const store = create(() => ({
    currentUser: { pk: 1 },
    tournament: { pk: 7 },
    isStaff: () => true,
  }));
  return { useUserStore: store };
});
vi.mock('~/store/bracketStore', async () => {
  const { create } = await import('zustand');
  const store = create(() => ({
    matches: [],
    setMatchWinner: () => {},
    advanceWinner: () => {},
    unsetMatchWinner: () => {},
  }));
  return { useBracketStore: store };
});
vi.mock('~/components/organization', () => ({
  useOrganization: () => ({ organization: undefined }),
}));
vi.mock('~/hooks/usePermissions', () => ({ useIsLeagueStaff: () => true }));
vi.mock('~/hooks/useHeroDraft', () => ({
  useCreateHeroDraft: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useResetHeroDraft: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));
vi.mock('~/hooks/useGameLobby', () => ({ useGameLobby: () => ({ data: undefined }) }));
vi.mock('~/components/lobby/LobbyPanel', () => ({
  LobbyPanel: () => <div data-testid="lobby-panel" style={{ height: 2000 }} />,
}));
vi.mock('../DotaMatchStatsModal', () => ({ DotaMatchStatsModal: () => null }));
vi.mock('../LinkSteamMatchModal', () => ({ LinkSteamMatchModal: () => null }));

const team = (pk: number, name: string) =>
  ({ pk, name, captain: { pk: pk * 10, username: name } }) as unknown as BracketMatch['radiantTeam'];

const match: BracketMatch = {
  id: 'w-2-0',
  gameId: 42,
  round: 2,
  position: 0,
  bracketType: 'winners',
  eliminationType: 'double',
  radiantTeam: team(1, 'Ember Lynx'),
  direTeam: team(2, 'Cinder'),
  status: 'pending',
};

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient();
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe('MatchStatsModal layout', () => {
  it('caps the dialog at the viewport and scrolls only the body', () => {
    render(<MatchStatsModal match={match} isOpen onClose={() => {}} />, { wrapper: Wrapper });

    const dialog = screen.getByTestId('matchStatsModal');
    const classes = dialog.className.split(/\s+/);
    expect(classes).toContain('flex');
    expect(classes).toContain('flex-col');
    expect(classes).not.toContain('grid');
    expect(classes).toContain('overflow-hidden');
    expect(classes).toContain('max-h-[calc(100vh-2rem)]');
    expect(
      classes.some((c) => c.startsWith('supports-[height:100dvh]:max-h-[calc(100dvh-2rem-env(safe-area-inset-top)')),
    ).toBe(true);

    const body = screen.getByTestId('matchStatsModal-body');
    expect(body.className).toMatch(/\boverflow-y-auto\b/);
    expect(body.className).toMatch(/\bmin-h-0\b/);
    expect(body.className).toMatch(/\bflex-1\b/);

    // Title and close stay outside the scroller, so they are always reachable.
    expect(body).not.toContainElement(screen.getByTestId('match-details-header'));
    expect(body).not.toContainElement(screen.getByTestId('dialog-close-button'));
    expect(dialog).toContainElement(screen.getByTestId('dialog-close-button'));

    // The tall lobby panel and the actions below it scroll with the body.
    expect(within(body).getByTestId('lobby-panel')).toBeInTheDocument();
    expect(within(body).getByTestId('link-steam-match-btn')).toBeInTheDocument();
  });
});
