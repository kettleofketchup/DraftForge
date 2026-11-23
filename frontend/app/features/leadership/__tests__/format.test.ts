import { describe, expect, it } from 'vitest';
import { formatRating, placementLabel } from '../format';

describe('formatRating', () => {
  it('rounds to one decimal', () => {
    expect(formatRating(3.456)).toBe('3.5');
    expect(formatRating(4)).toBe('4.0');
  });

  it('shows a dash for no rating', () => {
    expect(formatRating(null)).toBe('—');
  });
});

describe('placementLabel', () => {
  it('uses ordinal suffixes', () => {
    expect(placementLabel(1)).toBe('1st');
    expect(placementLabel(2)).toBe('2nd');
    expect(placementLabel(3)).toBe('3rd');
    expect(placementLabel(4)).toBe('4th');
    expect(placementLabel(11)).toBe('11th');
    expect(placementLabel(12)).toBe('12th');
    expect(placementLabel(13)).toBe('13th');
    expect(placementLabel(21)).toBe('21st');
    expect(placementLabel(22)).toBe('22nd');
  });

  it('returns null without a placement', () => {
    expect(placementLabel(null)).toBeNull();
  });
});
