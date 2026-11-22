// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useMmrPendingCount } from '~/features/mmr-requests';
import { LeagueTabs } from '../LeagueTabs';
import type { LeagueType } from '../schemas';

vi.mock('../tabs/InfoTab', () => ({ InfoTab: () => null }));
vi.mock('../tabs/MatchesTab', () => ({ MatchesTab: () => null }));
vi.mock('../tabs/TournamentsTab', () => ({ TournamentsTab: () => null }));
vi.mock('../tabs/UsersTab', () => ({ UsersTab: () => null }));
vi.mock('~/features/mmr-requests', () => ({
  MmrRequestsTab: ({ scope }: { scope: { league: number } }) => (
    <div data-testid="mmr-requests-tab-stub">{scope.league}</div>
  ),
  useMmrPendingCount: vi.fn(),
}));

const LEAGUE = { pk: 5, name: 'Season 4' } as LeagueType;

beforeEach(() => {
  vi.mocked(useMmrPendingCount).mockReturnValue({
    data: { count: 2 },
  } as ReturnType<typeof useMmrPendingCount>);
});

function renderTabs(canReviewMmr: boolean, activeTab = 'info') {
  render(
    <LeagueTabs
      league={LEAGUE}
      tournaments={[]}
      activeTab={activeTab}
      onTabChange={vi.fn()}
      canViewMembers
      memberAccessSettled
      canReviewMmr={canReviewMmr}
    />,
  );
}

describe('LeagueTabs MMR requests tab', () => {
  it('shows the tab and pending count to league staff', () => {
    renderTabs(true);
    expect(screen.getByTestId('league-tab-mmr-requests')).toBeInTheDocument();
    expect(
      screen.getByTestId('league-tab-mmr-requests-count'),
    ).toHaveTextContent('2');
    expect(useMmrPendingCount).toHaveBeenCalledWith({ league: 5 }, true);
  });

  it('renders the queue in league scope when active', () => {
    renderTabs(true, 'mmr-requests');
    expect(screen.getByTestId('mmr-requests-tab-stub')).toHaveTextContent('5');
  });

  it('hides the tab from everyone else', () => {
    renderTabs(false, 'mmr-requests');
    expect(
      screen.queryByTestId('league-tab-mmr-requests'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('mmr-requests-tab-stub'),
    ).not.toBeInTheDocument();
    expect(useMmrPendingCount).toHaveBeenCalledWith({ league: 5 }, false);
  });
});
