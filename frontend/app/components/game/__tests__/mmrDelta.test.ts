import { describe, expect, it } from 'vitest';
import { computeMmrDelta } from '../mmrDelta';

describe('computeMmrDelta', () => {
  it('has no percentage and is never large from 0', () => {
    expect(computeMmrDelta(0, 4000)).toEqual({
      delta: 4000,
      pct: null,
      isLarge: false,
    });
  });

  it('is not large at 19%', () => {
    const result = computeMmrDelta(1000, 1190);
    expect(result.delta).toBe(190);
    expect(result.pct).toBeCloseTo(0.19);
    expect(result.isLarge).toBe(false);
  });

  it('is large at exactly 20%', () => {
    expect(computeMmrDelta(1000, 1200)).toEqual({
      delta: 200,
      pct: 0.2,
      isLarge: true,
    });
  });

  it('treats a decrease by its absolute size', () => {
    expect(computeMmrDelta(5000, 3000)).toEqual({
      delta: -2000,
      pct: 0.4,
      isLarge: true,
    });
  });

  it('is not large when unchanged', () => {
    expect(computeMmrDelta(4000, 4000)).toEqual({
      delta: 0,
      pct: 0,
      isLarge: false,
    });
  });
});
