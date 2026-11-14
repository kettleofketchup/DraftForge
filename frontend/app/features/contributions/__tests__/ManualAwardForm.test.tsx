import { describe, expect, it } from 'vitest';
import { manualAwardSchema } from '../schemas';
import { todayInZone } from '../timezone';

const valid = {
  user_id: 3,
  points: 5,
  reason: 'Ran the caster desk',
  date: '2026-11-01',
};

function errorPaths(input: unknown): string[] {
  const result = manualAwardSchema.safeParse(input);
  return result.success ? [] : result.error.issues.map((i) => i.path.join('.'));
}

describe('manualAwardSchema', () => {
  it('accepts a valid award with and without an event', () => {
    expect(manualAwardSchema.parse(valid)).toEqual(valid);
    expect(manualAwardSchema.parse({ ...valid, event_id: 12 }).event_id).toBe(12);
    expect(manualAwardSchema.parse({ ...valid, event_id: null }).event_id).toBeNull();
  });

  it('trims the reason', () => {
    expect(manualAwardSchema.parse({ ...valid, reason: '  Casting  ' }).reason).toBe('Casting');
  });

  it('rejects a blank or whitespace-only reason', () => {
    expect(errorPaths({ ...valid, reason: '' })).toEqual(['reason']);
    expect(errorPaths({ ...valid, reason: '    ' })).toEqual(['reason']);
  });

  it('rejects a reason over 500 characters', () => {
    expect(errorPaths({ ...valid, reason: 'x'.repeat(501) })).toEqual(['reason']);
    expect(errorPaths({ ...valid, reason: 'x'.repeat(500) })).toEqual([]);
  });

  it('rejects zero, negative, fractional and over-1000 points', () => {
    expect(errorPaths({ ...valid, points: 0 })).toEqual(['points']);
    expect(errorPaths({ ...valid, points: -5 })).toEqual(['points']);
    expect(errorPaths({ ...valid, points: 2.5 })).toEqual(['points']);
    expect(errorPaths({ ...valid, points: 1001 })).toEqual(['points']);
    expect(errorPaths({ ...valid, points: Number.NaN })).toEqual(['points']);
    expect(errorPaths({ ...valid, points: 1000 })).toEqual([]);
    expect(errorPaths({ ...valid, points: 1 })).toEqual([]);
  });

  it('requires a member', () => {
    expect(errorPaths({ ...valid, user_id: 0 })).toEqual(['user_id']);
  });

  it('requires a real YYYY-MM-DD date', () => {
    expect(errorPaths({ ...valid, date: '' })).toEqual(['date']);
    expect(errorPaths({ ...valid, date: '11/01/2026' })).toEqual(['date']);
    expect(errorPaths({ ...valid, date: '2026-02-30' })).toEqual(['date']);
  });
});

describe('todayInZone', () => {
  it('returns the org-local calendar date', () => {
    const now = new Date('2026-11-01T03:00:00Z');
    expect(todayInZone('America/New_York', now)).toBe('2026-10-31');
    expect(todayInZone('UTC', now)).toBe('2026-11-01');
  });

  it('falls back to UTC for a bad zone', () => {
    expect(todayInZone('Not/AZone', new Date('2026-11-01T03:00:00Z'))).toBe('2026-11-01');
  });
});
