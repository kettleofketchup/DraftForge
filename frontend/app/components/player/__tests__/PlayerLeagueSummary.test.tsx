// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { PlayerLeagueSummary } from '../PlayerLeagueSummary';

const logError = vi.hoisted(() => vi.fn());
vi.mock('~/lib/logger', () => ({
  getLogger: () => ({
    error: logError,
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  }),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

const LEAGUE_PK = 10;
const USER_ID = 42;

const buckets = Array.from({ length: 10 }, (_, i) => ({
  min: i * 10,
  max: (i + 1) * 10,
  count: i === 5 ? 3 : i === 4 ? 2 : 0,
}));

const rankedRow = {
  rank: 12,
  top_percent: 15,
  games: 14,
  wins: 8,
  losses: 6,
  win_rate: 0.5714,
  bucket: 5,
  recent: ['L', 'W', 'L', 'W', 'W', 'L', 'W', 'L', 'L', 'W', 'L', 'W'],
  streak: { result: 'W', count: 1 },
};

function summaries(
  players: Record<string, unknown>,
  overrides: Record<string, unknown> = {},
) {
  return {
    league_pk: LEAGUE_PK,
    steam_league_id: 17929,
    min_games: 5,
    population: 84,
    players,
    distribution: { bucket_size: 10, buckets },
    ...overrides,
  };
}

const leagueStats = {
  user_id: USER_ID,
  username: 'alice',
  avatar: null,
  base_mmr: 4000,
  league_mmr: 4100,
  league_id: 17929,
  games_played: 14,
  wins: 8,
  losses: 6,
  win_rate: 0.5714,
  avg_kills: 7.2,
  avg_deaths: 4.1,
  avg_assists: 11.5,
  avg_gpm: 512,
  avg_xpm: 601,
  mmr_adjustment: 0,
  last_updated: '2026-11-01T00:00:00Z',
};

type Reply = { status: number; body: unknown } | 'pending';

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function stubFetch(summaryReply: Reply, statsReply: Reply) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    const reply = url.includes('/player-summaries/') ? summaryReply : statsReply;
    if (reply === 'pending') return new Promise<Response>(() => {});
    return json(reply.status, reply.body);
  });
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <PlayerLeagueSummary leaguePk={LEAGUE_PK} userId={USER_ID} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  logError.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('PlayerLeagueSummary', () => {
  it('shows loading while either query is pending', async () => {
    stubFetch({ status: 200, body: summaries({ [USER_ID]: rankedRow }) }, 'pending');
    renderPanel();
    expect(screen.getByText('Loading stats...')).toBeTruthy();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByText('Loading stats...')).toBeTruthy();
    expect(screen.queryByTestId('player-league-summary')).toBeNull();
  });

  it('shows loading while the summary is pending', () => {
    stubFetch('pending', { status: 200, body: leagueStats });
    renderPanel();
    expect(screen.getByText('Loading stats...')).toBeTruthy();
  });

  it('shows "Couldn\'t load league stats" on a malformed summary body and logs', async () => {
    stubFetch({ status: 200, body: { nope: true } }, { status: 200, body: leagueStats });
    renderPanel();
    expect(await screen.findByText("Couldn't load league stats")).toBeTruthy();
    expect(screen.queryByText('No league stats available')).toBeNull();
    expect(logError).toHaveBeenCalled();
  });

  it('logs when the summaries request returns 500', async () => {
    stubFetch({ status: 500, body: {} }, { status: 200, body: leagueStats });
    renderPanel();
    expect(await screen.findByText("Couldn't load league stats")).toBeTruthy();
    await waitFor(() => expect(logError).toHaveBeenCalledTimes(1));
  });

  it('omits the averages line when by-league stats 404', async () => {
    stubFetch(
      { status: 200, body: summaries({ [USER_ID]: rankedRow }) },
      { status: 404, body: {} },
    );
    renderPanel();
    expect(await screen.findByTestId('player-league-summary')).toBeTruthy();
    expect(screen.queryByText(/KDA/)).toBeNull();
    expect(screen.queryByText('Averages unavailable')).toBeNull();
    expect(logError).not.toHaveBeenCalled();
  });

  it('shows "Averages unavailable" when by-league stats 500 and logs', async () => {
    stubFetch(
      { status: 200, body: summaries({ [USER_ID]: rankedRow }) },
      { status: 500, body: {} },
    );
    renderPanel();
    expect(await screen.findByText('Averages unavailable')).toBeTruthy();
    expect(screen.getByTestId('player-league-summary')).toBeTruthy();
    expect(screen.queryByText(/KDA/)).toBeNull();
    await waitFor(() => expect(logError).toHaveBeenCalledTimes(1));
  });

  it('shows the averages line when by-league stats load', async () => {
    stubFetch(
      { status: 200, body: summaries({ [USER_ID]: rankedRow }) },
      { status: 200, body: leagueStats },
    );
    renderPanel();
    expect(
      await screen.findByText('KDA 7.2 / 4.1 / 11.5 · GPM 512 · XPM 601'),
    ).toBeTruthy();
  });

  it('shows "No league stats available" with no row and by-league 404', async () => {
    stubFetch({ status: 200, body: summaries({}) }, { status: 404, body: {} });
    renderPanel();
    expect(await screen.findByText('No league stats available')).toBeTruthy();
    expect(screen.queryByTestId('player-league-summary')).toBeNull();
  });

  it('shows "No league stats available" with no row even when by-league is 200', async () => {
    stubFetch({ status: 200, body: summaries({}) }, { status: 200, body: leagueStats });
    renderPanel();
    expect(await screen.findByText('No league stats available')).toBeTruthy();
    expect(screen.queryByTestId('player-league-summary')).toBeNull();
    expect(screen.queryByTestId('win-rate-histogram')).toBeNull();
    expect(screen.queryByText(/KDA/)).toBeNull();
  });

  it('shows "No league stats available" with no row when by-league errors', async () => {
    stubFetch({ status: 200, body: summaries({}) }, { status: 500, body: {} });
    renderPanel();
    expect(await screen.findByText('No league stats available')).toBeTruthy();
    expect(screen.queryByText('Averages unavailable')).toBeNull();
  });

  it('renders ranked tiles, last 10 form and the highlighted histogram', async () => {
    stubFetch(
      { status: 200, body: summaries({ [USER_ID]: rankedRow }) },
      { status: 404, body: {} },
    );
    renderPanel();
    const panel = await screen.findByTestId('player-league-summary');
    expect(panel.textContent).toContain('#12 / 84');
    expect(screen.getByText('top 15%')).toBeTruthy();
    expect(screen.getByText('14')).toBeTruthy();
    expect(screen.getByText('57%')).toBeTruthy();
    expect(screen.getByText('8–6')).toBeTruthy();
    expect(screen.getByText('W1')).toBeTruthy();
    expect(screen.getByText('won last game')).toBeTruthy();
    expect(screen.getByText('last 10, oldest → newest')).toBeTruthy();
    const form = screen.getByTestId('recent-form');
    expect(form.querySelectorAll('[data-result]')).toHaveLength(10);
    const histogram = screen.getByTestId('win-rate-histogram');
    expect(histogram.querySelector('[data-highlighted="true"]')).toBeTruthy();
  });

  it('labels a losing streak', async () => {
    stubFetch(
      {
        status: 200,
        body: summaries({
          [USER_ID]: { ...rankedRow, streak: { result: 'L', count: 3 } },
        }),
      },
      { status: 404, body: {} },
    );
    renderPanel();
    expect(await screen.findByText('L3')).toBeTruthy();
    expect(screen.getByText('lost last 3')).toBeTruthy();
  });

  it('shows the denominator and games-to-rank when unranked in an empty population', async () => {
    stubFetch(
      {
        status: 200,
        body: summaries(
          {
            [USER_ID]: {
              rank: null,
              top_percent: null,
              games: 3,
              wins: 2,
              losses: 1,
              win_rate: 0.6667,
              bucket: null,
              recent: ['W', 'L', 'W'],
              streak: { result: 'W', count: 1 },
            },
          },
          {
            min_games: 5,
            population: 0,
            distribution: {
              bucket_size: 10,
              buckets: buckets.map((b) => ({ ...b, count: 0 })),
            },
          },
        ),
      },
      { status: 404, body: {} },
    );
    renderPanel();
    const panel = await screen.findByTestId('player-league-summary');
    expect(panel.textContent).toContain('— / 0');
    expect(screen.getByText('3/5 games to rank')).toBeTruthy();
    expect(screen.getByText('No ranked players yet')).toBeTruthy();
  });

  it('interpolates min games from the response', async () => {
    stubFetch(
      {
        status: 200,
        body: summaries(
          {
            [USER_ID]: {
              ...rankedRow,
              rank: null,
              top_percent: null,
              games: 2,
              bucket: null,
            },
          },
          { min_games: 3 },
        ),
      },
      { status: 404, body: {} },
    );
    renderPanel();
    expect(await screen.findByText('2/3 games to rank')).toBeTruthy();
    expect(screen.getByTestId('player-league-summary').textContent).toContain('— / 84');
  });
});
