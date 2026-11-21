import type { PositionsType } from '~/store/userCacheTypes';

/** True if the user has rated any role above 0. */
export function hasAnyPosition(p: PositionsType | undefined): boolean {
  if (!p) return false;
  return (
    (p.carry ?? 0) > 0 ||
    (p.mid ?? 0) > 0 ||
    (p.offlane ?? 0) > 0 ||
    (p.soft_support ?? 0) > 0 ||
    (p.hard_support ?? 0) > 0
  );
}
