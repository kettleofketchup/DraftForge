import { describe, expect, it } from 'vitest';
import { deriveDraftIndex } from '~/components/teamdraft/utils';

describe('deriveDraftIndex', () => {
  const before = [
    { pk: 11, pick_number: 1 },
    { pk: 12, pick_number: 2 },
    { pk: 13, pick_number: 3 },
  ];
  it('viewing index 1 (pk 12) survives a 1<->2 swap as index 0', () => {
    expect(deriveDraftIndex(before, 12)).toBe(1);
    const after = [
      { pk: 12, pick_number: 1 },
      { pk: 11, pick_number: 2 },
      { pk: 13, pick_number: 3 },
    ];
    expect(deriveDraftIndex(after, 12)).toBe(0);
  });
  it('is -1 for a missing pk or no rounds', () => {
    expect(deriveDraftIndex(before, 99)).toBe(-1);
    expect(deriveDraftIndex(null, 12)).toBe(-1);
    expect(deriveDraftIndex(before, null)).toBe(-1);
  });
});
