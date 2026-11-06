// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import type { UserEntry } from '~/store/userCacheTypes';
import { UserStrip, userStripPropsAreEqual } from '../UserStrip';

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({
    showPlayerPopover: vi.fn(),
    hidePopover: vi.fn(),
    openPlayerModal: vi.fn(),
    openTeamModal: vi.fn(),
  }),
}));

const summaryCalls = vi.hoisted(() => ({ count: 0 }));
vi.mock('~/features/league-stats/queries', () => ({
  usePlayerLeagueSummary: () => {
    summaryCalls.count += 1;
    return {
      data: {
        summary: {
          rank: 1,
          top_percent: 10,
          games: 6,
          wins: 5,
          losses: 1,
          win_rate: 5 / 6,
          bucket: 8,
          recent: ['W', 'W', 'L', 'W', 'W', 'W'],
          streak: { result: 'W', count: 3 },
        },
        population: 10,
        minGames: 5,
      },
      isLoading: false,
      isError: false,
    };
  },
}));

const plainUser = {
  pk: 42,
  username: 'alice',
  nickname: 'Alice',
  mmr: 4200,
  league_mmr: 1500,
} as UserType & { league_mmr: number };

const entryUser: UserEntry = {
  pk: 43,
  username: 'bob',
  nickname: 'Bob',
  orgData: { 5: { id: 1, mmr: 3000, _fetchedAt: 0 } },
  leagueData: { 7: { id: 2, mmr: 1700, _fetchedAt: 0 } },
  _fetchedAt: 0,
};

function wrap(node: ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>
  );
}

function leagueBadgeText(container: HTMLElement): string | null {
  const label = Array.from(container.querySelectorAll('span')).find(
    (s) => s.textContent === 'L:',
  );
  return label?.parentElement?.textContent ?? null;
}

beforeEach(() => {
  summaryCalls.count = 0;
});

describe('UserStrip statsLeagueId', () => {
  it('does not re-render the stats column when the parent passes a new actionSlot', () => {
    const { rerender } = render(
      wrap(<UserStrip user={plainUser} statsLeagueId={1} actionSlot={<span>a</span>} />),
    );
    expect(screen.getByTestId('strip-league-stats')).toBeTruthy();
    const before = summaryCalls.count;
    expect(before).toBeGreaterThan(0);
    rerender(
      wrap(<UserStrip user={plainUser} statsLeagueId={1} actionSlot={<span>b</span>} />),
    );
    expect(screen.getByText('b')).toBeTruthy();
    expect(summaryCalls.count).toBe(before);
  });

  it('comparator returns false when statsLeagueId changes', () => {
    expect(
      userStripPropsAreEqual(
        { user: plainUser, statsLeagueId: 1 },
        { user: plainUser, statsLeagueId: 2 },
      ),
    ).toBe(false);
    expect(
      userStripPropsAreEqual(
        { user: plainUser, statsLeagueId: 1 },
        { user: plainUser, statsLeagueId: 1 },
      ),
    ).toBe(true);
  });

  it('L: badge output identical with and without statsLeagueId (UserType)', () => {
    const a = render(wrap(<UserStrip user={plainUser} />));
    const without = leagueBadgeText(a.container);
    a.unmount();
    const b = render(wrap(<UserStrip user={plainUser} statsLeagueId={7} />));
    expect(without).not.toBeNull();
    expect(leagueBadgeText(b.container)).toBe(without);
  });

  it('L: badge output identical with and without statsLeagueId (UserEntry)', () => {
    const a = render(wrap(<UserStrip user={entryUser} organizationId={5} leagueId={7} />));
    const without = leagueBadgeText(a.container);
    a.unmount();
    const b = render(
      wrap(
        <UserStrip user={entryUser} organizationId={5} leagueId={7} statsLeagueId={7} />,
      ),
    );
    expect(without).toContain('1,700');
    expect(leagueBadgeText(b.container)).toBe(without);
  });

  it('@container only with statsLeagueId', () => {
    const a = render(wrap(<UserStrip user={plainUser} data-testid="strip" />));
    expect(screen.getByTestId('strip').className).not.toContain('@container');
    a.unmount();
    render(wrap(<UserStrip user={plainUser} statsLeagueId={1} data-testid="strip" />));
    expect(screen.getByTestId('strip').className.split(' ')).toContain('@container');
  });

  it('name min-width narrows only with statsLeagueId', () => {
    const a = render(wrap(<UserStrip user={plainUser} />));
    const nameWithout = screen.getByText('Alice', { selector: '.hidden.sm\\:inline' })
      .parentElement!;
    expect(nameWithout.className).toContain('sm:min-w-[20ch]');
    a.unmount();
    render(wrap(<UserStrip user={plainUser} statsLeagueId={1} />));
    const nameWith = screen.getByText('Alice', { selector: '.hidden.sm\\:inline' })
      .parentElement!;
    expect(nameWith.className).toContain('sm:min-w-[12ch]');
    expect(nameWith.className).not.toContain('sm:min-w-[20ch]');
  });

  it('column renders with showMmr={false}', () => {
    render(wrap(<UserStrip user={plainUser} statsLeagueId={1} showMmr={false} />));
    expect(screen.getByTestId('strip-league-stats')).toBeTruthy();
  });

  it('no column without statsLeagueId', () => {
    render(wrap(<UserStrip user={plainUser} />));
    expect(screen.queryByTestId('strip-league-stats')).toBeNull();
  });
});
