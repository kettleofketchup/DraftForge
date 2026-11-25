// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useBracketStore } from '~/store/bracketStore';
import type { BracketMatch } from '../../types';
import { MatchStatsModal } from '../MatchStatsModal';

const persistMutate = vi.fn();
const { useGameLobby } = vi.hoisted(() => ({
  useGameLobby: vi.fn((_gameId?: number, _enabled?: boolean) => ({
    data: undefined,
  })),
}));

// jsdom has no layout, so this checks the structure that keeps the dialog
// inside the viewport: a height-capped flex column whose header and close
// button sit outside the one scrolling body.

vi.mock('~/store/userStore', async () => {
  const { create } = await import('zustand');
  const store = create(() => ({
    currentUser: { pk: 1 },
    tournament: { pk: 7 },
  }));
  return { useUserStore: store };
});
vi.mock('~/store/bracketStore', async () => {
  const { create } = await import('zustand');
  const store = create(() => ({
    matches: [],
    isDirty: false,
    hasStructuralEdits: false,
    setMatchWinner: () => {},
    advanceWinner: () => {},
    unsetMatchWinner: () => {},
    holdResultForSave: () => {},
  }));
  return { useBracketStore: store };
});
vi.mock('~/hooks/useCanManageTournament', () => ({
  useCanManageCurrentTournament: () => true,
}));
vi.mock('~/hooks/useHeroDraft', () => ({
  useCreateHeroDraft: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useResetHeroDraft: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));
vi.mock('~/hooks/useBracket', () => ({
  usePersistMatchResult: () => ({ isPending: false, mutate: persistMutate }),
}));
vi.mock('~/hooks/useGameLobby', () => ({ useGameLobby }));
vi.mock('~/components/lobby/LobbyPanel', () => ({
  LobbyPanel: () => <div data-testid="lobby-panel" style={{ height: 2000 }} />,
}));
vi.mock('../DotaMatchStatsModal', () => ({ DotaMatchStatsModal: () => null }));
vi.mock('../LinkSteamMatchModal', () => ({ LinkSteamMatchModal: () => null }));

const team = (pk: number, name: string) =>
  ({
    pk,
    name,
    captain: { pk: pk * 10, username: name },
  }) as unknown as BracketMatch['radiantTeam'];

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
    render(<MatchStatsModal match={match} isOpen onClose={() => {}} />, {
      wrapper: Wrapper,
    });

    const dialog = screen.getByTestId('matchStatsModal');
    const classes = dialog.className.split(/\s+/);
    expect(classes).toContain('flex');
    expect(classes).toContain('flex-col');
    expect(classes).not.toContain('grid');
    expect(classes).toContain('overflow-hidden');
    expect(classes).toContain('max-h-[calc(100vh-2rem)]');
    expect(
      classes.some((c) =>
        c.startsWith(
          'supports-[height:100dvh]:max-h-[calc(100dvh-2rem-env(safe-area-inset-top)',
        ),
      ),
    ).toBe(true);

    const body = screen.getByTestId('matchStatsModal-body');
    expect(body.className).toMatch(/\boverflow-y-auto\b/);
    expect(body.className).toMatch(/\bmin-h-0\b/);
    expect(body.className).toMatch(/\bflex-1\b/);

    // Title and close stay outside the scroller, so they are always reachable.
    expect(body).not.toContainElement(
      screen.getByTestId('match-details-header'),
    );
    expect(body).not.toContainElement(
      screen.getByTestId('dialog-close-button'),
    );
    expect(dialog).toContainElement(screen.getByTestId('dialog-close-button'));

    // The tall lobby panel and the actions below it scroll with the body.
    expect(within(body).getByTestId('lobby-panel')).toBeInTheDocument();
    expect(
      within(body).getByTestId('link-steam-match-btn'),
    ).toBeInTheDocument();
  });
});

