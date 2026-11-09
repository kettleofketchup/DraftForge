// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { TooltipProvider } from '~/components/ui/tooltip';
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

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
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

describe('LobbyPanel', () => {
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
    expect(screen.getByTestId('lobby-player-1')).toHaveTextContent('Seated (radiant_1), ready');
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
