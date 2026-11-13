// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LeaderboardPage } from '../LeaderboardPage';

vi.mock('~/components/user/UserPopover', () => ({
  UserPopover: ({ children }: { children: ReactNode }) => children,
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('LeaderboardPage', () => {
  it('requests the leaderboard sorted by win_rate by default', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ count: 0, next: null, previous: null, results: [] }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <LeaderboardPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    const url = String(fetchSpy.mock.calls[0][0]);
    expect(url).toContain('/api/steam/leaderboard/');
    expect(url).toContain('sort_by=win_rate');
    expect(url).not.toContain('league_mmr');
  });
});