describe('MatchStatsModal match result persistence (issue #466)', () => {
  beforeEach(() => {
    persistMutate.mockReset();
    useBracketStore.setState({ isDirty: false, hasStructuralEdits: false });
  });

  it('persists the winner of a saved match straight away', () => {
    render(<MatchStatsModal match={match} isOpen onClose={() => {}} />, {
      wrapper: Wrapper,
    });

    fireEvent.click(screen.getByTestId('direWinsButton'));

    expect(persistMutate).toHaveBeenCalledWith({ gameId: 42, winner: 'dire' });
  });

  it('persists a winner while an earlier result is still saving', () => {
    useBracketStore.setState({ isDirty: true, hasStructuralEdits: false });
    render(<MatchStatsModal match={match} isOpen onClose={() => {}} />, {
      wrapper: Wrapper,
    });

    fireEvent.click(screen.getByTestId('radiantWinsButton'));

    expect(persistMutate).toHaveBeenCalledWith({
      gameId: 42,
      winner: 'radiant',
    });
  });

  it('leaves the winner for Save when the bracket has structural edits', () => {
    useBracketStore.setState({ isDirty: true, hasStructuralEdits: true });
    render(<MatchStatsModal match={match} isOpen onClose={() => {}} />, {
      wrapper: Wrapper,
    });

    fireEvent.click(screen.getByTestId('radiantWinsButton'));

    expect(persistMutate).not.toHaveBeenCalled();
  });

  it('leaves the winner for Save when the match has no game record yet', () => {
    render(
      <MatchStatsModal
        match={{ ...match, gameId: undefined }}
        isOpen
        onClose={() => {}}
      />,
      {
        wrapper: Wrapper,
      },
    );

    fireEvent.click(screen.getByTestId('radiantWinsButton'));

    expect(persistMutate).not.toHaveBeenCalled();
  });

  it('persists an unset of a completed match', () => {
    render(
      <MatchStatsModal
        match={{ ...match, status: 'completed', winner: 'radiant' }}
        isOpen
        onClose={() => {}}
      />,
      { wrapper: Wrapper },
    );

    fireEvent.click(screen.getByTestId('unsetWinnerButton'));

    expect(persistMutate).toHaveBeenCalledWith({ gameId: 42, winner: null });
  });
});

describe('MatchStatsModal embedded in the Activity', () => {
  const draftMatch: BracketMatch = {
    ...match,
    status: 'live',
    herodraft_id: 156,
  };

  beforeEach(() => {
    useGameLobby.mockClear();
  });

  it('opens an openable hero draft through onOpenHeroDraft', () => {
    const onOpenHeroDraft = vi.fn();
    render(
      <MatchStatsModal
        match={draftMatch}
        isOpen
        onClose={() => {}}
        embedded
        openableDraftIds={new Set([156])}
        onOpenHeroDraft={onOpenHeroDraft}
      />,
      { wrapper: Wrapper },
    );

    fireEvent.click(screen.getByTestId('view-draft-btn'));

    expect(onOpenHeroDraft).toHaveBeenCalledWith(156);
  });

  it('hides staff, lobby and draft-start controls', () => {
    render(
      <MatchStatsModal
        match={draftMatch}
        isOpen
        onClose={() => {}}
        embedded
        openableDraftIds={new Set([156])}
        onOpenHeroDraft={vi.fn()}
      />,
      { wrapper: Wrapper },
    );

    expect(screen.queryByTestId('reset-draft-btn')).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('link-steam-match-btn'),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('lobby-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('radiantWinsButton')).not.toBeInTheDocument();
    expect(useGameLobby).toHaveBeenCalled();
    expect(useGameLobby.mock.calls.every(([, enabled]) => !enabled)).toBe(true);
  });

  it('shows no open-draft or Start Draft button for a draft that is not openable', () => {
    render(
      <MatchStatsModal
        match={draftMatch}
        isOpen
        onClose={() => {}}
        embedded
        openableDraftIds={new Set([999])}
        onOpenHeroDraft={vi.fn()}
      />,
      { wrapper: Wrapper },
    );

    expect(screen.queryByTestId('view-draft-btn')).not.toBeInTheDocument();
    expect(screen.queryByText('Start Draft')).not.toBeInTheDocument();
  });

  it('never offers Start Draft for a match with no draft', () => {
    render(
      <MatchStatsModal
        match={match}
        isOpen
        onClose={() => {}}
        embedded
        openableDraftIds={new Set([156])}
        onOpenHeroDraft={vi.fn()}
      />,
      { wrapper: Wrapper },
    );

    expect(screen.queryByTestId('view-draft-btn')).not.toBeInTheDocument();
    expect(screen.queryByText('Start Draft')).not.toBeInTheDocument();
  });
});
