// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Handler = (msg: unknown) => void;
const handlers: Handler[] = [];
const { send } = vi.hoisted(() => ({ send: vi.fn((_connId: string, _msg: unknown) => true) }));
vi.mock('~/lib/websocket', () => ({
  getWebSocketManager: () => ({
    connect: () => 'conn-1',
    subscribe: (_id: string, h: Handler) => { handlers.push(h); return () => {}; },
    send,
    disconnect: () => {},
  }),
}));

const { useHeroDraftStore, getServerNowISO } = await import('~/store/heroDraftStore');

const T0 = Date.parse('2026-11-08T12:00:00.000Z');
const baseTick = { type: 'herodraft_tick', draft_state: 'drafting', current_round: 0, active_team_id: 1,
  round_started_at: null, round_grace_time_ms: 30000, team_a_id: 1, team_a_reserve_ms: 1, team_b_id: 2, team_b_reserve_ms: 1 };

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(T0); handlers.length = 0; useHeroDraftStore.getState().connect(1); send.mockClear(); });
afterEach(() => { useHeroDraftStore.getState().disconnect(); vi.useRealTimers(); });

const heartbeatSends = () => send.mock.calls.filter(([, msg]) => (msg as { type?: string })?.type === 'heartbeat').length;

describe('heroDraftStore heartbeat (characterisation)', () => {
  it('a second startHeartbeat while running starts no second loop', () => {
    useHeroDraftStore.getState().startHeartbeat();
    useHeroDraftStore.getState().startHeartbeat();
    expect(heartbeatSends()).toBe(1);
    vi.advanceTimersByTime(3000);
    expect(heartbeatSends()).toBe(2);
  });

  it('stopHeartbeat stops the loop', () => {
    useHeroDraftStore.getState().startHeartbeat();
    vi.advanceTimersByTime(3000);
    useHeroDraftStore.getState().stopHeartbeat();
    vi.advanceTimersByTime(9000);
    expect(heartbeatSends()).toBe(2);
  });

  it('startHeartbeat while not connected sends nothing and arms no loop', () => {
    useHeroDraftStore.getState().disconnect();
    send.mockClear();
    useHeroDraftStore.getState().startHeartbeat();
    vi.advanceTimersByTime(9000);
    expect(heartbeatSends()).toBe(0);
    // had the disconnected call armed a loop, the "already running" guard would swallow this immediate send
    useHeroDraftStore.getState().connect(1);
    useHeroDraftStore.getState().startHeartbeat();
    expect(heartbeatSends()).toBe(1);
  });
});

describe('heroDraftStore clock offset (characterisation)', () => {
  it('captures server_time - receivedAt on a tick', () => {
    handlers[0]({ ...baseTick, server_time: new Date(T0 + 5_000).toISOString() });
    expect(useHeroDraftStore.getState().serverClockOffsetMs).toBe(5_000);
  });

  it('falls back to offset 0 on an unparseable server_time', () => {
    handlers[0]({ ...baseTick, server_time: 'not-a-date' });
    expect(useHeroDraftStore.getState().serverClockOffsetMs).toBe(0);
  });

  it('getServerNowISO uses the local clock when the offset is 0', () => {
    useHeroDraftStore.setState({ serverClockOffsetMs: 0 });
    expect(getServerNowISO()).toBe(new Date(T0).toISOString());
    useHeroDraftStore.setState({ serverClockOffsetMs: 2_500 });
    expect(getServerNowISO()).toBe(new Date(T0 + 2_500).toISOString());
  });
});
