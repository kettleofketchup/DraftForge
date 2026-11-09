import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { captureClockOffset, elapsedSince, remaining, serverNow, serverNowISO } from '~/lib/draftClock';

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
