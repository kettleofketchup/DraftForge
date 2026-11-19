// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useUserCacheStore } from '~/store/userCacheStore';

vi.mock('~/features/leaderboard/queries', () => ({
  useUserLeagueStats: () => ({ data: undefined, isLoading: false }),
}));

import { PlayerStatsTable } from '../PlayerStatsTable';
import { type MatchedPlayer, SteamMatchCard } from '../SteamMatchCard';

const goTo = (path: string) => window.history.pushState({}, '', path);

const player = (over: Partial<MatchedPlayer> = {}): MatchedPlayer => ({
  steam_id: 12345,
  user_id: 3,
  username: 'player_three',
  avatar: 'hash',
  hero_id: 1,
  player_slot: 0,
  is_radiant: true,
  is_captain: false,
  ...over,
});

const renderCard = (players: MatchedPlayer[]) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SteamMatchCard
        match={{
          match_id: 1,
          start_time: 0,
          duration: 1800,
          radiant_win: true,
          tier: 'all_players',
          tier_display: 'All players',
          player_overlap: players.length,
          radiant_captain: null,
          dire_captain: null,
          matched_players: players,
        }}
        onLink={() => {}}
        onViewDetails={() => {}}
        isCurrentlyLinked={false}
      />
    </QueryClientProvider>,
  );

beforeEach(() => useUserCacheStore.getState().reset());
afterEach(() => goTo('/'));

describe('SteamMatchCard player names and avatars', () => {
  it('builds the Discord avatar URL from the cached discordId', () => {
    useUserCacheStore
      .getState()
      .upsert({ pk: 3, username: 'player_three', discordId: '42' } as never);
    renderCard([player()]);
    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      'https://cdn.discordapp.com/avatars/42/hash',
    );
  });

  it('shows the org server nickname on an org page', () => {
    useUserCacheStore.getState().upsert(
      {
        pk: 3,
        username: 'player_three',
        guildNickname: 'Server Three',
      } as never,
      { orgId: 7 },
    );
    goTo('/organizations/7');
    renderCard([player()]);
    expect(screen.getByText('Server Three')).toBeInTheDocument();
  });

  it('falls back to the Steam id for an unlinked player', () => {
    renderCard([player({ user_id: null, username: null, avatar: null })]);
    expect(screen.getByText('Steam 12345')).toBeInTheDocument();
  });
});

describe('PlayerStatsTable player names', () => {
  it('shows the username, or Unknown without one', () => {
    const stats = {
      player_slot: 0,
      hero_id: 1,
      kills: 1,
      deaths: 2,
      assists: 3,
      gold_per_min: 400,
      xp_per_min: 500,
      last_hits: 100,
      denies: 5,
      hero_damage: 10000,
      tower_damage: 1000,
      hero_healing: 0,
    };
    render(
      <PlayerStatsTable
        team="radiant"
        isWinner
        players={[
          { ...stats, steam_id: 1, username: 'named' },
          { ...stats, steam_id: 2, username: null, player_slot: 1 },
        ]}
      />,
    );
    expect(screen.getByText('named')).toBeInTheDocument();
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });
});
