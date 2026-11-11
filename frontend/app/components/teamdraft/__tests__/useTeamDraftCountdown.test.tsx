// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { formatClock } from '../timer/formatClock';
import {
  _deriveTeamCountdown,
  useTeamDraftCountdown,
  type CountdownDraftSlice,
} from '../timer/useTeamDraftCountdown';
import { T0, tick } from './fixtures';

const armedDraft = (o: Partial<CountdownDraftSlice> = {}): CountdownDraftSlice => ({
  state: 'drafting',
  clock_armed: true,
  latest_round: 22,
  draft_rounds: [{ pk: 22, started_at: new Date(T0 - 25_000).toISOString(), grace_time_ms: 20_000, captain: { pk: 7 } }],
  tournament: {
    teams: [
      { pk: 1, draft_reserve_ms: 10_000, captain: { pk: 7 } },
      { pk: 2, draft_reserve_ms: 10_000, captain: { pk: 8 } },
    ],
  },
  ...o,
});

describe('_deriveTeamCountdown', () => {
  it('is unarmed with no tick and no paused draft', () =>
    expect(_deriveTeamCountdown(null, null, 0, T0)).toEqual({ kind: 'unarmed' }));
  it('is unarmed when the tick has no round anchor', () =>
    expect(_deriveTeamCountdown(tick({ round_started_at: null }), null, 0, T0).kind).toBe('unarmed'));
  it('burns only the active team past grace', () => {
    const c = _deriveTeamCountdown(tick(), null, 0, T0);
    expect(c).toMatchObject({ kind: 'armed', graceRemainingMs: 0, resumingRemainingMs: 0, expired: false });
    if (c.kind === 'armed') expect(c.reserveByTeamId).toEqual({ 1: 5_000, 2: 10_000 });
  });
  it('shows grace remaining before grace ends and leaves reserve intact', () => {
    const c = _deriveTeamCountdown(tick({ round_started_at: new Date(T0 - 5_000).toISOString() }), null, 0, T0);
    if (c.kind === 'armed') {
      expect(c.graceRemainingMs).toBe(15_000);
      expect(c.reserveByTeamId[1]).toBe(10_000);
    } else throw new Error('expected armed');
  });
  it('freezes values at resuming_until while resuming', () => {
    const until = new Date(T0 + 3_000).toISOString();
    const c = _deriveTeamCountdown(
      tick({ draft_state: 'resuming', resuming_until: until, round_started_at: new Date(T0 - 7_000).toISOString() }),
      null,
      0,
      T0,
    );
    if (c.kind === 'armed') {
      expect(c.resumingRemainingMs).toBe(3_000);
      expect(c.graceRemainingMs).toBe(10_000);
    } else throw new Error('expected armed');
  });
  it('flags a last-slot expiry', () => {
    const c = _deriveTeamCountdown(tick({ round_timed_out_at: new Date(T0).toISOString() }), null, 0, T0);
    expect(c.kind === 'armed' && c.expired).toBe(true);
  });
  it('derives frozen values from the serialized draft when paused with no tick', () => {
    const draft = {
      state: 'paused' as const,
      paused_at: new Date(T0 - 2_000).toISOString(),
      latest_round: 22,
      draft_rounds: [{ pk: 22, started_at: new Date(T0 - 27_000).toISOString(), grace_time_ms: 20_000, captain: { pk: 7 } }],
      tournament: {
        teams: [
          { pk: 1, draft_reserve_ms: 10_000, captain: { pk: 7 } },
          { pk: 2, draft_reserve_ms: 10_000, captain: { pk: 8 } },
        ],
      },
    };
    const c = _deriveTeamCountdown(null, draft, 0, T0);
    expect(c).toMatchObject({ kind: 'armed', graceRemainingMs: 0 });
    if (c.kind === 'armed') expect(c.reserveByTeamId).toEqual({ 1: 5_000, 2: 10_000 });
  });
  it('keeps a captain-less team in reserveByTeamId', () => {
    const c = _deriveTeamCountdown(
      tick({
        teams: [
          { team_id: 1, captain_id: 7, reserve_ms: 10_000, is_connected: true, is_ready: true },
          { team_id: 3, captain_id: null, reserve_ms: 10_000, is_connected: false, is_ready: false },
        ],
      }),
      null,
      0,
      T0,
    );
    if (c.kind === 'armed') expect(c.reserveByTeamId[3]).toBe(10_000);
    else throw new Error('expected armed');
  });
  it('treats a null tick reserve as 0, never NaN', () => {
    const c = _deriveTeamCountdown(
      tick({
        teams: [
          { team_id: 1, captain_id: 7, reserve_ms: null, is_connected: true, is_ready: true },
          { team_id: 2, captain_id: 8, reserve_ms: null, is_connected: true, is_ready: true },
        ],
      }),
      null,
      0,
      T0,
    );
    if (c.kind === 'armed') expect(c.reserveByTeamId).toEqual({ 1: 0, 2: 0 });
    else throw new Error('expected armed');
  });
  it('applies the server clock offset', () => {
    const c = _deriveTeamCountdown(tick({ round_started_at: new Date(T0).toISOString() }), null, 0, T0 + 4_000);
    if (c.kind === 'armed') expect(c.graceRemainingMs).toBe(16_000);
    else throw new Error('expected armed');
  });
  it('armed draft with no tick yet derives from the serialized active round (not unarmed)', () => {
    const c = _deriveTeamCountdown(null, armedDraft(), 0, T0);
    expect(c).toMatchObject({ kind: 'armed', graceRemainingMs: 0, expired: false });
    if (c.kind === 'armed') expect(c.reserveByTeamId).toEqual({ 1: 5_000, 2: 10_000 });
  });
  it('ignores a tick that still names the previous round', () => {
    const draft = armedDraft({
      latest_round: 23,
      draft_rounds: [{ pk: 23, started_at: new Date(T0 - 1_000).toISOString(), grace_time_ms: 20_000, captain: { pk: 8 } }],
    });
    const c = _deriveTeamCountdown(tick({ active_round_pk: 22 }), draft, 0, T0);
    if (c.kind === 'armed') {
      expect(c.graceRemainingMs).toBe(19_000);
      expect(c.reserveByTeamId).toEqual({ 1: 10_000, 2: 10_000 });
    } else throw new Error('expected armed');
  });
  it('ignores a pre-pause tick once resume moved the round anchor', () => {
    const draft = armedDraft({
      state: 'resuming',
      resuming_until: new Date(T0 + 2_000).toISOString(),
      draft_rounds: [{ pk: 22, started_at: new Date(T0 - 5_000).toISOString(), grace_time_ms: 20_000, captain: { pk: 7 } }],
    });
    const stale = tick({ round_started_at: new Date(T0 - 65_000).toISOString() });
    const c = _deriveTeamCountdown(stale, draft, 0, T0);
    expect(c).toMatchObject({ kind: 'armed', resumingRemainingMs: 2_000, graceRemainingMs: 13_000 });
    if (c.kind === 'armed') expect(c.reserveByTeamId).toEqual({ 1: 10_000, 2: 10_000 });
  });
  it('ignores an expired tick after a shuffle skip re-armed the same round', () => {
    const draft = armedDraft({
      draft_rounds: [{ pk: 22, started_at: new Date(T0 - 1_000).toISOString(), timed_out_at: null, grace_time_ms: 20_000, captain: { pk: 8 } }],
    });
    const stale = tick({ round_timed_out_at: new Date(T0 - 1_500).toISOString() });
    const c = _deriveTeamCountdown(stale, draft, 0, T0);
    expect(c).toMatchObject({ kind: 'armed', expired: false, graceRemainingMs: 19_000 });
  });
  it('uses a tick whose anchor matches the round in another ISO spelling', () => {
    const draft = armedDraft({
      draft_rounds: [{ pk: 22, started_at: '2026-11-08T11:59:35+00:00', grace_time_ms: 20_000, captain: { pk: 7 } }],
    });
    const c = _deriveTeamCountdown(tick({ round_timed_out_at: new Date(T0).toISOString() }), draft, 0, T0);
    expect(c.kind === 'armed' && c.expired).toBe(true);
  });
  it('is unarmed when the draft is not clock_armed, even with a tick', () => {
    expect(_deriveTeamCountdown(tick(), armedDraft({ clock_armed: false }), 0, T0).kind).toBe('unarmed');
  });
});

describe('useTeamDraftCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(T0);
  });
  afterEach(() => vi.useRealTimers());
  it('advances while drafting and freezes while paused', () => {
    const t = tick({ round_started_at: new Date(T0 - 5_000).toISOString() });
    const { result, rerender } = renderHook(
      ({ d }) => useTeamDraftCountdown(t, d, 0),
      { initialProps: { d: { state: 'drafting' as const, clock_armed: true, latest_round: 22 } as CountdownDraftSlice } },
    );
    const first = result.current.kind === 'armed' ? result.current.graceRemainingMs : -1;
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(result.current.kind === 'armed' && result.current.graceRemainingMs).toBeLessThan(first);
    rerender({ d: { state: 'paused' as const, clock_armed: false, latest_round: 22, paused_at: new Date(T0 + 1_000).toISOString() } as CountdownDraftSlice });
    const frozen = result.current;
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(result.current).toEqual(frozen);
  });
});

describe('formatClock', () => {
  it('rounds to the nearest second as m:ss', () => {
    expect(formatClock(29_600)).toBe('0:30');
    expect(formatClock(90_000)).toBe('1:30');
    expect(formatClock(-5)).toBe('0:00');
  });
});
