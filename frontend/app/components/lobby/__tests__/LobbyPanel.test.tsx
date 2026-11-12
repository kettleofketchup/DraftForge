// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import { useUserStore } from '~/store/userStore';
import type { UserType } from '~/index';
import { createGameLobby } from '../api';
import { LobbyPanelBody } from '../LobbyPanel';
import { GameLobbyResponseSchema, type GameLobbyResponse } from '../schemas';
import { privateLobby, publicLobby, players } from './fixtures';

// Uses @testing-library/react like ConfirmDialog.test.tsx: the panel holds
// mutation hooks and Radix dialogs, so it needs a real DOM. The mutations
// are never fired here, but keep axios off the network anyway.
vi.mock('~/components/lobby/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getGameLobby: vi.fn(),
    createGameLobby: vi.fn(),
    closeGameLobby: vi.fn(),
    inviteToGameLobby: vi.fn(),
    launchGameLobby: vi.fn(),
  };
});

// The real store fetches the signed-in user when it loads; the panel only
// reads `currentUser.pk`.
vi.mock('~/store/userStore', async () => {
  const { create } = await import('zustand');
  return { useUserStore: create(() => ({ currentUser: {} })) };
});

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <I18nextProvider i18n={createI18nInstance('en')}>
      <QueryClientProvider client={qc}>
        <TooltipProvider>{children}</TooltipProvider>
      </QueryClientProvider>
    </I18nextProvider>
  );
}

function response(overrides: Partial<Record<keyof GameLobbyResponse, unknown>>) {
  return GameLobbyResponseSchema.parse({
    game_id: 1,
    enabled: true,
    mode: 'manual',
    can_manage: false,
    is_player: false,
    lobby: publicLobby,
    ...overrides,
  });
}

function renderPanel(data: GameLobbyResponse) {
  return render(<LobbyPanelBody gameId={1} data={data} />, { wrapper: Wrapper });
}

const seated = players.map((p, i) => ({
  ...p,
  account_id: p.account_id ?? 1003,
  status: 'joined',
  seat: `${p.side}_${i + 1}`,
  ready: true,
}));

function endedLobby(state: string, extra: Record<string, unknown> = {}) {
  return { ...privateLobby, state, ended: true, password: null, ...extra };
}

