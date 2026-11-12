import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CLOCK_OFFSET_SAMPLES,
  addClockOffsetSample,
  captureClockOffset,
  elapsedSince,
  remaining,
  seedClockOffset,
  serverNow,
  serverNowISO,
} from '~/lib/draftClock';

const T0 = Date.parse('2026-11-08T12:00:00.000Z');
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(T0); });
afterEach(() => vi.useRealTimers());

describe('captureClockOffset', () => {
  it('is server minus local receive time', () => {
    expect(captureClockOffset(new Date(T0 + 5_000).toISOString(), T0)).toBe(5_000);
    expect(captureClockOffset(new Date(T0 - 1_500).toISOString(), T0)).toBe(-1_500);
  });
  it('is 0 for an unparseable server_time', () => {
    expect(captureClockOffset('garbage', T0)).toBe(0);
  });
});

describe('serverNow / serverNowISO', () => {
  it('adds the offset to Date.now()', () => {
    expect(serverNow(2_000)).toBe(T0 + 2_000);
    expect(serverNowISO(0)).toBe(new Date(T0).toISOString());
  });
});

describe('elapsedSince / remaining', () => {
  const anchor = new Date(T0 - 10_000).toISOString();
  it('measures elapsed and remaining against server now', () => {
    expect(elapsedSince(anchor, T0)).toBe(10_000);
    expect(remaining(anchor, 30_000, T0)).toBe(20_000);
  });
  it('clamps at zero once expired', () => {
    expect(remaining(anchor, 5_000, T0)).toBe(0);
  });
  it('returns the full duration for an anchor in the future', () => {
    const future = new Date(T0 + 4_000).toISOString();
    expect(elapsedSince(future, T0)).toBe(0);
    expect(remaining(future, 30_000, T0)).toBe(30_000);
  });
  it('returns 0 for null anchor or non-numeric duration', () => {
    expect(elapsedSince(null, T0)).toBe(0);
    expect(remaining(null, 30_000, T0)).toBe(0);
    expect(remaining(anchor, null, T0)).toBe(0);
    expect(remaining(anchor, undefined, T0)).toBe(0);
    expect(remaining('nope', 30_000, T0)).toBe(0);
  });
});

describe('clock offset estimator', () => {
  const at = (ms: number) => new Date(T0 + ms).toISOString();

  it('a late tick does not move the offset', () => {
    let est = addClockOffsetSample([], at(0), T0);
    expect(est.offsetMs).toBe(0);
    // Sent 1 s later, delivered after 1.5 s in a queue.
    est = addClockOffsetSample(est.samples, at(1000), T0 + 2500);
    expect(est.offsetMs).toBe(0);
  });

  it('follows a real clock change once the old samples age out', () => {
    let est = addClockOffsetSample([], at(0), T0);
    for (let i = 1; i <= CLOCK_OFFSET_SAMPLES; i++) {
      est = addClockOffsetSample(est.samples, at(i * 1000 - 3000), T0 + i * 1000);
    }
    expect(est.offsetMs).toBe(-3000);
  });

  it('initial_state seeds the offset; a missing server_time keeps the current samples', () => {
    expect(seedClockOffset([5], at(4000), T0)).toEqual({ samples: [4000], offsetMs: 4000 });
    expect(seedClockOffset([5], undefined, T0)).toEqual({ samples: [5], offsetMs: 5 });
  });
});
