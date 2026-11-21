import type { GameTypeValue } from '~/components/game/constants';
import { GAME_TYPE } from '~/components/game/constants';

import type { UserCacheState } from './userCacheStore';
import type { PositionsType } from './userCacheTypes';

/**
 * Read a user's positions from the list-populated, rendered-once flat
 * `_users[]` entity adapter (userCacheStore). gameType-gated so future games
 * resolve their own layer. orgUserId is reserved for org overrides and is
 * unused; pass undefined. Returns the stored reference (or undefined) — stable for
 * Zustand Object.is, no per-call allocation.
 */
export function selectPositions(
  state: UserCacheState,
  userPk: number,
  gameType: GameTypeValue | null,
  _orgUserId?: number, // unused until org-scoped positions exist
): PositionsType | undefined {
  if (gameType !== GAME_TYPE.DOTA2) return undefined;
  return state.entities[userPk]?.positions ?? undefined;
}
