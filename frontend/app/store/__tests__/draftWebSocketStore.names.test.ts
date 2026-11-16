// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { WebSocketDraftState } from '~/types/draftEvent';

type Handler = (msg: unknown) => void;
const { manager, captured } = vi.hoisted(() => {
  const captured: { handler: Handler | null } = { handler: null };
  return {
    captured,
    manager: {
      connect: vi.fn((_url: string, _opts: unknown) => 'conn-1'),
      subscribe: vi.fn((_id: string, cb: Handler) => {
        captured.handler = cb;
        return () => {};
      }),
      send: vi.fn((_id: string, _msg: unknown) => true),
    },
  };
});
vi.mock('~/lib/websocket', () => ({ getWebSocketManager: () => manager }));
vi.mock('sonner', () => ({ toast: vi.fn() }));

const { useDraftWebSocketStore } = await import('~/store/draftWebSocketStore');
const { useUserStore } = await import('~/store/userStore');
const { useOrgStore } = await import('~/store/orgStore');
const { useUserCacheStore } = await import('~/store/userCacheStore');

const emit = (msg: unknown) => captured.handler!(msg);
const state = (overrides: Record<string, unknown> = {}): WebSocketDraftState =>
  ({
    pk: 1,
    state: 'drafting',
    clock_armed: false,
    paused_at: null,
    resuming_until: null,
    is_manual_pause: false,
    draft_options: {
      timer_enabled: false,
      grace_time_ms: 0,
      reserve_time_ms: 0,
      timeout_action: 'skip',
    },
    latest_round: null,
    draft_rounds: [],
    users_remaining: [1],
    draft_style: 'snake',
    tournament: { pk: 5, teams: [] },
    _users: {
      1: {
        pk: 1,
        username: 'dc_handle',
        discordNickname: 'GwaihirTheWindlord',
        guildNickname: 'DragonClaw',
      },
    },
    ...overrides,
  }) as unknown as WebSocketDraftState;
const nicknames = () => useUserCacheStore.getState().getById(1)?.orgNicknames;

beforeEach(() => {
  useDraftWebSocketStore.getState().reset();
  useUserCacheStore.getState().reset();
  useOrgStore.setState({ currentOrg: null });
  useUserStore.setState({ tournament: {} as never });
  useDraftWebSocketStore.getState().connect(1);
});
afterEach(() => useDraftWebSocketStore.getState().disconnect());

describe('draftWebSocketStore name ingest', () => {
  it('tags _users with the WS organization_pk before any org fetch', () => {
    emit({ type: 'initial_state', draft_state: state({ organization_pk: 7 }) });
    expect(nicknames()).toEqual({ 7: 'DragonClaw' });
  });

  it('ignores a stale currentOrg when organization_pk is present', () => {
    useOrgStore.setState({ currentOrg: { pk: 3 } as never });
    emit({ type: 'initial_state', draft_state: state({ organization_pk: 7 }) });
    expect(nicknames()).toEqual({ 7: 'DragonClaw' });
  });

  it('stores no server nickname when the loaded tournament is a different one', () => {
    useOrgStore.setState({ currentOrg: { pk: 3 } as never });
    useUserStore.setState({
      tournament: { pk: 99, organization_pk: 7 } as never,
    });
    emit({ type: 'initial_state', draft_state: state() });
    expect(useUserCacheStore.getState().getById(1)?.discordNickname).toBe(
      'GwaihirTheWindlord',
    );
    expect(nicknames()).toEqual({});
  });

  it('falls back to the loaded tournament org when it is the draft tournament', () => {
    useUserStore.setState({
      tournament: { pk: 5, organization_pk: 7 } as never,
    });
    emit({ type: 'initial_state', draft_state: state() });
    expect(nicknames()).toEqual({ 7: 'DragonClaw' });
  });
});