describe('LobbyPanel', () => {
  afterEach(() => {
    useUserStore.setState({ currentUser: {} as UserType });
  });

  it('shows the state but no password or roster to other users', () => {
    renderPanel(response({}));
    expect(screen.getByTestId('lobby-state-badge')).toHaveTextContent('Waiting for players');
    expect(screen.queryByTestId('lobby-password')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lobby-players')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lobby-staff-controls')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lobby-invite-me')).not.toBeInTheDocument();
  });

  it('shows the password, roster and self-invite to a rostered player', () => {
    renderPanel(response({ is_player: true, lobby: privateLobby }));
    expect(screen.getByTestId('lobby-password')).toHaveTextContent('abcd2345efgh');
    expect(screen.getByTestId('lobby-name')).toHaveTextContent('Ravens vs Owls');
    expect(screen.getByTestId('lobby-player-1')).toHaveTextContent('Seated · Radiant 1 · Ready');
    expect(screen.getByTestId('lobby-player-2')).toHaveTextContent('Invited (2×)');
    expect(screen.getByTestId('lobby-player-3')).toHaveTextContent('No Steam account');
    expect(screen.getByTestId('lobby-invite-me')).toBeInTheDocument();
    // Re-invite buttons are staff-only.
    expect(screen.queryByTestId('lobby-reinvite-2')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lobby-staff-controls')).not.toBeInTheDocument();
  });

  it('gives staff invite, launch and close for a waiting lobby', () => {
    renderPanel(response({ can_manage: true, lobby: privateLobby }));
    expect(screen.getByTestId('lobby-invite-missing-btn')).toBeInTheDocument();
    expect(screen.getByTestId('lobby-launch-btn')).toBeInTheDocument();
    expect(screen.getByTestId('lobby-close-btn')).toBeInTheDocument();
    expect(screen.getByTestId('lobby-recreate-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('lobby-create-btn')).not.toBeInTheDocument();
    // Seated players need no invite; unlinked ones cannot get one.
    expect(screen.queryByTestId('lobby-reinvite-1')).not.toBeInTheDocument();
    expect(screen.getByTestId('lobby-reinvite-2')).toBeInTheDocument();
    expect(screen.queryByTestId('lobby-reinvite-3')).not.toBeInTheDocument();
  });

  it('offers staff a retry with the error after a failed lobby', () => {
    renderPanel(
      response({
        can_manage: true,
        lobby: {
          ...privateLobby,
          state: 'error',
          ended: true,
          password: null,
          last_error_code: 'league_not_held',
          last_error_detail: 'no bot holds league 17',
        },
        eligibility: { ok: true, code: null, details: {} },
      }),
    );
    expect(screen.getByTestId('lobby-error')).toHaveTextContent(/admin of this tournament's Dota league/);
    expect(screen.getByTestId('lobby-create-btn')).toHaveTextContent('Retry lobby');
    expect(screen.queryByTestId('lobby-close-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lobby-password')).not.toBeInTheDocument();
  });

  it('offers a retry after a played match when the backend allows it', () => {
    // The game's teams changed since that match, so the backend answers ok.
    renderPanel(
      response({
        can_manage: true,
        lobby: endedLobby('finished', { provisional_scored: true, match_id: '8000000001' }),
        eligibility: { ok: true, code: null, details: {} },
      }),
    );
    expect(screen.getByTestId('lobby-create-btn')).toHaveTextContent('Retry lobby');
    expect(screen.queryByTestId('lobby-replay-btn')).not.toBeInTheDocument();
  });

  it('explains why a played match gets no retry and offers a replay', () => {
    renderPanel(
      response({
        can_manage: true,
        lobby: endedLobby('finished', { provisional_scored: true }),
        eligibility: { ok: false, code: 'lobby_match_played', details: {} },
      }),
    );
    expect(screen.getByTestId('lobby-eligibility')).toHaveTextContent('Confirm the winner');
    expect(screen.queryByTestId('lobby-create-btn')).not.toBeInTheDocument();
    expect(screen.getByTestId('lobby-replay-btn')).toBeInTheDocument();
  });

  it('replays a played match only after confirming', async () => {
    vi.mocked(createGameLobby).mockResolvedValue(undefined);
    renderPanel(
      response({
        can_manage: true,
        lobby: endedLobby('finished', { provisional_scored: true }),
        eligibility: { ok: false, code: 'lobby_match_played', details: {} },
      }),
    );
    fireEvent.click(screen.getByTestId('lobby-replay-btn'));
    expect(createGameLobby).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId('lobby-replay-confirm'));
    await waitFor(() => expect(createGameLobby).toHaveBeenCalledWith(1, { replay: true }));
  });

  it.each([
    ['failed', {}],
    ['timed_out', {}],
    ['closed', {}],
    ['finished', { provisional_scored: false }],
  ])('offers a retry after a %s lobby without a played match', (state, extra) => {
    renderPanel(
      response({
        can_manage: true,
        lobby: endedLobby(state, extra),
        eligibility: { ok: true, code: null, details: {} },
      }),
    );
    expect(screen.getByTestId('lobby-create-btn')).toHaveTextContent('Retry lobby');
  });

  it('hides invite missing when every player is in the lobby', () => {
    renderPanel(
      response({ can_manage: true, lobby: { ...privateLobby, state: 'ready', players: seated } }),
    );
    expect(screen.queryByTestId('lobby-invite-missing-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lobby-reinvite-2')).not.toBeInTheDocument();
    expect(screen.getByTestId('lobby-launch-btn')).toBeInTheDocument();
  });

  it('hides invite missing when the only absentee has no Steam account', () => {
    const roster = seated.map((p) =>
      p.user_id === 3 ? { ...p, account_id: null, status: '', seat: null, ready: false } : p,
    );
    renderPanel(
      response({ can_manage: true, lobby: { ...privateLobby, players: roster } }),
    );
    expect(screen.queryByTestId('lobby-invite-missing-btn')).not.toBeInTheDocument();
  });

  it('does not offer a self-invite to a player already in the lobby', () => {
    useUserStore.setState({ currentUser: { pk: 1 } as UserType });
    renderPanel(response({ is_player: true, lobby: privateLobby }));
    expect(screen.queryByTestId('lobby-invite-me')).not.toBeInTheDocument();
  });

  it('offers a self-invite to a player who is not in the lobby', () => {
    useUserStore.setState({ currentUser: { pk: 2 } as UserType });
    renderPanel(response({ is_player: true, lobby: privateLobby }));
    expect(screen.getByTestId('lobby-invite-me')).toBeInTheDocument();
  });

  it('puts each name on its own line above the status', () => {
    const long = 'A very long display name that would not fit next to its status';
    const roster = players.map((p) => (p.user_id === 1 ? { ...p, name: long } : p));
    renderPanel(response({ is_player: true, lobby: { ...privateLobby, players: roster } }));
    const name = screen.getByTestId('lobby-player-name-1');
    expect(name).toHaveTextContent(long);
    expect(name.className).not.toMatch(/\btruncate\b/);
    expect(screen.getByTestId('lobby-player-status-1')).toHaveTextContent(
      'Seated · Radiant 1 · Ready',
    );
    expect(name.parentElement).toBe(screen.getByTestId('lobby-player-status-1').parentElement);
  });

  it('labels a pending player with a capitalised status', () => {
    const roster = players.map((p) => (p.user_id === 2 ? { ...p, status: 'pending' } : p));
    renderPanel(response({ is_player: true, lobby: { ...privateLobby, players: roster } }));
    expect(screen.getByTestId('lobby-player-status-2')).toHaveTextContent('Invite pending');
  });

  it('names the players without Steam before the first lobby', () => {
    renderPanel(
      response({
        can_manage: true,
        lobby: null,
        players,
        eligibility: {
          ok: false,
          code: 'missing_steam_ids',
          details: { user_ids: [3], players: [{ id: 3, name: 'Carol' }] },
        },
      }),
    );
    expect(screen.getByTestId('lobby-state-none')).toBeInTheDocument();
    expect(screen.getByTestId('lobby-missing-players')).toHaveTextContent('Carol');
    expect(screen.getByTestId('lobby-create-btn')).toHaveTextContent(
      'Create lobby without missing players',
    );
  });

  it('hides create when the game cannot get a lobby', () => {
    renderPanel(
      response({
        can_manage: true,
        lobby: null,
        eligibility: { ok: false, code: 'teams_missing', details: {} },
      }),
    );
    expect(screen.getByTestId('lobby-eligibility')).toHaveTextContent('Both teams must be set');
    expect(screen.queryByTestId('lobby-create-btn')).not.toBeInTheDocument();
  });

  it('shows the provisional result banner', () => {
    renderPanel(
      response({
        lobby: {
          ...publicLobby,
          state: 'post_game',
          match_id: '8000000001',
          provisional_winner_side: 'dire',
          provisional_winner_team_id: 11,
          provisional_scored: true,
        },
      }),
    );
    expect(screen.getByTestId('lobby-provisional-result')).toHaveTextContent(
      'Lobby reported: Owls (Dire) win, provisional',
    );
    expect(screen.getByTestId('lobby-match-id')).toHaveTextContent('8000000001');
  });

  it('reports an unscored match', () => {
    renderPanel(
      response({ lobby: { ...publicLobby, state: 'finished', ended: true, provisional_scored: false } }),
    );
    expect(screen.getByTestId('lobby-provisional-result')).toHaveTextContent(
      'without a scored result',
    );
  });
});
