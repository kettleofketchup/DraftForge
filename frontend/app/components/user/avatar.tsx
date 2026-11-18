import type { GuildMember, UserClassType, UserType } from '~/index';
import { currentDisplayOrgId } from '~/lib/displayOrg';
import {
  type DiscordMemberLike,
  resolveDisplayName,
  type UserRef,
} from '~/lib/userDisplayName';

/**
 * Display name for any user payload: org server nickname (in an org context),
 * then global Discord name, then username. Missing fields come from the user
 * cache. `orgId` defaults to the current page's org; pass `null` for none.
 */
export const DisplayName = (
  user: UserType | GuildMember | UserClassType | UserRef | undefined,
  maxLength?: number,
  orgId?: number | null,
): string => {
  if (!user || typeof user !== 'object') {
    return '?';
  }
  return resolveDisplayName(user as UserRef | DiscordMemberLike, {
    maxLength,
    orgId: orgId === undefined ? currentDisplayOrgId() : orgId,
  });
};

// Re-export AvatarUrl from UserAvatar for backwards compatibility
export { AvatarUrl } from './UserAvatar';
