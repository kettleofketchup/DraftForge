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
 */
export const DisplayName = (
  user: UserType | GuildMember | UserClassType | DisplayNameable | undefined,
): string => {
  if (!user) {
    return '?';
  }

  if ('user' in user) {
    // user is GuildMember - prefer nick, then global_name, then username
    return user.nick || user.user.global_name || user.user.username;
  }

  // Standard user - prefer nickname, then username, fallback to '?'
  return user.nickname || user.username || '?';
};

export const AvatarUrl = (
  user: UserType | GuildMember | UserClassType | undefined,
): string => {
  const genUrl = `https://ui-avatars.com/api/?rounded=True&background=random`;
  const discordCdn = `https://cdn.discordapp.com/avatars`;

  if (!user) {
    return `${genUrl}&name=?&length=1`;
  }

  if ('user' in user) {
    // user is GuildMember
    return user.user.avatar
      ? `${discordCdn}/${user.user.id}/${user.user.avatar}`
      : `${genUrl}&name=${encodeURIComponent(
          user.nick || user.user.global_name || user.user.username,
        )}`;
  }

  // Generate fallback URL from username/nickname (after GuildMember check)
  const fallback = `${genUrl}&length=2&name=${encodeURIComponent(
    user.nickname || user.username,
  )}`;

  // 1. Use avatarUrl if available (full URL from backend)
  if (user.avatarUrl) {
    return user.avatarUrl;
  }

  // 2. If avatar is already a full URL, use it
  if (user.avatar?.startsWith('http')) {
    return user.avatar;
  }

  // 3. If we have discordId and avatar hash, construct Discord CDN URL
  if (user.discordId && user.avatar) {
    return `${discordCdn}/${user.discordId}/${user.avatar}`;
  }

  // 4. Fall back to generated avatar from username
  return fallback;
};
