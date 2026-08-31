import { useGameType } from '~/hooks/useGameType';
import { useUserCacheStore } from '~/store/userCacheStore';
import { selectPositions } from '~/store/selectPositions';
import type { PositionsType } from '~/store/userCacheTypes';

/**
 * Reactive positions read for DISPLAY surfaces, off the list-populated flat
 * `_users[]` entity adapter (userCacheStore). Returns undefined when no active
 * game — never silently defaults to Dota. The Dota EDIT tab does NOT use this;
 * it reads positions off the modal's layered `profile.gameUser.dota.positions`.
 * Cannot be called inside `.map()` row callbacks (Rules of Hooks) — for per-row
 * reads in a list, call `selectPositions(useUserCacheStore.getState(), pk, gt)`
 * ONCE at the component top with a single store subscription, or subscribe the
 * whole row list. orgUserId is T3.
 */
export function usePlayerPositions(userPk: number): PositionsType | undefined {
  const gameType = useGameType();
  return useUserCacheStore((s) => selectPositions(s, userPk, gameType));
}
