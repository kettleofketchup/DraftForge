import { GAME_TYPE } from '~/components/game/constants';
import type { GameTypeValue } from '~/components/game/constants';

import type { UserCacheState } from './userCacheStore';
import type { PositionsType } from './userCacheTypes';

/**
 * Read a user's positions from the list-populated, rendered-once flat
 * `_users[]` entity adapter (userCacheStore). gameType-gated so future games
 * resolve their own layer. orgUserId is a T3 parameter (org overrides) — pass
 * undefined in T2. Returns the stored reference (or undefined) — stable for
 * Zustand Object.is, no per-call allocation.
 */
export function selectPositions(
  state: UserCacheState,
  userPk: number,
  gameType: GameTypeValue | null,
  _orgUserId?: number, // T3 only
): PositionsType | undefined {
  if (gameType !== GAME_TYPE.DOTA2) return undefined;
  return state.entities[userPk]?.positions ?? undefined;
}
