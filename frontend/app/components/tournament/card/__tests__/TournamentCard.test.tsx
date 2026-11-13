// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { TournamentBucket, TournamentType } from '~/components/tournament/types';
import { useUserStore } from '~/store/userStore';
import { TournamentCard } from '../TournamentCard';

vi.mock('~/components/api/api', () => ({
  deleteTournament: vi.fn(),
}));

vi.mock('../TournamentEditModal', () => ({
  TournamentEditModal: () => null,
}));

vi.mock('~/store/userStore', async () => {
  const { create } = await import('zustand');
  return {
    useUserStore: create(() => ({
      currentUser: {},
      isStaff: () => false,
      delTournament: () => undefined,
    })),
  };
});

const LOGO = 'https://example.test/logo-a.png';
const OTHER_LOGO = 'https://example.test/logo-b.png';

function tournament(overrides: Partial<TournamentType> = {}): TournamentType {
  return {
    pk: 900,
    name: 'Discovery Cup',
    date_played: '2026-11-20T18:00:00Z',
    timezone: 'UTC',
    tournament_type: 'double_elimination',
    state: 'future',
    user_count: 4,
    league: {
      pk: 30,
      name: 'Discovery League',
      organization_name: 'Discovery Org',
      organization_id: 30,
      organization_logo: LOGO,
    },
    ...overrides,
  } as TournamentType;
}

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <TooltipProvider>{children}</TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

function renderCard(t: TournamentType, bucket?: TournamentBucket) {
  return render(<TournamentCard tournament={t} bucket={bucket} />, { wrapper: Wrapper });
}

function orgMedia(): HTMLElement {
  return screen.getByTestId('tournament-card-org-media');
}

describe('TournamentCard (non-staff)', () => {
  it('shows the org logo in an aria-hidden media box', () => {
    renderCard(tournament());
    expect(orgMedia()).toHaveAttribute('aria-hidden', 'true');
    const img = orgMedia().querySelector('img');
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute('alt', '');
    expect(screen.getByText('Discovery Org')).toBeInTheDocument();
  });

  it('swaps a broken logo for the Building2 box and keeps it across unrelated re-renders', () => {
    const { rerender } = renderCard(tournament());
    fireEvent.error(orgMedia().querySelector('img')!);
    expect(orgMedia().querySelector('img')).toBeNull();
    expect(orgMedia().querySelector('svg')).not.toBeNull();

    rerender(<TournamentCard tournament={tournament({ name: 'Renamed Cup' })} />);
    expect(screen.getByText('Renamed Cup')).toBeInTheDocument();
    expect(orgMedia().querySelector('img')).toBeNull();
    expect(orgMedia().querySelector('svg')).not.toBeNull();

    rerender(
      <TournamentCard
        tournament={tournament({
          name: 'Renamed Cup',
          league: {
            pk: 30,
            name: 'Discovery League',
            organization_name: 'Discovery Org',
            organization_id: 30,
            organization_logo: OTHER_LOGO,
          },
        })}
      />,
    );
    expect(orgMedia().querySelector('img')).not.toBeNull();
  });

  it('shows the org name and a centred fallback box when the org has no logo', () => {
    renderCard(
      tournament({
        league: {
          pk: 30,
          name: 'Discovery League',
          organization_name: 'Discovery Org',
          organization_id: 30,
          organization_logo: null,
        },
      }),
    );
    expect(orgMedia().querySelector('img')).toBeNull();
    expect(screen.getByText('Discovery Org')).toBeInTheDocument();
    const box = screen.getByTestId('tournament-card-org-fallback');
    expect(box).toHaveClass('size-full', 'flex', 'items-center', 'justify-center');
  });

  it('shows neutral "No organization" and "No league" without red when the league is null', () => {
    renderCard(tournament({ league: null }));
    const leagueCell = screen.getByTestId('tournament-cell-league');
    const orgCell = screen.getByTestId('tournament-cell-org');
    expect(within(orgCell).getByText('No organization')).toBeInTheDocument();
    expect(within(leagueCell).getByText('No league')).toBeInTheDocument();
    for (const cell of [leagueCell, orgCell]) {
      const all = [cell, ...Array.from(cell.querySelectorAll('*'))];
      for (const el of all) {
        expect(el.getAttribute('class') ?? '').not.toContain('red-500');
      }
    }
    expect(screen.getByTestId('tournament-card-org-fallback')).toHaveClass(
      'size-full',
      'flex',
      'items-center',
      'justify-center',
    );
  });

  it('labels a numeric league as League #N', () => {
    renderCard(tournament({ league: 7 }));
    expect(screen.getByText('League #7')).toBeInTheDocument();
  });

  it('shows the LIVE badge instead of the description for an in-progress upcoming row', () => {
    renderCard(tournament({ state: 'in_progress' }), 'upcoming');
    const badge = screen.getByTestId('tournament-live-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('Live');
    expect(screen.queryByText('Tournament')).toBeNull();
    expect(screen.getByTestId('tournament-card-state')).toHaveTextContent('Live');
  });

  it('shows a muted "Past (not closed)" for a future row in the archive', () => {
    renderCard(tournament({ state: 'future' }), 'archived');
    const state = screen.getByTestId('tournament-card-state');
    expect(state).toHaveTextContent('Past (not closed)');
    expect(state).toHaveClass('text-muted-foreground');
    expect(screen.queryByTestId('tournament-live-badge')).toBeNull();
  });

  it('shows "Past" for a closed tournament without a bucket', () => {
    renderCard(tournament({ state: 'past', date_played: '2025-01-01T18:00:00Z' }));
    expect(screen.getByTestId('tournament-card-state')).toHaveTextContent(/^Past$/);
  });
});

describe('TournamentCard (staff)', () => {
  it('renders the edit button with the brand toxic gradient', () => {
    useUserStore.setState({
      currentUser: { pk: 1, is_staff: true },
      isStaff: () => true,
    } as never);
    renderCard(tournament());
    const edit = screen.getByTestId('tournament-edit-button');
    expect(edit.className).toContain('from-violet-700');
    expect(edit.className).not.toContain('to-blue-500/20');
  });
});
