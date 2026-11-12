// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { UserStripLeagueStats } from '../UserStripLeagueStats';

const actions = vi.hoisted(() => ({
  showPlayerPopover: vi.fn(),
  hidePopover: vi.fn(),
  scheduleHidePopover: vi.fn(),
  openPlayerModal: vi.fn(),
}));

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => actions,
}));

function player(pk: number): UserType {
  return { pk, username: `user${pk}`, nickname: `User ${pk}` } as UserType;
}

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

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

function renderStats(userId: number, leaguePk = 3, controlUserId?: number) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <div data-testid="subject">
          <UserStripLeagueStats leaguePk={leaguePk} player={player(userId)} />
        </div>
        {controlUserId != null && (
          <div data-testid="control">
            <UserStripLeagueStats leaguePk={3} player={player(controlUserId)} />
          </div>
        )}
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

async function expectSubjectEmptyAfterControlRenders() {
  await waitFor(() =>
    expect(
      screen.getByTestId('control').querySelector('[data-testid="strip-league-stats"]'),
    ).not.toBeNull(),
  );
  expect(screen.getByTestId('subject').childElementCount).toBe(0);
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
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
    expect(screen.getByRole('button').getAttribute('aria-label')).toBe(
      'League stats for User 42: Rank 12 of 84 (≥3 ticket games), 14 games, 57% win rate, last 5: L W W W W, oldest to newest, win streak 4. Opens the player panel',
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
    const trigger = screen.getByRole('button');
    expect(trigger.getAttribute('aria-label')).toBe(
      'League stats for User 43: Unranked: needs 3 ticket games (2 so far), 0% win rate, last 2: L L, oldest to newest. Opens the player panel',
    );
    expect(column.textContent).not.toContain('#');
    expect(column.textContent).toContain('2g');
    expect(screen.getByTestId('strip-league-stats-rank').textContent).toBe('');
    expect(screen.queryByTestId('streak-badge')).toBeNull();
  });

  it('renders nothing for a missing user', async () => {
    stubFetch(summaries);
    renderStats(999, 3, 42);
    await expectSubjectEmptyAfterControlRenders();
  });

  it('renders nothing for a 0-game user', async () => {
    stubFetch(summaries);
    renderStats(44, 3, 42);
    await expectSubjectEmptyAfterControlRenders();
  });

  it('leaguePk=0 never fetches and renders nothing', async () => {
    const fetchSpy = stubFetch(summaries);
    renderStats(42, 0, 42);
    await expectSubjectEmptyAfterControlRenders();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(String(fetchSpy.mock.calls[0][0])).toContain('/leagues/3/');
  });

  it('renders nothing while loading', () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      () => new Promise<Response>(() => {}),
    );
    renderStats(42);
    expect(screen.queryByTestId('strip-league-stats')).toBeNull();
  });

  it('renders nothing on error', async () => {
    stubFetch({ detail: 'boom' }, 500);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <UserStripLeagueStats leaguePk={3} player={player(42)} />
        </TooltipProvider>
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(client.getQueryState(['league-player-summaries', 3])?.status).toBe('error'),
    );
    expect(screen.queryByTestId('strip-league-stats')).toBeNull();
  });

  it('separators keep their surrounding spaces inside the flex badge', async () => {
    stubFetch(summaries);
    renderStats(42);
    const column = await screen.findByTestId('strip-league-stats');
    const seps = Array.from(column.querySelectorAll('span[aria-hidden]')).filter(
      (s) => s.textContent === ' · ',
    );
    expect(seps).toHaveLength(2);
    for (const sep of seps) expect(sep.className).toContain('whitespace-pre');
  });

  it('the badge opens the hover card and the panel for this league', async () => {
    stubFetch(summaries);
    renderStats(42);
    await screen.findByTestId('strip-league-stats');
    const trigger = screen.getByRole('button', { name: /^League stats for User 42: Rank 12 of 84/ });

    fireEvent.mouseEnter(trigger);
    expect(actions.showPlayerPopover).toHaveBeenCalledWith(
      expect.objectContaining({ pk: 42 }),
      trigger,
      { statsLeagueId: 3 },
    );

    fireEvent.click(trigger);
    expect(actions.openPlayerModal).toHaveBeenCalledWith(
      expect.objectContaining({ pk: 42 }),
      expect.objectContaining({ statsLeagueId: 3 }),
    );
  });

  it('mounts no tooltip of its own', async () => {
    stubFetch(summaries);
    renderStats(42);
    const column = await screen.findByTestId('strip-league-stats');
    fireEvent.pointerOver(column);
    fireEvent.mouseEnter(screen.getByRole('button'));
    expect(screen.queryByText('League ticket games')).toBeNull();
    expect(column.querySelector('[data-state]')).toBeNull();
  });
});
