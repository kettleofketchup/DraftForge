// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router';
import { toast } from 'sonner';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { updateTournament } from '~/components/api/api';
import { Dialog } from '~/components/ui/dialog';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import { useUserStore } from '~/store/userStore';
import type { TournamentClassType } from '../types';
import { TournamentEditForm } from './editForm';

vi.mock('~/components/api/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('~/components/api/api')>();
  return { ...actual, updateTournament: vi.fn(), createTournament: vi.fn() };
});

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock('~/store/userStore', async () => {
  const { create } = await import('zustand');
  return {
    useUserStore: create(() => ({
      currentUser: {},
      leagues: [],
      leaguesOrgId: 'all',
      getLeagues: () => Promise.resolve(),
      getTournaments: () => Promise.resolve(),
    })),
  };
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <I18nextProvider i18n={createI18nInstance('en')}>
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <MemoryRouter>
            <Dialog>{children}</Dialog>
          </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </I18nextProvider>
  );
}

const siteStaff = { pk: 1, is_staff: true, is_superuser: false };

function setUser(user: Record<string, unknown>, leagues: unknown[] = []) {
  useUserStore.setState({
    currentUser: user,
    leagues,
    leaguesOrgId: 'all',
  } as unknown as Parameters<typeof useUserStore.setState>[0]);
}

function tournament(
  overrides: Record<string, unknown> = {},
): TournamentClassType {
  return {
    pk: 5,
    name: 'Cup',
    date_played: '2026-12-01T19:00:00',
    timezone: 'America/New_York',
    state: 'future',
    tournament_type: 'double_elimination',
    league: {
      pk: 9,
      name: 'L9',
      organization_name: 'Org8',
      organization: { pk: 8 },
    },
    source_event: null,
    auto_create_hero_drafts: false,
    discord_send_draft_link: false,
    discord_send_herodraft_link: false,
    dota_lobby_mode: 'off',
    dota_lobby_launch: 'manual',
    dota_lobby_region: '',
    discord_send_lobby_info: false,
    game_type: 1,
    game_mode: 'normal',
    lobby_steam_league_id: null,
    captains_draft_time: 10,
    custom_game_name: '',
    ...overrides,
  } as unknown as TournamentClassType;
}

const submit = () => fireEvent.submit(screen.getByTestId('tournament-form'));
const tabState = (tab: string) =>
  screen.getByTestId(`tournament-form-tab-${tab}`).getAttribute('data-state');

describe('TournamentEditForm', () => {
  afterEach(() => {
    vi.mocked(updateTournament).mockReset();
    vi.mocked(toast.error).mockReset();
  });

  it('locks a league the user cannot admin and sends it unchanged', async () => {
    setUser({ pk: 2, staff_league_ids: [9] }, [
      {
        pk: 31,
        name: 'Other',
        organization_name: 'OrgB',
        organization: { pk: 30 },
      },
    ]);
    vi.mocked(updateTournament).mockResolvedValue({} as never);
    render(<TournamentEditForm tourn={tournament()} canEdit />, {
      wrapper: Wrapper,
    });

    const trigger = screen.getByTestId('tournament-league-select');
    expect(trigger).toHaveTextContent('L9');
    expect(trigger).toBeDisabled();

    submit();
    await waitFor(() => expect(updateTournament).toHaveBeenCalled());
    const payload = vi.mocked(updateTournament).mock.calls[0][1] as Record<
      string,
      unknown
    >;
    expect(payload.league_id_write).toBe(9);
    expect(payload.game_mode).toBe('normal');
    expect(payload).not.toHaveProperty('captains_draft_time');
    expect(payload).not.toHaveProperty('game_type');
  });

  it('saves when a hidden draft time is invalid outside Captains Mode', async () => {
    setUser(siteStaff);
    vi.mocked(updateTournament).mockResolvedValue({} as never);
    render(
      <TournamentEditForm
        tourn={tournament({ captains_draft_time: 0 })}
        canEdit
      />,
      {
        wrapper: Wrapper,
      },
    );

    submit();
    await waitFor(() => expect(updateTournament).toHaveBeenCalled());
    const payload = vi.mocked(updateTournament).mock.calls[0][1] as Record<
      string,
      unknown
    >;
    expect(payload).not.toHaveProperty('captains_draft_time');
  });

  it('sends the draft time in Captains Mode', async () => {
    setUser(siteStaff);
    vi.mocked(updateTournament).mockResolvedValue({} as never);
    render(
      <TournamentEditForm
        tourn={tournament({
          game_mode: 'captains_mode',
          captains_draft_time: 25,
        })}
        canEdit
      />,
      { wrapper: Wrapper },
    );

    submit();
    await waitFor(() => expect(updateTournament).toHaveBeenCalled());
    const payload = vi.mocked(updateTournament).mock.calls[0][1] as Record<
      string,
      unknown
    >;
    expect(payload.captains_draft_time).toBe(25);
  });

  it('shows a server error on a visible field in another tab', async () => {
    setUser(siteStaff);
    vi.mocked(updateTournament).mockRejectedValue({
      response: { data: { captains_draft_time: ['bad'] } },
    });
    render(
      <TournamentEditForm
        tourn={tournament({ game_mode: 'captains_mode' })}
        canEdit
      />,
      {
        wrapper: Wrapper,
      },
    );
    expect(tabState('general')).toBe('active');

    submit();
    await waitFor(() => expect(tabState('config')).toBe('active'));
    expect(await screen.findByText('bad')).toBeInTheDocument();
  });

  it('toasts a server error on a hidden field', async () => {
    setUser(siteStaff);
    vi.mocked(updateTournament).mockRejectedValue({
      response: { data: { captains_draft_time: ['bad'] } },
    });
    render(<TournamentEditForm tourn={tournament()} canEdit />, {
      wrapper: Wrapper,
    });

    submit();
    await waitFor(() => expect(tabState('config')).toBe('active'));
    expect(toast.error).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ description: expect.stringContaining('bad') }),
    );
  });

  it('jumps to the tab of a client-side invalid field', async () => {
    setUser(siteStaff);
    render(
      <TournamentEditForm
        tourn={tournament({
          game_mode: 'captains_mode',
          captains_draft_time: 0,
        })}
        canEdit
      />,
      { wrapper: Wrapper },
    );

    submit();
    await waitFor(() => expect(tabState('config')).toBe('active'));
    expect(toast.error).toHaveBeenCalled();
    expect(updateTournament).not.toHaveBeenCalled();
  });

  it('blocks editing without permission', () => {
    setUser(siteStaff);
    render(<TournamentEditForm tourn={tournament()} canEdit={false} />, {
      wrapper: Wrapper,
    });
    expect(screen.getByText(/You do not have permission/)).toBeInTheDocument();
  });

  it('blocks create for a superuser who is not staff', () => {
    setUser({ pk: 3, is_staff: false, is_superuser: true });
    render(<TournamentEditForm tourn={{} as TournamentClassType} />, {
      wrapper: Wrapper,
    });
    expect(screen.getByText(/You do not have permission/)).toBeInTheDocument();
  });

  it('allows create for site staff', () => {
    setUser(siteStaff);
    render(<TournamentEditForm tourn={{} as TournamentClassType} />, {
      wrapper: Wrapper,
    });
    expect(screen.getByTestId('tournament-form')).toBeInTheDocument();
  });
});
