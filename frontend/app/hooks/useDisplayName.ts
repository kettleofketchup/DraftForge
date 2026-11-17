import {
  type DiscordMemberLike,
  isDiscordMember,
  type NameSource,
  resolveDisplayName,
} from '~/lib/userDisplayName';
import { type UserCacheState, useUserCacheStore } from '~/store/userCacheStore';

type DisplayNameInput =
  | NameSource
  | DiscordMemberLike
  | number
  | null
  | undefined;

function selectName(
  s: UserCacheState,
  userOrPk: DisplayNameInput,
  orgId: number | null,
  maxLength: number | undefined,
): string {
  const opts = { orgId, maxLength };
  if (typeof userOrPk === 'number') {
    return resolveDisplayName(s.entities[userOrPk] ?? { pk: userOrPk }, opts);
  }
  if (!userOrPk || typeof userOrPk !== 'object') return '?';
  if (isDiscordMember(userOrPk) || orgId === null) {
    return resolveDisplayName(userOrPk, opts);
  }
  const own = userOrPk.orgNicknames;
  if (own && Object.prototype.hasOwnProperty.call(own, orgId)) {
    return resolveDisplayName(userOrPk, opts);
  }
  const stored =
    typeof userOrPk.pk === 'number'
      ? (s.entities[userOrPk.pk]?.orgNicknames?.[orgId] ?? null)
      : null;
  return resolveDisplayName(
    { ...userOrPk, orgNicknames: { ...own, [orgId]: stored } },
    opts,
  );
}

export function useDisplayName(
  userOrPk: DisplayNameInput,
  orgId: number | null,
  opts?: { maxLength?: number },
): string {
  const maxLength = opts?.maxLength;
  return useUserCacheStore((s) => selectName(s, userOrPk, orgId, maxLength));
}
