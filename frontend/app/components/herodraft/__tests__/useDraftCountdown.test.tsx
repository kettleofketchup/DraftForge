// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _deriveCountdown, useDraftCountdown } from '~/components/herodraft/useDraftCountdown';
import type { HeroDraftTick } from '~/components/herodraft/types';
import { useHeroDraftStore } from '~/store/heroDraftStore';

const T0 = Date.parse('2026-11-08T12:00:00.000Z');
const tick = (over: Partial<HeroDraftTick> = {}): HeroDraftTick => ({
  type: 'herodraft_tick',
  draft_state: 'drafting',
  server_time: new Date(T0).toISOString(),
  current_round: 0,
  active_team_id: 1,
  round_started_at: new Date(T0 - 40_000).toISOString(),
  round_grace_time_ms: 30_000,
  team_a_id: 1,
  team_a_reserve_ms: 90_000,
  team_b_id: 2,
  team_b_reserve_ms: 90_000,
  resuming_until: null,
  ...over,
});

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(T0); });
afterEach(() => { vi.useRealTimers(); });

describe('_deriveCountdown (characterisation)', () => {
  it('burns only the active team past grace', () => {
    const c = _deriveCountdown(tick(), 0);
    expect(c.graceRemainingMs).toBe(0);
    expect(c.teamAReserveMs).toBe(80_000);
    expect(c.teamBReserveMs).toBe(90_000);
    expect(c.resumingRemainingMs).toBe(0);
  });

  it('does not burn reserve inside grace', () => {
    const c = _deriveCountdown(tick({ round_started_at: new Date(T0 - 10_000).toISOString() }), 0);
    expect(c.graceRemainingMs).toBe(20_000);
    expect(c.teamAReserveMs).toBe(90_000);
  });

  it('applies the clock offset', () => {
    const c = _deriveCountdown(tick({ round_started_at: new Date(T0 - 10_000).toISOString() }), 5_000);
    expect(c.graceRemainingMs).toBe(15_000);
  });

  it('freezes drafting values at resuming_until while resuming', () => {
    const t = tick({
      draft_state: 'resuming',
      resuming_until: new Date(T0 + 3_000).toISOString(),
      round_started_at: new Date(T0 - 20_000).toISOString(),
    });
    const a = _deriveCountdown(t, 0);
    expect(a.resumingRemainingMs).toBe(3_000);
    expect(a.graceRemainingMs).toBe(7_000);
    vi.setSystemTime(T0 + 1_000);
    const b = _deriveCountdown(t, 0);
    expect(b.resumingRemainingMs).toBe(2_000);
    expect(b.graceRemainingMs).toBe(7_000);
  });

  it('returns zeros for null anchors and for a null tick', () => {
    expect(_deriveCountdown(tick({ round_started_at: null }), 0)).toEqual({
      graceRemainingMs: 0, teamAReserveMs: 0, teamBReserveMs: 0, resumingRemainingMs: 0,
    });
    expect(_deriveCountdown(null, 0).graceRemainingMs).toBe(0);
  });
});

describe('useDraftCountdown (characterisation)', () => {
  beforeEach(() => {
    useHeroDraftStore.setState({
      tick: tick({ round_started_at: new Date(T0 - 10_000).toISOString() }),
      serverClockOffsetMs: 0,
      draft: { state: 'paused' } as never,
    });
  });

  it('freezes the frame loop while paused but re-derives on a new tick', () => {
    const { result } = renderHook(() => useDraftCountdown());
    expect(result.current.graceRemainingMs).toBe(20_000);
    act(() => { vi.setSystemTime(T0 + 5_000); vi.advanceTimersByTime(100); });
    expect(result.current.graceRemainingMs).toBe(20_000);
    act(() => {
      useHeroDraftStore.setState({ tick: tick({ round_started_at: new Date(T0 - 25_000).toISOString() }) });
    });
    expect(result.current.graceRemainingMs).toBe(0);
  });

  it('advances every frame while not paused', () => {
    useHeroDraftStore.setState({ draft: { state: 'drafting' } as never });
    const { result } = renderHook(() => useDraftCountdown());
    act(() => { vi.setSystemTime(T0 + 5_000); vi.advanceTimersByTime(100); });
    // advanceTimersByTime also moves the faked Date.now, so the last frame lands at ~T0+5_084..5_100
    expect(result.current.graceRemainingMs).toBeLessThanOrEqual(15_000);
    expect(result.current.graceRemainingMs).toBeGreaterThan(14_850);
  });
});
