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
vi.mock('~/features/mmr-requests', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/features/mmr-requests')>()),
  useMmrPendingCount: () => ({ data: undefined }),
}));

const league = { pk: 5, name: 'L', users_count: 9 } as LeagueType;

const renderTabs = () =>
  render(
    <LeagueTabs
      league={league}
      tournaments={[]}
      activeTab="info"
      onTabChange={vi.fn()}
      canViewMembers
      memberAccessSettled
      canManageLobbyBots={false}
      lobbyBotsAccessSettled
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

describe('LeagueTabs users count', () => {
  it('shows users_count before the member list is loaded', () => {
    renderTabs();
    expect(screen.getByTestId('league-tab-users').textContent).toBe(
      'Users (9)',
    );
  });

  it('shows the loaded member list length once loaded', () => {
    useLeagueStore.setState({
      leagueUserPks: [1, 2],
      leagueUsersLeagueId: 5,
    });
    renderTabs();
    expect(screen.getByTestId('league-tab-users').textContent).toBe(
      'Users (2)',
    );
  });
});
