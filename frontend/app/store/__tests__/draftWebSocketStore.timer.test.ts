// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DraftEvent, DraftEventType, WebSocketDraftState } from '~/types/draftEvent';

type Handler = (msg: unknown) => void;
const { manager, toast, captured } = vi.hoisted(() => {
  const captured: { handler: Handler | null } = { handler: null };
  return {
    captured,
    toast: vi.fn(),
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
vi.mock('sonner', () => ({ toast }));

const { useDraftWebSocketStore, draftWsSelectors } = await import('~/store/draftWebSocketStore');
const { useUserStore } = await import('~/store/userStore');

const T0 = Date.parse('2026-11-08T12:00:00.000Z');
const emit = (msg: unknown) => captured.handler!(msg);
// Draft events render together once the flush window passes.
const settle = () => vi.advanceTimersByTime(50);

const OPTIONS = { timer_enabled: true, grace_time_ms: 30000, reserve_time_ms: 60000, timeout_action: 'skip' };
const state = (overrides: Partial<WebSocketDraftState> & Record<string, unknown> = {}): WebSocketDraftState =>
  ({
    pk: 1,
    state: 'drafting',
    clock_armed: true,
    paused_at: null,
    resuming_until: null,
    is_manual_pause: false,
    draft_options: OPTIONS,
    latest_round: 22,
    draft_rounds: [
      { pk: 21, pick_number: 1 },
      { pk: 22, pick_number: 2 },
      { pk: 23, pick_number: 3 },
    ],
    users_remaining: [],
    draft_style: 'snake',
    ...overrides,
  }) as WebSocketDraftState;

const tick = (overrides: Record<string, unknown> = {}) => ({
  type: 'draft_tick',
  draft_state: 'drafting',
  server_time: new Date(T0).toISOString(),
  resuming_until: null,
  active_round_pk: 22,
  active_pick_number: 2,
  active_captain_id: 8,
  active_team_id: 2,
  round_started_at: null,
  round_timed_out_at: null,
  round_grace_time_ms: 30000,
  teams: [],
  ...overrides,
});

let nextEventPk = 1;
const evt = (event_type: DraftEventType, payload: object = {}): DraftEvent => ({
  pk: nextEventPk++,
  event_type,
  payload: payload as DraftEvent['payload'],
  actor: null,
  created_at: '2026-11-08T12:00:00Z',
});
const cap = { captain_id: 7, captain_name: 'Ana', captain_avatar_url: null, team_id: 1, team_name: 'T1' };
const skipped = {
  skipped_captain_id: 7, skipped_captain_name: 'Ana', skipped_team_id: 1, skipped_team_name: 'T1',
  next_captain_id: 8, next_captain_name: 'Bo', next_team_id: 2, next_team_name: 'T2',
  from_pick_number: 4, to_pick_number: 5, pick_duration_ms: 60000, reserve_used_ms: 30000,
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(T0);
  useDraftWebSocketStore.getState().reset();
  useUserStore.setState({ curDraftRound: {} as never });
  vi.clearAllMocks();
  useDraftWebSocketStore.getState().connect(1);
});
afterEach(() => vi.useRealTimers());

describe('draftWebSocketStore timer', () => {
  it('initial_state sets draftState without touching events; initial_events sets events without touching draftState', () => {
    emit({ type: 'initial_state', draft_state: state() });
    expect(useDraftWebSocketStore.getState().draftState?.pk).toBe(1);
    expect(useDraftWebSocketStore.getState().events).toEqual([]);
    emit({ type: 'initial_events', events: [evt('draft_lobby_opened')] });
    expect(useDraftWebSocketStore.getState().events).toHaveLength(1);
    expect(useDraftWebSocketStore.getState().draftState?.pk).toBe(1);
    expect(toast).not.toHaveBeenCalled();
  });

  it('tolerates initial_state -> initial_events -> own captain_connected', () => {
    emit({ type: 'initial_state', draft_state: state() });
    emit({ type: 'initial_events', events: [] });
    emit({ type: 'draft_event', event: evt('captain_connected', { ...cap, pick_number: 1, is_active_captain: true }), draft_state: state() });
    settle();
    expect(useDraftWebSocketStore.getState().events).toHaveLength(1);
    expect(toast).not.toHaveBeenCalled();
  });

  it('ingests draft_tick with a clock offset and ignores pings', () => {
    emit({ type: 'ping' });
    emit(tick({ server_time: new Date(T0 + 4000).toISOString() }));
    const s = useDraftWebSocketStore.getState();
    expect(s.tick?.active_round_pk).toBe(22);
    expect(s.serverClockOffsetMs).toBe(4000);
    expect(s.getServerNowISO()).toBe(new Date(T0 + 4000).toISOString());
  });

  it('a tick delivered late does not shift the clock offset', () => {
    emit(tick({ server_time: new Date(T0).toISOString() }));
    expect(useDraftWebSocketStore.getState().serverClockOffsetMs).toBe(0);
    // The next tick left the server 1 s later but sat 1.5 s in a queue.
    vi.setSystemTime(T0 + 2500);
    emit(tick({ server_time: new Date(T0 + 1000).toISOString() }));
    expect(useDraftWebSocketStore.getState().serverClockOffsetMs).toBe(0);
  });

  it('initial_state anchors the clock offset before the first tick', () => {
    emit({ type: 'initial_state', draft_state: state(), server_time: new Date(T0 + 5000).toISOString() });
    expect(useDraftWebSocketStore.getState().serverClockOffsetMs).toBe(5000);
  });

  it('keeps a tick that arrives before initial_state', () => {
    emit(tick());
    expect(useDraftWebSocketStore.getState().draftState).toBeNull();
    expect(useDraftWebSocketStore.getState().tick).not.toBeNull();
  });

  it('drops an invalid draft_tick without throwing', () => {
    expect(() => emit({ type: 'draft_tick', server_time: 'x' })).not.toThrow();
    expect(useDraftWebSocketStore.getState().tick).toBeNull();
  });

  it('heartbeat sends immediately, every 3000 ms, is idempotent and stops on disconnect', () => {
    const { startHeartbeat, stopHeartbeat } = useDraftWebSocketStore.getState();
    startHeartbeat();
    startHeartbeat();
    expect(manager.send).toHaveBeenCalledTimes(1);
    expect(manager.send).toHaveBeenLastCalledWith('conn-1', { type: 'heartbeat' });
    vi.advanceTimersByTime(3000);
    expect(manager.send).toHaveBeenCalledTimes(2);
    stopHeartbeat();
    vi.advanceTimersByTime(9000);
    expect(manager.send).toHaveBeenCalledTimes(2);
    startHeartbeat();
    useDraftWebSocketStore.getState().disconnect();
    vi.advanceTimersByTime(9000);
    expect(manager.send).toHaveBeenCalledTimes(3);
    expect(useDraftWebSocketStore.getState()._stopHeartbeat).toBeNull();
  });

  it('startHeartbeat does nothing when not connected', () => {
    useDraftWebSocketStore.getState().disconnect();
    vi.mocked(manager.send).mockClear();
    useDraftWebSocketStore.getState().startHeartbeat();
    vi.advanceTimersByTime(3000);
    expect(manager.send).not.toHaveBeenCalled();
    expect(useDraftWebSocketStore.getState()._stopHeartbeat).toBeNull();
  });

  it('toasts through getEventToast: pick_skipped yes, pick_timed_out no, captain_disconnected only when active', () => {
    emit({ type: 'draft_event', event: evt('pick_timed_out', { ...cap, pick_number: 4, elapsed_ms: 1, reserve_used_ms: 1 }) });
    expect(toast).not.toHaveBeenCalled();
    emit({ type: 'draft_event', event: evt('pick_skipped', { ...skipped, deferred_to_pick_number: 5 }), draft_state: state() });
    expect(toast).toHaveBeenCalledWith('Ana ran out of time — Bo is up, Ana picks at #5');
    emit({ type: 'draft_event', event: evt('captain_disconnected', { ...cap, pick_number: 4, is_active_captain: false }) });
    expect(toast).toHaveBeenCalledTimes(1);
  });

  it('sets forceJumpToRoundPk on pick_skipped and round_started', () => {
    emit({
      type: 'draft_event',
      event: evt('round_started', { ...cap, pick_number: 3, started_at: new Date(T0).toISOString(), grace_time_ms: 30000, reserve_ms: null }),
      draft_state: state({ latest_round: 23 }),
    });
    settle();
    expect(useDraftWebSocketStore.getState().forceJumpToRoundPk).toBe(23);
    useDraftWebSocketStore.getState().clearForceJump();
    expect(useDraftWebSocketStore.getState().forceJumpToRoundPk).toBeNull();
    emit({ type: 'draft_event', event: evt('pick_skipped', { ...skipped, deferred_to_pick_number: null }), draft_state: state({ latest_round: 22 }) });
    settle();
    expect(useDraftWebSocketStore.getState().forceJumpToRoundPk).toBe(22);
  });

  it('jumpToPickNumber moves the userStore cursor and reports misses', () => {
    emit({ type: 'initial_state', draft_state: state() });
    expect(useDraftWebSocketStore.getState().jumpToPickNumber(3)).toBe(true);
    expect(useUserStore.getState().curDraftRound.pk).toBe(23);
    expect(useDraftWebSocketStore.getState().jumpToPickNumber(99)).toBe(false);
    expect(useUserStore.getState().curDraftRound.pk).toBe(23);
  });

  it('selectors: draftState.latest_round wins over a stale tick; the tick fills in before initial_state', () => {
    const rounds = [{ pk: 21, pick_number: 1, captain: { pk: 7 } }, { pk: 22, pick_number: 2, captain: { pk: 8 } }];
    emit(tick({ active_round_pk: 21, active_captain_id: 7 }));
    expect(draftWsSelectors.activeRoundPk(useDraftWebSocketStore.getState())).toBe(21);
    emit({ type: 'initial_state', draft_state: state({ latest_round: 22, draft_rounds: rounds }) });
    const s = useDraftWebSocketStore.getState();
    expect(draftWsSelectors.activeRoundPk(s)).toBe(22);
    expect(draftWsSelectors.isMyTurn(s, 8)).toBe(true);
    expect(draftWsSelectors.isMyTurn(s, 7)).toBe(false);
  });

  it('isActiveCaptainDisconnected reads heartbeat freshness from ticks, initial_state and captain_heartbeat', () => {
    const rounds = [{ pk: 21, pick_number: 1, captain: { pk: 7 } }, { pk: 22, pick_number: 2, captain: { pk: 8 } }];
    emit({ type: 'initial_state', draft_state: state({ latest_round: 21, draft_rounds: rounds }), captain_fresh: { '7': true, '8': false } });
    expect(draftWsSelectors.isActiveCaptainDisconnected(useDraftWebSocketStore.getState())).toBe(false);
    emit(tick({ active_round_pk: 21, active_captain_id: 7, teams: [{ team_id: 1, captain_id: 7, reserve_ms: 10000, is_connected: false, is_ready: true }] }));
    expect(draftWsSelectors.isActiveCaptainDisconnected(useDraftWebSocketStore.getState())).toBe(true);
  });

  it('while paused, freshness changes only on captain_heartbeat, not on socket-presence draft_state', () => {
    const teamsA = (connected: boolean) => ({ tournament: { pk: 1, teams: [{ pk: 1, captain: { pk: 7 }, draft_is_connected: connected }] } });
    const rounds = [{ pk: 21, pick_number: 1, captain: { pk: 7 } }, { pk: 22, pick_number: 2, captain: { pk: 8 } }];
    emit({ type: 'initial_state', draft_state: state({ latest_round: 21, draft_rounds: rounds }), captain_fresh: { '7': true } });
    emit({
      type: 'draft_event',
      event: evt('draft_paused', { ...cap, reason: 'captain_disconnected', paused_by_id: null, paused_by_name: null, pick_number: 1 }),
      draft_state: state({ state: 'paused', clock_armed: false, latest_round: 21, draft_rounds: rounds, ...teamsA(true) }),
    });
    settle();
    expect(draftWsSelectors.isActiveCaptainDisconnected(useDraftWebSocketStore.getState())).toBe(true);
    emit({
      type: 'draft_event',
      event: evt('captain_connected', { ...cap, pick_number: 1, is_active_captain: true }),
      draft_state: state({ state: 'paused', clock_armed: false, latest_round: 21, draft_rounds: rounds, ...teamsA(true) }),
    });
    settle();
    expect(draftWsSelectors.isActiveCaptainDisconnected(useDraftWebSocketStore.getState())).toBe(true);
    emit({ type: 'captain_heartbeat', captain_id: 7, fresh: true });
    expect(draftWsSelectors.isActiveCaptainDisconnected(useDraftWebSocketStore.getState())).toBe(false);
    emit({
      type: 'draft_event',
      event: evt('player_picked', { captain_name: 'Ana', picked_name: 'P', pick_number: 1 }),
      draft_state: state({ state: 'paused', clock_armed: false, latest_round: 22, draft_rounds: rounds, ...teamsA(true) }),
    });
    settle();
    expect(draftWsSelectors.activeRoundPk(useDraftWebSocketStore.getState())).toBe(22);
  });

  it('a burst of draft events renders once with the newest state; toasts fire as events arrive', () => {
    emit({ type: 'initial_state', draft_state: state({ latest_round: 21 }) });
    const renders = vi.fn();
    const unsubscribe = useDraftWebSocketStore.subscribe(renders);
    const burst = [
      evt('pick_timed_out', { ...cap, pick_number: 1, elapsed_ms: 1, reserve_used_ms: 0 }),
      evt('captain_assigned', { ...cap, pick_number: 1 }),
      evt('pick_skipped', { ...skipped, deferred_to_pick_number: null }),
      evt('round_started', { ...cap, pick_number: 1, started_at: new Date(T0).toISOString(), grace_time_ms: 30000, reserve_ms: null }),
    ];
    burst.forEach((event, i) => emit({ type: 'draft_event', event, draft_state: state({ latest_round: 21 + i }) }));
    expect(toast).toHaveBeenCalledWith('Ana ran out of time — Bo is up');
    expect(renders).not.toHaveBeenCalled();
    settle();
    unsubscribe();
    expect(renders).toHaveBeenCalledTimes(1);
    const s = useDraftWebSocketStore.getState();
    expect(s.events.map((e) => e.event_type)).toEqual(['round_started', 'pick_skipped', 'captain_assigned', 'pick_timed_out']);
    expect(s.draftState?.latest_round).toBe(24);
    expect(s.forceJumpToRoundPk).toBe(24);
  });

  it('keeps a forced jump when a later event in the same burst carries state', () => {
    emit({
      type: 'draft_event',
      event: evt('round_started', { ...cap, pick_number: 3, started_at: new Date(T0).toISOString(), grace_time_ms: 30000, reserve_ms: null }),
      draft_state: state({ latest_round: 23 }),
    });
    emit({
      type: 'draft_event',
      event: evt('player_picked', { captain_name: 'Ana', picked_name: 'P', pick_number: 3 }),
      draft_state: state({ latest_round: 23 }),
    });
    settle();
    expect(useDraftWebSocketStore.getState().forceJumpToRoundPk).toBe(23);
  });

  it('initial_state resets the event ordering guard', () => {
    emit({ type: 'draft_event', event: { ...evt('player_picked', { captain_name: 'Ana', picked_name: 'P', pick_number: 1 }), pk: 500 }, draft_state: state({ latest_round: 23 }) });
    settle();
    emit({ type: 'initial_state', draft_state: state({ latest_round: 21 }) });
    expect(useDraftWebSocketStore.getState()._lastStateEventPk).toBeNull();
    emit({ type: 'draft_event', event: { ...evt('round_started', {}), pk: 400 }, draft_state: state({ latest_round: 22 }) });
    settle();
    expect(useDraftWebSocketStore.getState().draftState?.latest_round).toBe(22);
  });

  it('never replaces a newer draft_state with one built for an older event', () => {
    const newer = evt('player_picked', { captain_name: 'Ana', picked_name: 'P', pick_number: 1 });
    const older = { ...evt('captain_connected', { ...cap, pick_number: 1, is_active_captain: true }), pk: newer.pk - 1 };
    emit({ type: 'draft_event', event: newer, draft_state: state({ latest_round: 23 }) });
    settle();
    emit({ type: 'draft_event', event: older, draft_state: state({ latest_round: 21 }) });
    settle();
    expect(useDraftWebSocketStore.getState().draftState?.latest_round).toBe(23);
    expect(useDraftWebSocketStore.getState().events).toHaveLength(2);
  });

  it('applies buffered events before a tick so the tick sees their state', () => {
    const until = new Date(T0 + 3000).toISOString();
    emit({ type: 'initial_state', draft_state: state({ state: 'paused' }) });
    emit({ type: 'draft_event', event: evt('draft_resumed', {}), draft_state: state({ state: 'resuming', resuming_until: until }) });
    emit(tick({ draft_state: 'drafting', server_time: new Date(T0 + 3500).toISOString() }));
    expect(useDraftWebSocketStore.getState().draftState?.state).toBe('drafting');
  });

  it('a drafting tick past resuming_until ends the resuming countdown', () => {
    const until = new Date(T0 + 3000).toISOString();
    emit({ type: 'initial_state', draft_state: state({ state: 'resuming', resuming_until: until }) });
    emit(tick({ draft_state: 'resuming', resuming_until: until, server_time: new Date(T0 + 1000).toISOString() }));
    expect(draftWsSelectors.draftStatus(useDraftWebSocketStore.getState())).toBe('resuming');

    emit(tick({ draft_state: 'drafting', server_time: new Date(T0 + 3200).toISOString() }));
    const s = useDraftWebSocketStore.getState();
    expect(draftWsSelectors.draftStatus(s)).toBe('drafting');
    expect(s.draftState?.resuming_until).toBeNull();
  });

  it('a drafting tick from before resuming_until does not end the countdown', () => {
    const until = new Date(T0 + 3000).toISOString();
    emit({ type: 'initial_state', draft_state: state({ state: 'resuming', resuming_until: until }) });
    emit(tick({ draft_state: 'drafting', server_time: new Date(T0 - 5000).toISOString() }));
    expect(draftWsSelectors.draftStatus(useDraftWebSocketStore.getState())).toBe('resuming');
  });

  it('a drafting tick never overrides paused', () => {
    emit({ type: 'initial_state', draft_state: state({ state: 'paused' }) });
    emit(tick({ draft_state: 'drafting', server_time: new Date(T0 + 9000).toISOString() }));
    expect(draftWsSelectors.draftStatus(useDraftWebSocketStore.getState())).toBe('paused');
  });

  it('teamTiming returns the same empty array reference with no tick', () => {
    const s = useDraftWebSocketStore.getState();
    expect(draftWsSelectors.teamTiming(s)).toBe(draftWsSelectors.teamTiming(s));
  });

  it('connect passes staleTimeoutMs 3000', () => {
    expect(manager.connect).toHaveBeenCalledWith(expect.stringContaining('/api/draft/1/'), expect.objectContaining({ staleTimeoutMs: 3000 }));
  });
});
