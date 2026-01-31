import type { GuildMember, UserClassType, UserType } from '~/index';

/**
 * Generic type for any object with username/nickname fields.
 * Accepts full UserType, simple captain objects from serializers, etc.
 * Username can be optional to handle partial data from various sources.
 */
type DisplayNameable = {
  username?: string;
  nickname?: string | null;
};

/**
 * Get the display name for a user.
 * Priority: nickname > username
 * @param user - The user object
 * @param maxLength - Optional max length to truncate to (adds … if truncated)
 */
export const DisplayName = (
  user: UserType | GuildMember | UserClassType | DisplayNameable | undefined,
  maxLength?: number,
): string => {
  if (!user) {
    return '?';
  }

  let name: string;

  if ('user' in user) {
    // user is GuildMember - prefer nick, then global_name, then username
    name = user.nick || user.user.global_name || user.user.username;
  } else {
    // Standard user - prefer nickname, then username, fallback to '?'
    name = user.nickname || user.username || '?';
  }

  // Truncate if maxLength specified and name exceeds it
  if (maxLength && name.length > maxLength) {
    return `${name.substring(0, maxLength)}…`;
  }

  return name;
};

// Re-export AvatarUrl from UserAvatar for backwards compatibility
export { AvatarUrl } from './UserAvatar';
