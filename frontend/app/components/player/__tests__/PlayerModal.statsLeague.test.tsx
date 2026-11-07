// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PlayerModalContext } from '~/components/ui/shared-popover-context';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { PlayerModal } from '../PlayerModal';

const modalCtx = vi.hoisted(() => ({ value: {} as PlayerModalContext }));
vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopover: () => ({
    playerModalState: { player: null, open: true, context: modalCtx.value },
  }),
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

const player = { pk: 42, username: 'alice', nickname: 'Alice' } as UserType;

const summaries = {
  league_pk: 10,
  steam_league_id: 17929,
  min_games: 5,
  population: 0,
  players: {},
  distribution: {
    bucket_size: 10,
    buckets: Array.from({ length: 10 }, (_, i) => ({
      min: i * 10,
      max: (i + 1) * 10,
      count: 0,
    })),
  },
};

function stubFetch() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    const body = url.includes('/player-summaries/') ? summaries : {};
    const status = url.includes('/player-summaries/') ? 200 : 404;
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  });
}

function renderModal(props: { leagueId?: number; organizationId?: number }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <PlayerModal player={player} open onOpenChange={vi.fn()} {...props} />
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('PlayerModal league stats context', () => {
  it('uses statsLeagueId over leagueId and sends ?league=', async () => {
    modalCtx.value = { leagueId: 2, statsLeagueId: 10, organizationId: 1 };
    const fetchSpy = stubFetch();
    renderModal({ leagueId: 2, organizationId: 1 });
    await screen.findByText('No league stats available');
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    const urls = fetchSpy.mock.calls.map(([input]) => String(input));
    expect(urls.some((u) => u.includes('/leagues/10/player-summaries/'))).toBe(true);
    expect(urls.some((u) => u.includes('league=10'))).toBe(true);
    expect(urls.some((u) => u.includes('league_id='))).toBe(false);
  });

  it('falls back to leagueId as a DraftForge pk', async () => {
    modalCtx.value = { leagueId: 2 };
    const fetchSpy = stubFetch();
    renderModal({ leagueId: 2 });
    await screen.findByText('No league stats available');
    const urls = fetchSpy.mock.calls.map(([input]) => String(input));
    expect(urls.some((u) => u.includes('/leagues/2/player-summaries/'))).toBe(true);
    expect(urls.some((u) => u.includes('league=2'))).toBe(true);
    expect(urls.some((u) => u.includes('league_id='))).toBe(false);
  });

  it('hides the org placeholder when statsLeagueId is set', async () => {
    modalCtx.value = { organizationId: 1, statsLeagueId: 10 };
    stubFetch();
    renderModal({ organizationId: 1 });
    await screen.findByText('No league stats available');
    expect(screen.queryByText('Organization stats coming soon')).toBeNull();
  });

  it('an explicit null statsLeagueId suppresses the leagueId fallback', () => {
    modalCtx.value = { leagueId: 2, statsLeagueId: null };
    const fetchSpy = stubFetch();
    renderModal({ leagueId: 2 });
    expect(screen.queryByText('League Stats')).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('keeps the org placeholder without any league context', () => {
    modalCtx.value = { organizationId: 1 };
    const fetchSpy = stubFetch();
    renderModal({ organizationId: 1 });
    expect(screen.getByText('Organization stats coming soon')).toBeTruthy();
    expect(screen.queryByText('League Stats')).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
