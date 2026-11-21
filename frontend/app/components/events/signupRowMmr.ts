import type { EventSignupType } from '~/components/events/schemas';
import { GAME_TYPE, type GameTypeValue } from '~/components/game/constants';
import type { UserType } from '~/components/user/types';
import { selectOrgMmr } from '~/store/selectOrgMmr';
import { isUserEntry, type UserEntry } from '~/store/userCacheTypes';

/** Org MMR for the event's game, then the API value, then self-reported (Dota only). */
export function signupRowMmr(
  user: UserEntry | UserType | undefined,
  signup: Pick<EventSignupType, 'org_user_mmr' | 'dota_profile'>,
  orgId: number | undefined,
  gameType: GameTypeValue,
): number | null {
  const cached =
    user && isUserEntry(user) ? selectOrgMmr(user, orgId, gameType) : undefined;
  if (cached != null) return cached;
  if (signup.org_user_mmr != null) return signup.org_user_mmr;
  if (gameType === GAME_TYPE.DOTA2) return signup.dota_profile?.mmr ?? null;
  return null;
}
