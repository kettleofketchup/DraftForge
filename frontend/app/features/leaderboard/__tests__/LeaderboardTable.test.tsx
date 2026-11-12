// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LeaderboardTable } from '../LeaderboardTable';
import type { LeaderboardEntry } from '../types';

vi.mock('~/components/user/UserPopover', () => ({
  UserPopover: ({ children }: { children: ReactNode }) => children,
}));

function entry(userId: number): LeaderboardEntry {
  return {
    user_id: userId,
    username: `player${userId}`,
    avatar: null,
    base_mmr: 3000,
    league_mmr: 3000,
    mmr_adjustment: 0,
    games_played: 10,
    win_rate: 0.5,
    avg_kills: 5,
    avg_deaths: 5,
    avg_assists: 5,
    avg_kda: 2,
    avg_gpm: 400,
    avg_xpm: 500,
  };
}

afterEach(cleanup);

describe('LeaderboardTable', () => {
  it('renders rankOffset + index + 1', () => {
    render(
      <LeaderboardTable
        entries={[entry(1), entry(2)]}
        sortBy="win_rate"
        order="desc"
        onSort={vi.fn()}
        rankOffset={20}
      />,
    );
    const rows = screen.getAllByRole('row');
    expect(rows[1].querySelector('td')?.textContent).toBe('21');
    expect(rows[2].querySelector('td')?.textContent).toBe('22');
  });

  it('clicking the League MMR header does not call onSort', () => {
    const onSort = vi.fn();
    render(
      <LeaderboardTable
        entries={[entry(1)]}
        sortBy="win_rate"
        order="desc"
        onSort={onSort}
        rankOffset={0}
      />,
    );
    fireEvent.click(screen.getByText('League MMR'));
    expect(onSort).not.toHaveBeenCalled();
  });
});
