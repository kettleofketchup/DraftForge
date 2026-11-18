// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Handler = (msg: unknown) => void;
const handlers: Handler[] = [];
vi.mock('~/lib/websocket', () => ({
  getWebSocketManager: () => ({
    connect: () => 'conn-1',
    subscribe: (_id: string, h: Handler) => {
      handlers.push(h);
      return () => {};
    },
    send: () => true,
    disconnect: () => {},
  }),
}));

const { useHeroDraftStore } = await import('~/store/heroDraftStore');
const { useUserCacheStore } = await import('~/store/userCacheStore');
const { resolveDisplayName } = await import('~/lib/userDisplayName');

const dragon = {
  pk: 1,
  username: 'dc_handle',
  nickname: null,
  discordNickname: 'GwaihirTheWindlord',
  guildNickname: 'DragonClaw',
  avatar: null,
};
const member = {
  pk: 2,
  username: 'm',
  nickname: null,
  discordNickname: null,
  guildNickname: 'Mem',
  avatar: null,
};

const team = (
  id: number,
  captain: Record<string, unknown>,
  members: Record<string, unknown>[],
) => ({
  id,
  tournament_team: 30 + id,
  captain,
  team_name: `Team ${id}`,
  members,
  is_first_pick: null,
  is_radiant: null,
  reserve_time_remaining: 90000,
  is_ready: false,
  is_connected: false,
});
const draftState = (extra: Record<string, unknown> = {}) => ({
  id: 2,
  game: 99,
  tournament_id: 8,
  state: 'waiting_for_captains',
  roll_winner: null,
  draft_teams: [team(1, dragon, [dragon, member])],
  rounds: [],
  current_round: null,
  created_at: '2026-05-19T00:00:00Z',
  updated_at: '2026-05-19T00:00:00Z',
  ...extra,
});
const emit = (msg: unknown) => handlers[handlers.length - 1](msg);
const cached = (pk: number) => useUserCacheStore.getState().getById(pk);

beforeEach(() => {
  handlers.length = 0;
  useUserCacheStore.getState().reset();
  useHeroDraftStore.getState().connect(2);
});
afterEach(() => useHeroDraftStore.getState().disconnect());

describe('heroDraftStore name ingest', () => {
  it('initial_state into an empty cache resolves the captain to the org server nickname', () => {
    emit({
      type: 'initial_state',
      draft_state: draftState({ organization_pk: 7 }),
    });
    expect(resolveDisplayName(cached(1), { orgId: 7 })).toBe('DragonClaw');
    expect(resolveDisplayName(cached(1), { orgId: null })).toBe(
      'GwaihirTheWindlord',
    );
    expect(cached(2)?.orgNicknames).toEqual({ 7: 'Mem' });
  });

  it('herodraft_event with a draft_state upserts under its organization_pk', () => {
    emit({
      type: 'herodraft_event',
      event_type: 'captain_ready',
      draft_state: draftState({ organization_pk: 9 }),
    });
    expect(cached(1)?.orgNicknames).toEqual({ 9: 'DragonClaw' });
  });

  it('without organization_pk stores core names but no server nickname', () => {
    emit({
      type: 'initial_state',
      draft_state: draftState({ organization_pk: null }),
    });
    expect(cached(1)?.discordNickname).toBe('GwaihirTheWindlord');
    expect(cached(1)?.orgNicknames).toEqual({});
  });
});
