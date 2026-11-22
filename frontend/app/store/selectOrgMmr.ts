import type { GameTypeValue } from '~/components/game/constants';

import { useUserCacheStore } from './userCacheStore';
import type { UserEntry } from './userCacheTypes';

export function selectOrgMmr(
  entry: UserEntry | undefined,
  orgId: number | undefined,
  gameType: GameTypeValue,
): number | undefined {
  if (!entry || orgId == null) return undefined;
  return entry.orgData[orgId]?.mmrs[gameType];
}

export function useOrgMmr(
  userPk: number | undefined,
  orgId: number | undefined,
  gameType: GameTypeValue,
): number | undefined {
  return useUserCacheStore((s) =>
    selectOrgMmr(
      userPk != null ? s.entities[userPk] : undefined,
      orgId,
      gameType,
    ),
  );
}
