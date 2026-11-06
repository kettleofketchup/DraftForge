// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { UserStripLeagueStats } from '../UserStripLeagueStats';

const buckets = Array.from({ length: 10 }, (_, i) => ({
  min: i * 10,
  max: (i + 1) * 10,
  count: i === 5 ? 1 : 0,
}));

const summaries = {
  league_pk: 3,
  steam_league_id: 17938,
  min_games: 3,
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
    '43': {
      rank: null,
      top_percent: null,
      games: 2,
      wins: 0,
      losses: 2,
      win_rate: 0,
      bucket: null,
      recent: ['L', 'L'],
      streak: { result: 'L', count: 2 },
    },
    '45': {
      rank: 80,
      top_percent: 96,
      games: 10,
      wins: 3,
      losses: 7,
      win_rate: 0.3,
      bucket: 3,
      recent: ['L', 'W', 'L', 'L', 'L'],
      streak: { result: 'L', count: 3 },
    },
    '44': {
      rank: null,
      top_percent: null,
      games: 0,
      wins: 0,
      losses: 0,
      win_rate: 0,
      bucket: null,
      recent: [],
      streak: null,
    },
  },
  distribution: { bucket_size: 10, buckets },
};

function stubFetch(body: unknown, status = 200) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
  );
}

function renderStats(userId: number) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <UserStripLeagueStats leaguePk={3} userId={userId} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('UserStripLeagueStats', () => {
  it('renders rank, games and pct', async () => {
    stubFetch(summaries);
    renderStats(42);
    const column = await screen.findByTestId('strip-league-stats');
    expect(column.textContent).toContain('#12');
    expect(column.textContent).toContain('14g');
    const pct = screen.getByText('57%');
    expect(pct.className).toContain('text-success');
    expect(column.getAttribute('aria-label')).toBe(
      'Rank 12 of 84 players with ≥3 ticket games in this league',
    );
    expect(screen.getByTestId('recent-form')).toBeTruthy();
    expect(screen.getByTestId('streak-badge').textContent).toBe('W4');
  });

  it('bad win rate uses the tinted chip, not small red text', async () => {
    stubFetch(summaries);
    renderStats(45);
    await screen.findByTestId('strip-league-stats');
    const pct = screen.getByText('30%');
    expect(pct.className).toContain('bg-destructive/25');
    expect(pct.className).toContain('text-foreground');
    expect(pct.className).toContain('font-semibold');
    expect(pct.className).not.toContain('text-destructive');
  });

  it('unranked shows empty rank span and copy with minGames=3', async () => {
    stubFetch(summaries);
    renderStats(43);
    const column = await screen.findByTestId('strip-league-stats');
    const label = column.getAttribute('aria-label') ?? '';
    expect(label).toBe('Needs 3 games to be ranked (2 so far)');
    expect(label).not.toContain('5');
    expect(column.textContent).not.toContain('#');
    expect(column.textContent).toContain('2g');
    expect(screen.getByTestId('strip-league-stats-rank').textContent).toBe('');
    expect(screen.queryByTestId('streak-badge')).toBeNull();
  });

  it('renders nothing for a missing user', async () => {
    const fetchSpy = stubFetch(summaries);
    renderStats(999);
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId('strip-league-stats')).toBeNull();
  });

  it('renders nothing for a 0-game user', async () => {
    const fetchSpy = stubFetch(summaries);
    renderStats(44);
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId('strip-league-stats')).toBeNull();
  });

  it('renders nothing while loading', () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      () => new Promise<Response>(() => {}),
    );
    renderStats(42);
    expect(screen.queryByTestId('strip-league-stats')).toBeNull();
  });

  it('renders nothing on error', async () => {
    const fetchSpy = stubFetch({ detail: 'boom' }, 500);
    renderStats(42);
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId('strip-league-stats')).toBeNull();
  });
});
