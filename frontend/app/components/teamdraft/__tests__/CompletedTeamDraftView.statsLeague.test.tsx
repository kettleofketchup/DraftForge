// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { TeamType } from '~/components/tournament/types';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { CompletedTeamDraftView, TeamCard } from '../CompletedTeamDraftView';

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({
    showPlayerPopover: vi.fn(),
    hidePopover: vi.fn(),
    openPlayerModal: vi.fn(),
    openTeamModal: vi.fn(),
  }),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

const captain: UserType = { pk: 41, username: 'alice', nickname: 'Alice', mmr: 5000 } as UserType;
const member: UserType = { pk: 42, username: 'bob', nickname: 'Bob', mmr: 4200 } as UserType;

const team = {
  pk: 1,
  name: 'Team Alice',
  captain,
  members: [captain, member],
} as TeamType;

const summaries = {
  league_pk: 10,
  steam_league_id: 17938,
  min_games: 5,
  population: 84,
  players: {
    '42': {
      rank: 12,
      top_percent: 15,
      games: 14,
      wins: 8,
      losses: 6,
      win_rate: 0.5714,
      bucket: 5,
      recent: ['L', 'W', 'W', 'W', 'W'],
      streak: { result: 'W', count: 4 },
    },
  },
  distribution: {
    bucket_size: 10,
    buckets: Array.from({ length: 10 }, (_, i) => ({
      min: i * 10,
      max: (i + 1) * 10,
      count: i === 5 ? 1 : 0,
    })),
  },
};

function stubFetch() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () =>
      new Response(JSON.stringify(summaries), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
  );
}

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>,
  );
}

function memberRow(): HTMLElement {
  const row = screen.getAllByText('Bob')[0].closest('[class*="base-700"], [class*="slate-700"]');
  if (!row) throw new Error('member row not found');
  return row as HTMLElement;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('CompletedTeamDraftView league stats', () => {
  it('threads leaguePk down to the member UserStrip', async () => {
    const fetchSpy = stubFetch();
    wrap(<CompletedTeamDraftView teams={[team]} organizationId={1} leaguePk={10} />);
    expect(await screen.findAllByTestId('strip-league-stats')).toHaveLength(1);
    expect(String(fetchSpy.mock.calls[0][0])).toContain('/api/steam/leagues/10/player-summaries/');
  });

  it('renders no column and makes no request when leaguePk is null', async () => {
    const fetchSpy = stubFetch();
    wrap(<CompletedTeamDraftView teams={[team]} organizationId={1} leaguePk={null} />);
    await waitFor(() => expect(screen.getAllByText('Bob')[0]).toBeTruthy());
    expect(screen.queryByTestId('strip-league-stats')).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('member row uses base tokens, not slate', () => {
    stubFetch();
    wrap(<CompletedTeamDraftView teams={[team]} organizationId={1} leaguePk={null} />);
    const cls = memberRow().className;
    expect(cls).toContain('bg-base-700/30');
    expect(cls).not.toContain('slate');
  });

  it('TeamCard renders the column directly (TeamsTab path)', async () => {
    stubFetch();
    wrap(<TeamCard team={team} rank={1} organizationId={1} leaguePk={10} />);
    expect(await screen.findByTestId('strip-league-stats')).toBeTruthy();
  });
});
