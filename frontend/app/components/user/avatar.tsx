import type { GuildMember, UserClassType, UserType } from '~/index';

export const AvatarUrl = (
  user: UserType | GuildMember | UserClassType | undefined,
): string => {
  var genUrl = `https://ui-avatars.com/api/?rounded=True&background=random`;
  var discordUrl = `https://cdn.discordapp.com/avatars/`;
  let avatarUrl;

  if (!user) {
    return `${genUrl}&name=?&length=1`;
  }

  if ('user' in user) {
    // user is GuildMember
    return user.user.avatar
      ? `${discordUrl}/${user.user.id}/${user.user.avatar}`
      : `${genUrl}&name=${encodeURIComponent(
          user.nick || user.user.global_name || user.user.username,
        )}`;
  }

  if (!user.avatar) {
    return `${genUrl}&length=2&name=${encodeURIComponent(
      user.nickname || user.username,
    )}`;
  }

  // Use avatarUrl if available, otherwise fall back to avatar field (which may be the full URL)
  // If neither has a valid URL, generate one from username
  return user.avatarUrl || user.avatar || `${genUrl}&length=2&name=${encodeURIComponent(
    user.nickname || user.username,
  )}`;
};
