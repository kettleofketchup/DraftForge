import { describe, expect, it } from 'vitest';
import { memberCountDisplay } from '../memberCountDisplay';

const base = {
  entityId: 5,
  loadedForId: null,
  loading: false,
  loadedCount: 0,
  fallbackCount: undefined,
};

describe('memberCountDisplay', () => {
  it('uses the loaded list length once loaded for this entity', () => {
    expect(
      memberCountDisplay({
        ...base,
        loadedForId: 5,
        loadedCount: 3,
        fallbackCount: 9,
      }),
    ).toBe(3);
  });

  it('falls back to users_count when the list is not loaded', () => {
    expect(memberCountDisplay({ ...base, fallbackCount: 9 })).toBe(9);
  });

  it('falls back to users_count when the list belongs to another entity', () => {
    expect(
      memberCountDisplay({
        ...base,
        loadedForId: 6,
        loadedCount: 2,
        fallbackCount: 9,
      }),
    ).toBe(9);
  });

  it('falls back to users_count while the list is loading', () => {
    expect(
      memberCountDisplay({
        ...base,
        loadedForId: 5,
        loading: true,
        fallbackCount: 9,
      }),
    ).toBe(9);
  });

  it('shows a zero users_count rather than the placeholder', () => {
    expect(memberCountDisplay({ ...base, fallbackCount: 0 })).toBe(0);
  });

  it('shows the placeholder only when neither count is known', () => {
    expect(memberCountDisplay(base)).toBe('...');
  });
});
