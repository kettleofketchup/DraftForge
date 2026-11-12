import { describe, expect, it } from 'vitest';
import { resolveViewedRound } from '../utils';
import type { DraftRoundType } from '../types';
import { user } from './fixtures';

const r = (pk: number, pick_number: number, captainPk: number) =>
  ({ pk, pick_number, captain: user(captainPk), choice: null }) as unknown as DraftRoundType;

describe('resolveViewedRound', () => {
  it('force-jump wins over a stale viewed round when autoAdvance is off', () => {
    const rounds = [r(22, 1, 8), r(21, 2, 7), r(23, 3, 9)];
    const res = resolveViewedRound(rounds, r(21, 1, 7), { autoAdvance: false, latestRoundPk: 22, forceJumpToRoundPk: 22 });
    expect(res.round?.pk).toBe(22);
    expect(res.moved).toEqual({ captain: user(7), pickNumber: 2 });
  });

  it('without a force-jump and autoAdvance off, keeps the viewed pk', () => {
    const res = resolveViewedRound([r(21, 1, 7), r(22, 2, 8)], r(21, 1, 7), { autoAdvance: false, latestRoundPk: 22, forceJumpToRoundPk: null });
    expect(res.round?.pk).toBe(21);
    expect(res.moved).toBeNull();
  });

  it('autoAdvance moves to latest; a missing viewed pk yields null', () => {
    expect(resolveViewedRound([r(21, 1, 7), r(22, 2, 8)], r(21, 1, 7), { autoAdvance: true, latestRoundPk: 22, forceJumpToRoundPk: null }).round?.pk).toBe(22);
    expect(resolveViewedRound([r(22, 2, 8)], r(99, 1, 7), { autoAdvance: false, latestRoundPk: 22, forceJumpToRoundPk: null }).round).toBeNull();
  });

  it('force-jump reports no move when the viewed pick number is unchanged', () => {
    const res = resolveViewedRound([r(21, 1, 7), r(22, 2, 8)], r(21, 1, 7), { autoAdvance: false, latestRoundPk: 22, forceJumpToRoundPk: 22 });
    expect(res.round?.pk).toBe(22);
    expect(res.moved).toBeNull();
  });
});
