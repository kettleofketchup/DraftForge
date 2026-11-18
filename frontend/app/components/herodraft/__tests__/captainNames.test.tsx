// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('~/components/player', () => ({
  PlayerPopover: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

import { CompletedDraftView } from '~/components/herodraft/CompletedDraftView';
import { DraftTopBar } from '~/components/herodraft/DraftTopBar';
import { HeroDraftSchema } from '~/components/herodraft/schemas';
import type { HeroDraftTick } from '~/components/herodraft/types';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { useUserCacheStore } from '~/store/userCacheStore';

const captain = (pk: number) => ({
  pk,
  username: `user${pk}`,
  nickname: null,
  discordNickname: `Discord${pk}`,
  avatar: `hash${pk}`,
  discordId: `${pk}00`,
});
const team = (id: number, isRadiant: boolean) => ({
  id,
  tournament_team: 30 + id,
  captain: captain(id),
  team_name: `Team ${id}`,
  members: [],
  is_first_pick: isRadiant,
  is_radiant: isRadiant,
  reserve_time_remaining: 5_000,
  is_ready: true,
  is_connected: true,
});
const draft = HeroDraftSchema.parse({
  id: 2,
  game: 99,
  tournament_id: 8,
  state: 'drafting',
  roll_winner: null,
  draft_teams: [team(1, true), team(2, false)],
  rounds: [],
  current_round: 0,
  created_at: '2026-11-08T00:00:00Z',
  updated_at: '2026-11-08T00:00:00Z',
});
const tick: HeroDraftTick = {
  type: 'herodraft_tick',
  draft_state: 'drafting',
  server_time: '2026-11-08T12:00:00Z',
  current_round: 0,
  active_team_id: 1,
  round_started_at: '2026-11-08T11:59:00Z',
  round_grace_time_ms: 30_000,
  team_a_id: 1,
  team_a_reserve_ms: 5_000,
  team_b_id: 2,
  team_b_reserve_ms: 5_000,
  resuming_until: null,
};

beforeEach(() => useUserCacheStore.getState().reset());
afterEach(() => useHeroDraftStore.setState({ draft: null, tick: null }));

describe('hero draft captain names and avatars', () => {
  it('DraftTopBar keeps the Discord name from the captain payload', () => {
    useHeroDraftStore.setState({ draft, tick });
    render(<DraftTopBar draft={draft} tick={tick} />);
    expect(
      screen.getByTestId('herodraft-team-a-captain-name').textContent,
    ).toBe('Discord1');
  });

  it('CompletedDraftView loads the captain Discord avatar', () => {
    render(<CompletedDraftView draft={draft} />);
    const srcs = screen.getAllByRole('img').map((i) => i.getAttribute('src'));
    expect(srcs).toContain('https://cdn.discordapp.com/avatars/100/hash1');
    expect(srcs).toContain('https://cdn.discordapp.com/avatars/200/hash2');
    expect(screen.getByText('Discord1')).toBeInTheDocument();
  });
});
