import type { GuildMember, UserClassType, UserType } from '~/index';
import {
  type DiscordMemberLike,
  type NameSource,
  resolveDisplayName,
} from '~/lib/userDisplayName';

type DisplayNameable = {
  pk?: number | null;
  // Username may be null for Steam-only signups (model field is null=True).
  username?: string | null;
  discordNickname?: string | null;
  orgNicknames?: Record<number, string | null>;
};

/**
 * Display name via resolveDisplayName: org server nickname (when orgId is
 * given) > global Discord name > username.
 */
export const DisplayName = (
  user:
    | UserType
    | GuildMember
    | UserClassType
    | DisplayNameable
    | DiscordMemberLike
    | undefined,
  maxLength?: number,
  orgId?: number | null,
): string => {
  if (!user || typeof user !== 'object') {
    return '?';
  }
  return resolveDisplayName(user as NameSource | GuildMember, {
    maxLength,
    orgId: orgId ?? null,
  });
};

// Re-export AvatarUrl from UserAvatar for backwards compatibility
export { AvatarUrl } from './UserAvatar';
