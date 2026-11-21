import { describe, expect, it } from 'vitest';
import { periodOptions, safeTimeZone } from '../timezone';

describe('safeTimeZone', () => {
  it('falls back to UTC for an invalid zone', () => {
    expect(safeTimeZone('Not/AZone')).toBe('UTC');
  });

  it('falls back to UTC for a missing zone and keeps a valid one', () => {
    expect(safeTimeZone(undefined)).toBe('UTC');
    expect(safeTimeZone('America/New_York')).toBe('America/New_York');
  });
});

describe('periodOptions', () => {
  it('lists all time then the last 12 months in the org timezone', () => {
    const now = new Date('2026-11-01T03:00:00Z');
    const ny = periodOptions('America/New_York', now);
    expect(ny[0]).toEqual({ value: 'all', label: 'All time' });
    expect(ny).toHaveLength(13);
    expect(ny[1]).toEqual({ value: '2026-10', label: 'October 2026' });
    expect(ny[12].value).toBe('2025-11');
    expect(periodOptions('Not/AZone', now)[1]).toEqual({
      value: '2026-11',
      label: 'November 2026',
    });
  });
});
