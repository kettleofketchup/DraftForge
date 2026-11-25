// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useLeagueStore } from '~/store/leagueStore';
import { LeagueTabs } from '../LeagueTabs';
import type { LeagueType } from '../schemas';

vi.mock('../tabs/InfoTab', () => ({ InfoTab: () => null }));
vi.mock('../tabs/MatchesTab', () => ({ MatchesTab: () => null }));
vi.mock('../tabs/TournamentsTab', () => ({ TournamentsTab: () => null }));
vi.mock('../tabs/UsersTab', () => ({ UsersTab: () => null }));
vi.mock('~/features/mmr-requests', () => ({
  MmrRequestsTab: () => null,
  useMmrPendingCount: () => ({ data: undefined }),
}));
vi.mock('../tabs/LobbyBotsTab', () => ({
  LobbyBotsTab: ({ enabled }: { enabled: boolean }) => (
    <div data-testid="lobby-bots-tab-stub" data-enabled={String(enabled)} />
  ),
}));

const league = { pk: 5, name: 'L', users_count: 9 } as LeagueType;

const renderTabs = (
  opts: {
    canViewMembers?: boolean;
    canManageLobbyBots?: boolean;
    lobbyBotsAccessSettled?: boolean;
    activeTab?: string;
  } = {},
) =>
  render(
    <LeagueTabs
      league={league}
      tournaments={[]}
      activeTab={opts.activeTab ?? 'info'}
      onTabChange={vi.fn()}
      canViewMembers={opts.canViewMembers ?? false}
      memberAccessSettled
      canManageLobbyBots={opts.canManageLobbyBots ?? false}
      lobbyBotsAccessSettled={opts.lobbyBotsAccessSettled ?? true}
    />,
  );

beforeEach(() => {
  useLeagueStore.setState({
    leagueUserPks: [],
    leagueUsersLoading: false,
    leagueUsersLeagueId: null,
  });
});

afterEach(cleanup);

describe('LeagueTabs lobby bots tab', () => {
  it('shows three tabs to the public', () => {
    renderTabs();
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.getByRole('tablist').className).toContain('grid-cols-3');
    expect(screen.queryByTestId('league-tab-lobby-bots')).toBeNull();
  });

  it('shows four tabs to a member viewer without bot access', () => {
    renderTabs({ canViewMembers: true });
    expect(screen.getAllByRole('tab')).toHaveLength(4);
    expect(screen.getByRole('tablist').className).toContain('grid-cols-4');
    expect(screen.queryByTestId('league-tab-lobby-bots')).toBeNull();
  });

  it('shows the Lobby bots tab to a league admin', () => {
    renderTabs({ canViewMembers: true, canManageLobbyBots: true });
    expect(screen.getAllByRole('tab')).toHaveLength(5);
    expect(screen.getByRole('tablist').className).toContain('grid-cols-5');
    expect(screen.getByTestId('league-tab-lobby-bots').textContent).toBe(
      'Lobby bots',
    );
  });

  it('renders the panel on the active lobby-bots tab', () => {
    renderTabs({
      canViewMembers: true,
      canManageLobbyBots: true,
      activeTab: 'lobby-bots',
    });
    expect(
      screen.getByTestId('lobby-bots-tab-stub').getAttribute('data-enabled'),
    ).toBe('true');
  });

  it('keeps the panel disabled until access settles', () => {
    renderTabs({
      canManageLobbyBots: true,
      lobbyBotsAccessSettled: false,
      activeTab: 'lobby-bots',
    });
    expect(
      screen.getByTestId('lobby-bots-tab-stub').getAttribute('data-enabled'),
    ).toBe('false');
  });
});
